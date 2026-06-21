"""Regression detector — patched fingerprint + new occurrence within grace = resurrect.

Keeps accepted dispositions honest: a "fixed" item that comes back is news,
not noise. Fires in queue.ingest() when the matched fingerprint is in
terminal ``patched`` state.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def _to_dt(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return None


def is_regression(row: dict, *, occurred_at: datetime, config: dict) -> bool:
    """True if ``row`` is patched and reappears *within* the grace window.

    A patched fingerprint whose new occurrence lands at or before
    ``patched_at + regression_grace_hours`` is a regression (per README + the
    0.1.0 plan: "a new occurrence within ``regression_grace_hours`` resurrects").
    Reappearances after the grace window are treated as fresh, not regressions.
    """
    if (row.get("status") or "") != "patched":
        return False
    patched_at = _to_dt(row.get("patched_at"))
    if patched_at is None:
        return False
    occ = _to_dt(occurred_at)
    if occ is None:
        return False
    grace = timedelta(hours=float(config["regression_grace_hours"]))
    return occ <= patched_at + grace


def resurrect(queue, fingerprint_id: int, *, note: str = "") -> bool:
    """Flip a row to ``status='new', regression=1``, log the transition with
    actor ``"ingest"``, and notify via the queue's notify hook if present.
    """
    from sqlalchemy import select, update, insert

    from swarph_triage.schema import fingerprints, state_log

    with queue.engine.begin() as conn:
        row = conn.execute(
            select(fingerprints).where(fingerprints.c.id == fingerprint_id)
        ).mappings().one_or_none()
        if row is None:
            return False
        from_status = row["status"]
        now = datetime.now(timezone.utc)
        conn.execute(
            update(fingerprints)
            .where(fingerprints.c.id == fingerprint_id)
            .values(status="new", regression=1)
        )
        conn.execute(insert(state_log).values(
            fingerprint_id=fingerprint_id,
            from_status=from_status,
            to_status="new",
            actor="ingest",
            note=note or "regression detected",
            transitioned_at=now,
        ))

    if queue.notify_fn is not None:
        try:
            queue.notify_fn("regression", {"fingerprint_id": fingerprint_id, "note": note})
        except Exception:
            pass
    return True
