"""Regression detector — patched fingerprint + new occurrence within grace = resurrect.

Keeps accepted dispositions honest: a "fixed" item that comes back is news,
not noise. Fires in queue.ingest() when the matched fingerprint is in
terminal ``patched`` state.
"""

from __future__ import annotations

from datetime import datetime


def is_regression(row: dict, *, occurred_at: datetime, config: dict) -> bool:
    """Stub — implementation lands with queue.ingest() port.

    Returns True if ``row.patched_at + regression_grace_hours <= occurred_at``.
    """
    raise NotImplementedError("regression.is_regression — to land in queue-ingest port")


def resurrect(queue, fingerprint_id: int, *, note: str = "") -> bool:
    """Stub — flip row to ``status='new', regression=1``, log the transition,
    optionally notify caller via the queue's notify hook.
    """
    raise NotImplementedError("regression.resurrect — to land in queue-ingest port")
