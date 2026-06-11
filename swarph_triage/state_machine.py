"""State machine — 6 states + an explicit transition matrix.

The state machine itself has no domain coupling. ``proposed_fix`` content,
``actionability`` scoring, and ingest source are all consumer-supplied.
"""

from __future__ import annotations

from enum import Enum


class Status(str, Enum):
    NEW = "new"
    TRIAGED = "triaged"
    APPROVED = "approved"
    PATCHED = "patched"
    WONTFIX = "wontfix"
    NEEDS_REVIEW = "needs_review"


# Allowed forward transitions. Reverse / lateral moves go via ``reopen``
# (any terminal state → NEW) which is handled explicitly in queue.transition().
VALID_TRANSITIONS: dict[Status, set[Status]] = {
    Status.NEW: {Status.TRIAGED, Status.WONTFIX, Status.NEEDS_REVIEW},
    Status.TRIAGED: {Status.APPROVED, Status.WONTFIX, Status.NEEDS_REVIEW},
    Status.APPROVED: {Status.PATCHED, Status.NEEDS_REVIEW, Status.WONTFIX},
    Status.PATCHED: set(),       # terminal except via reopen / regression resurrect
    Status.WONTFIX: set(),       # terminal except via reopen
    Status.NEEDS_REVIEW: {Status.TRIAGED, Status.APPROVED, Status.WONTFIX},
}

TERMINAL: frozenset[Status] = frozenset({Status.PATCHED, Status.WONTFIX})


def can_transition(from_status: Status, to_status: Status) -> bool:
    """Pure check — does the matrix allow this move?

    Does NOT handle ``reopen`` (terminal → NEW) — that's an explicit method
    on TriageQueue with its own audit semantics.
    """
    if from_status == to_status:
        return False
    return to_status in VALID_TRANSITIONS.get(from_status, set())
