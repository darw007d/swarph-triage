"""TriageQueue — main class. Public API.

Skeleton signatures only; each method is a stub that documents the contract.
Implementation lands in follow-up commits per the README "Status" line.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping, Optional

from sqlalchemy.engine import Engine

from swarph_triage.config import load_config
from swarph_triage.state_machine import Status


ProposerFn = Callable[[dict, list[dict]], dict | None]
NotifyFn = Callable[[str, dict], None]


class TriageQueue:
    """Backend-agnostic ranked-queue triage primitive.

    Construct via :func:`open()` rather than this class directly — ``open()``
    handles engine creation, schema bootstrap, and config merge.
    """

    def __init__(
        self,
        engine: Engine,
        *,
        config: dict[str, Any],
        proposer_fn: ProposerFn | None = None,
        notify_fn: NotifyFn | None = None,
    ) -> None:
        self.engine = engine
        self.config = config
        self.proposer_fn = proposer_fn
        self.notify_fn = notify_fn

    # ─── ingest ────────────────────────────────────────────────────────────
    def ingest(
        self,
        *,
        fingerprint: str,
        severity: str = "medium",
        actionability: float = 1.0,
        category: str | None = None,
        context: Mapping[str, Any] | None = None,
        occurred_at=None,  # datetime | None — defaults to now()
    ) -> int:
        """Stub — UPSERT a fingerprint, append an occurrence, return fp_id.

        Side effects:
        - If fingerprint exists in ``patched`` and ``occurred_at`` is within
          ``regression_grace_hours``: resurrect to ``new``, regression=1.
        - If fingerprint is ``new`` and a proposer_fn is registered, fire it
          and store ``proposed_fix``, transition to ``triaged``.
        """
        raise NotImplementedError("queue.ingest — implementation in flight")

    # ─── transitions ───────────────────────────────────────────────────────
    def transition(
        self,
        fingerprint_id: int,
        *,
        to_status: Status | str,
        actor: str,
        note: str = "",
    ) -> bool:
        """Stub — move row to ``to_status`` if allowed by state machine.

        Logs to ``state_log``, updates ``triaged_at`` / ``approved_at`` /
        ``patched_at`` timestamps. Returns False if transition is disallowed.
        """
        raise NotImplementedError("queue.transition — implementation in flight")

    def reopen(self, fingerprint_id: int, *, actor: str, note: str = "") -> bool:
        """Stub — terminal state → NEW (resurrect path for human review).

        Distinct from ``regression.resurrect`` (which sets regression=1
        automatically); ``reopen`` is human-initiated and does not flag.
        """
        raise NotImplementedError("queue.reopen — implementation in flight")

    # ─── reads ─────────────────────────────────────────────────────────────
    def list(
        self,
        *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """Stub — return rows ordered by priority_score desc. Filter by status."""
        raise NotImplementedError("queue.list — implementation in flight")

    def show(self, fingerprint_id: int, *, include_history: bool = True) -> dict:
        """Stub — full row + recent occurrences + state_log entries."""
        raise NotImplementedError("queue.show — implementation in flight")

    def stats(self) -> dict[str, Any]:
        """Stub — counts per status, regression count, oldest-new age, etc."""
        raise NotImplementedError("queue.stats — implementation in flight")

    def history(self, fingerprint_id: int) -> list[dict]:
        """Stub — full state_log for a fingerprint, oldest-first."""
        raise NotImplementedError("queue.history — implementation in flight")

    # ─── maintenance ───────────────────────────────────────────────────────
    def recompute_priorities(self) -> int:
        """Stub — re-score every non-terminal row. Returns rows updated."""
        raise NotImplementedError("queue.recompute_priorities — implementation in flight")

    def prune_occurrences(self, *, older_than_days: int = 30) -> int:
        """Stub — delete occurrences older than N days. Returns rows pruned."""
        raise NotImplementedError("queue.prune_occurrences — implementation in flight")

    def backlog_md(self) -> str:
        """Stub — render the queue as a markdown snapshot string."""
        raise NotImplementedError("queue.backlog_md — implementation in flight")


def open(
    db_url: str,
    *,
    config: Mapping[str, Any] | None = None,
    proposer_fn: ProposerFn | None = None,
    notify_fn: NotifyFn | None = None,
    create_tables: bool = True,
) -> TriageQueue:
    """Open a TriageQueue against ``db_url`` (sqlite:/// or postgresql://).

    Bootstraps the schema if ``create_tables`` is True (idempotent — safe to
    call repeatedly).
    """
    from sqlalchemy import create_engine
    from swarph_triage.schema import create_all

    engine = create_engine(db_url, future=True)
    if create_tables:
        create_all(engine)

    merged_cfg: dict[str, Any] = load_config(config)
    return TriageQueue(
        engine,
        config=merged_cfg,
        proposer_fn=proposer_fn,
        notify_fn=notify_fn,
    )
