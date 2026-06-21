"""TriageQueue — main class. Public API.

Skeleton signatures only; each method is a stub that documents the contract.
Implementation lands in follow-up commits per the README "Status" line.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping, Optional

from sqlalchemy.engine import Engine

from swarph_triage.config import load_config
from swarph_triage.state_machine import (
    Status,
    TERMINAL,
    VALID_TRANSITIONS,
    can_transition,
)


def _coerce_now(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now


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
        """UPSERT a fingerprint, append an occurrence, return fp_id.

        Side effects:
        - If fingerprint exists in ``patched`` and ``occurred_at`` is within
          ``regression_grace_hours``: resurrect to ``new``, regression=1.
        - If fingerprint is ``new`` and a proposer_fn is registered, fire it
          and store ``proposed_fix``, transition to ``triaged``.
        """
        from sqlalchemy import select, insert, update

        from swarph_triage import regression
        from swarph_triage.priority import compute
        from swarph_triage.schema import fingerprints, occurrences, state_log

        occ_dt = _coerce_now(occurred_at)
        ctx = dict(context) if context else None

        with self.engine.begin() as conn:
            existing = conn.execute(
                select(fingerprints).where(
                    fingerprints.c.fingerprint == fingerprint
                )
            ).mappings().one_or_none()

            if existing is None:
                res = conn.execute(insert(fingerprints).values(
                    fingerprint=fingerprint,
                    severity=severity,
                    category=category,
                    status="new",
                    count_total=1,
                    count_24h=1,
                    first_seen=occ_dt,
                    last_seen=occ_dt,
                    actionability=actionability,
                    priority_score=0.0,
                    regression=0,
                    context=ctx,
                ))
                fp_id = res.inserted_primary_key[0]
                conn.execute(insert(state_log).values(
                    fingerprint_id=fp_id,
                    from_status=None,
                    to_status="new",
                    actor="ingest",
                    note="",
                    transitioned_at=occ_dt,
                ))
            else:
                fp_id = existing["id"]
                values: dict[str, Any] = {
                    "count_total": (existing["count_total"] or 0) + 1,
                    "last_seen": occ_dt,
                }
                # Regression: a patched fingerprint reappearing within grace.
                if regression.is_regression(
                    dict(existing), occurred_at=occ_dt, config=self.config
                ):
                    values["status"] = "new"
                    values["regression"] = 1
                    conn.execute(insert(state_log).values(
                        fingerprint_id=fp_id,
                        from_status=existing["status"],
                        to_status="new",
                        actor="ingest",
                        note="regression detected",
                        transitioned_at=occ_dt,
                    ))
                conn.execute(
                    update(fingerprints)
                    .where(fingerprints.c.id == fp_id)
                    .values(**values)
                )

            # Append the occurrence.
            conn.execute(insert(occurrences).values(
                fingerprint_id=fp_id,
                occurred_at=occ_dt,
                payload=ctx,
            ))

            # Recompute count_24h relative to this occurrence.
            window_start = occ_dt - timedelta(hours=24)
            from sqlalchemy import func
            count_24h = conn.execute(
                select(func.count()).select_from(occurrences).where(
                    occurrences.c.fingerprint_id == fp_id,
                    occurrences.c.occurred_at > window_start,
                )
            ).scalar() or 0
            conn.execute(
                update(fingerprints)
                .where(fingerprints.c.id == fp_id)
                .values(count_24h=count_24h)
            )

            # Recompute priority for this row, "now" = the latest occurrence.
            row = conn.execute(
                select(fingerprints).where(fingerprints.c.id == fp_id)
            ).mappings().one()
            score = compute(dict(row), now_ts=occ_dt.timestamp(), config=self.config)
            conn.execute(
                update(fingerprints)
                .where(fingerprints.c.id == fp_id)
                .values(priority_score=score)
            )

        # Optional proposer hook for fresh rows.
        if self.proposer_fn is not None and existing is None:
            try:
                proposal = self.proposer_fn(dict(row), [])
            except Exception:
                proposal = None
            if proposal and proposal.get("proposed_fix"):
                from sqlalchemy import update as _update
                with self.engine.begin() as conn:
                    conn.execute(
                        _update(fingerprints)
                        .where(fingerprints.c.id == fp_id)
                        .values(proposed_fix=proposal["proposed_fix"])
                    )

        return fp_id

    # ─── transitions ───────────────────────────────────────────────────────
    def transition(
        self,
        fingerprint_id: int,
        *,
        to_status: Status | str,
        actor: str,
        note: str = "",
        now: datetime | None = None,
    ) -> bool:
        """Move row to ``to_status`` if allowed by the state machine.

        Logs to ``state_log``, updates ``triaged_at`` / ``approved_at`` /
        ``patched_at`` timestamps. Returns False (writing nothing) if the
        transition is disallowed or the row is missing.
        """
        from sqlalchemy import select, insert, update

        from swarph_triage.schema import fingerprints, state_log

        to_value = to_status.value if isinstance(to_status, Status) else str(to_status)
        when = _coerce_now(now)

        with self.engine.begin() as conn:
            row = conn.execute(
                select(fingerprints.c.status).where(
                    fingerprints.c.id == fingerprint_id
                )
            ).mappings().one_or_none()
            if row is None:
                return False
            from_value = row["status"]
            try:
                from_status = Status(from_value)
                to_enum = Status(to_value)
            except ValueError:
                return False
            if not can_transition(from_status, to_enum):
                return False

            values: dict[str, Any] = {"status": to_value}
            if to_enum is Status.TRIAGED:
                values["triaged_at"] = when
            elif to_enum is Status.APPROVED:
                values["approved_at"] = when
            elif to_enum is Status.PATCHED:
                values["patched_at"] = when

            conn.execute(
                update(fingerprints)
                .where(fingerprints.c.id == fingerprint_id)
                .values(**values)
            )
            conn.execute(insert(state_log).values(
                fingerprint_id=fingerprint_id,
                from_status=from_value,
                to_status=to_value,
                actor=actor,
                note=note,
                transitioned_at=when,
            ))
        return True

    def let_cool(
        self,
        fingerprint_id: int,
        *,
        actor: str,
        note: str = "",
        now: datetime | None = None,
    ) -> bool:
        """Defer a row: set ``cooldown_until = now + cooldown_default_days``.

        The priority calc ramps the score back from zero as cooldown expires,
        so a deliberately-deferred item doesn't immediately re-surface. Returns
        False if the row is missing.
        """
        from sqlalchemy import select, insert, update

        from swarph_triage.schema import fingerprints, state_log

        when = _coerce_now(now)
        cooldown_until = when + timedelta(days=float(self.config["cooldown_default_days"]))

        with self.engine.begin() as conn:
            row = conn.execute(
                select(fingerprints.c.status).where(
                    fingerprints.c.id == fingerprint_id
                )
            ).mappings().one_or_none()
            if row is None:
                return False
            conn.execute(
                update(fingerprints)
                .where(fingerprints.c.id == fingerprint_id)
                .values(cooldown_until=cooldown_until)
            )
            conn.execute(insert(state_log).values(
                fingerprint_id=fingerprint_id,
                from_status=row["status"],
                to_status=row["status"],
                actor=actor,
                note=note or "let_cool",
                transitioned_at=when,
            ))
        return True

    def reopen(
        self,
        fingerprint_id: int,
        *,
        actor: str,
        note: str = "",
        now: datetime | None = None,
    ) -> bool:
        """Terminal state → NEW (human-initiated re-open).

        Distinct from ``regression.resurrect`` (which sets regression=1
        automatically); ``reopen`` does not flag. Returns False if the row is
        missing or not in a terminal state.
        """
        from sqlalchemy import select, insert, update

        from swarph_triage.schema import fingerprints, state_log

        when = _coerce_now(now)
        with self.engine.begin() as conn:
            row = conn.execute(
                select(fingerprints.c.status).where(
                    fingerprints.c.id == fingerprint_id
                )
            ).mappings().one_or_none()
            if row is None:
                return False
            try:
                from_status = Status(row["status"])
            except ValueError:
                return False
            if from_status not in TERMINAL:
                return False
            conn.execute(
                update(fingerprints)
                .where(fingerprints.c.id == fingerprint_id)
                .values(status="new")
            )
            conn.execute(insert(state_log).values(
                fingerprint_id=fingerprint_id,
                from_status=row["status"],
                to_status="new",
                actor=actor,
                note=note or "reopen",
                transitioned_at=when,
            ))
        return True

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
