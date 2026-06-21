"""Priority formula — config-driven, no hardcoded coefficients.

    priority = severity_w * freq_curve(count_24h) * decay(hours_since_last_seen)
                 * max(actionability, actionability_floor)

Clamped to ``[priority_min, priority_max]``. If ``cooldown_until`` is in the
future, the score is ramped toward zero (linear from cooldown-start to
cooldown-end) so a deliberately-deferred item doesn't immediately re-surface.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any


def _to_epoch(value: Any) -> float | None:
    """Coerce a stored timestamp (datetime or ISO string or epoch) to epoch
    seconds. sqlite hands back naive datetimes/strings; treat naive as UTC."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.timestamp()
    return None


def _freq_term(count_24h: float, config: dict) -> float:
    curve = config.get("freq_curve", "log")
    n = max(0.0, float(count_24h or 0))
    if curve == "linear":
        return n
    if curve == "sqrt":
        return math.sqrt(n)
    # default: log_base(1 + n)
    base = float(config.get("freq_log_base", 10))
    return math.log(1.0 + n) / math.log(base)


def compute(row: dict, *, now_ts: float, config: dict) -> float:
    """Compute a fingerprint's priority score.

    Args:
        row: a fingerprint row as dict (must have ``severity``, ``count_24h``,
            ``last_seen``, ``actionability``, ``cooldown_until``).
        now_ts: epoch seconds for "now". Caller supplies for testability.
        config: merged config dict (see ``swarph_triage.config``).

    Returns:
        Priority score in ``[config["priority_min"], config["priority_max"]]``.
    """
    severity_weights: dict = config["severity_weights"]
    severity = (row.get("severity") or "medium")
    sev_w = severity_weights.get(severity, 0.5)

    freq = _freq_term(row.get("count_24h", 0), config)

    last_seen_ts = _to_epoch(row.get("last_seen"))
    if last_seen_ts is None:
        hours_since = 0.0
    else:
        hours_since = max(0.0, (now_ts - last_seen_ts) / 3600.0)
    half_life = float(config["decay_half_life_hours"])
    decay = math.exp(-hours_since * math.log(2) / half_life)

    actionability = float(row.get("actionability", 1.0) or 0.0)
    actionability = max(actionability, float(config["actionability_floor"]))

    score = sev_w * freq * decay * actionability

    # Cooldown ramp: if cooldown_until is in the future, ramp the score toward
    # zero, linearly from cooldown-start (factor 0) to cooldown-end (factor 1).
    cd_end_ts = _to_epoch(row.get("cooldown_until"))
    if cd_end_ts is not None and cd_end_ts > now_ts:
        duration = float(config["cooldown_default_days"]) * 86400.0
        if duration > 0:
            remaining = cd_end_ts - now_ts
            ramp = 1.0 - (remaining / duration)
            ramp = min(1.0, max(0.0, ramp))
        else:
            ramp = 1.0
        score *= ramp

    lo = float(config["priority_min"])
    hi = float(config["priority_max"])
    return min(hi, max(lo, score))


def recompute_all(queue, *, now_ts: float | None = None) -> int:
    """Recompute ``priority_score`` for every non-terminal fingerprint.

    Returns the number of rows updated.
    """
    from sqlalchemy import select, update

    from swarph_triage.schema import fingerprints
    from swarph_triage.state_machine import TERMINAL

    if now_ts is None:
        now_ts = datetime.now(timezone.utc).timestamp()

    terminal_values = {s.value for s in TERMINAL}
    updated = 0
    with queue.engine.begin() as conn:
        rows = conn.execute(
            select(
                fingerprints.c.id,
                fingerprints.c.severity,
                fingerprints.c.count_24h,
                fingerprints.c.last_seen,
                fingerprints.c.actionability,
                fingerprints.c.cooldown_until,
                fingerprints.c.status,
            ).where(fingerprints.c.status.notin_(terminal_values))
        ).mappings().all()
        for r in rows:
            score = compute(dict(r), now_ts=now_ts, config=queue.config)
            conn.execute(
                update(fingerprints)
                .where(fingerprints.c.id == r["id"])
                .values(priority_score=score)
            )
            updated += 1
    return updated
