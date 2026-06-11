"""Priority formula — config-driven, no hardcoded coefficients.

    priority = severity_w * freq_curve(count_24h) * decay(hours_since_last_seen)
                 * max(actionability, actionability_floor)

Clamped to ``[priority_min, priority_max]``.
"""

from __future__ import annotations

from typing import Any  # noqa: F401  — used by future signature additions


def compute(row: dict, *, now_ts: float, config: dict) -> float:
    """Stub — implementation lands in the formula-port commit.

    Args:
        row: a fingerprint row as dict (must have ``severity``, ``count_24h``,
            ``last_seen``, ``actionability``, ``cooldown_until``).
        now_ts: epoch seconds for "now". Caller supplies for testability.
        config: merged config dict (see ``swarph_triage.config``).

    Returns:
        Priority score in ``[config["priority_min"], config["priority_max"]]``.
    """
    raise NotImplementedError("priority.compute — to land in formula-port commit")


def recompute_all(queue, *, now_ts: float | None = None) -> int:
    """Stub — recompute priority_score for every non-terminal fingerprint.

    Returns the number of rows updated.
    """
    raise NotImplementedError("priority.recompute_all — to land in formula-port commit")
