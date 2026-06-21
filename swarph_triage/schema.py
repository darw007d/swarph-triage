"""SQLAlchemy Core schema — 3 tables, 6 indexes, dialect-portable.

queue.ingest upserts via SELECT-then-INSERT/UPDATE (read-modify-write), which is
correct for the single-writer (cron) model these queues target. It is NOT atomic:
two concurrent ingests of the *same new* fingerprint could collide on the unique
constraint. A future revision can switch to a dialect ON CONFLICT for multi-writer.
"""

from __future__ import annotations

from sqlalchemy import (
    MetaData, Table, Column,
    Integer, Float, String, Text, DateTime, JSON, Index,
)

metadata = MetaData()


# ─────────────────────────────────────────────────────────────────────────────
# fingerprints — one row per logical issue/entity-action.
# Many concrete observations collapse here via fingerprint_fn.
# ─────────────────────────────────────────────────────────────────────────────
fingerprints = Table(
    "swarph_triage_fingerprints", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("fingerprint", String(128), nullable=False, unique=True),
    Column("severity", String(32), nullable=False, default="medium"),
    Column("category", String(64)),
    Column("status", String(32), nullable=False, default="new", index=True),

    # Occurrence rollups
    Column("count_total", Integer, nullable=False, default=0),
    Column("count_24h", Integer, nullable=False, default=0),
    Column("first_seen", DateTime(timezone=True), nullable=False),
    Column("last_seen", DateTime(timezone=True), nullable=False, index=True),

    # Disposition + audit
    Column("triaged_at", DateTime(timezone=True)),
    Column("approved_at", DateTime(timezone=True)),
    Column("patched_at", DateTime(timezone=True)),
    Column("cooldown_until", DateTime(timezone=True)),
    Column("proposed_fix", Text),
    Column("fix_commit_sha", String(64)),
    Column("notes", Text),
    Column("regression", Integer, nullable=False, default=0),  # 0/1

    # Tunables
    Column("actionability", Float, nullable=False, default=1.0),
    Column("priority_score", Float, nullable=False, default=0.0),

    # Free-form context payload (entity_id, channel, tier, ...).
    # Consumer-defined shape; library reads only for display/proposer.
    Column("context", JSON),
)


# ─────────────────────────────────────────────────────────────────────────────
# occurrences — append-only event stream. 30-day retention recommended.
# ─────────────────────────────────────────────────────────────────────────────
occurrences = Table(
    "swarph_triage_occurrences", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("fingerprint_id", Integer, nullable=False, index=True),
    Column("occurred_at", DateTime(timezone=True), nullable=False, index=True),
    Column("payload", JSON),
)


# ─────────────────────────────────────────────────────────────────────────────
# state_log — every transition (audit + history view).
# ─────────────────────────────────────────────────────────────────────────────
state_log = Table(
    "swarph_triage_state_log", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("fingerprint_id", Integer, nullable=False, index=True),
    Column("from_status", String(32)),
    Column("to_status", String(32), nullable=False),
    Column("actor", String(64), nullable=False),
    Column("note", Text),
    Column("transitioned_at", DateTime(timezone=True), nullable=False, index=True),
)


# Compound index for the "top of queue" query (most common read).
Index(
    "ix_fp_status_priority",
    fingerprints.c.status,
    fingerprints.c.priority_score.desc(),
)


def create_all(engine) -> None:
    """Create tables if absent (idempotent)."""
    metadata.create_all(engine)
