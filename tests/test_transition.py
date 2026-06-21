"""Task 3 — queue.transition (state-machine-enforced + state_log) + reopen + let_cool."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import swarph_triage
from swarph_triage.schema import fingerprints, state_log
from sqlalchemy import select, func


def _now() -> datetime:
    return datetime(2026, 6, 21, 12, 0, 0, tzinfo=timezone.utc)


def _open(tmp_path):
    return swarph_triage.open(f"sqlite:///{tmp_path/'t.db'}")


def _row(q, fp_id) -> dict:
    with q.engine.begin() as conn:
        return dict(conn.execute(
            select(fingerprints).where(fingerprints.c.id == fp_id)
        ).mappings().one())


def _logs(q, fp_id):
    with q.engine.begin() as conn:
        return conn.execute(
            select(state_log).where(state_log.c.fingerprint_id == fp_id)
        ).mappings().all()


def test_valid_transition_succeeds_and_logs(tmp_path):
    q = _open(tmp_path)
    fp = q.ingest(fingerprint="A|x|1", occurred_at=_now())
    ok = q.transition(fp, to_status="triaged", actor="oncall",
                      note="looking", now=_now())
    assert ok is True
    r = _row(q, fp)
    assert r["status"] == "triaged"
    assert r["triaged_at"] is not None
    logs = [l for l in _logs(q, fp) if l["actor"] == "oncall"]
    assert len(logs) == 1
    assert logs[0]["from_status"] == "new"
    assert logs[0]["to_status"] == "triaged"
    assert logs[0]["note"] == "looking"
    assert logs[0]["transitioned_at"] is not None


def test_timestamp_columns_per_status(tmp_path):
    q = _open(tmp_path)
    fp = q.ingest(fingerprint="B|x|1", occurred_at=_now())
    q.transition(fp, to_status="triaged", actor="t", now=_now())
    q.transition(fp, to_status="approved", actor="t", now=_now())
    q.transition(fp, to_status="patched", actor="t", now=_now())
    r = _row(q, fp)
    assert r["status"] == "patched"
    assert r["triaged_at"] is not None
    assert r["approved_at"] is not None
    assert r["patched_at"] is not None


def test_invalid_transition_rejected_and_writes_nothing(tmp_path):
    q = _open(tmp_path)
    fp = q.ingest(fingerprint="C|x|1", occurred_at=_now())
    logs_before = len(_logs(q, fp))
    # new -> approved is NOT a valid edge (must go through triaged)
    ok = q.transition(fp, to_status="approved", actor="t", now=_now())
    assert ok is False
    r = _row(q, fp)
    assert r["status"] == "new"  # unchanged
    assert r["approved_at"] is None
    assert len(_logs(q, fp)) == logs_before  # nothing logged


def test_self_transition_rejected(tmp_path):
    q = _open(tmp_path)
    fp = q.ingest(fingerprint="S|x|1", occurred_at=_now())
    ok = q.transition(fp, to_status="new", actor="t", now=_now())
    assert ok is False


def test_let_cool_sets_cooldown(tmp_path):
    q = _open(tmp_path)
    fp = q.ingest(fingerprint="D|x|1", occurred_at=_now())
    now = _now()
    ok = q.let_cool(fp, actor="t", note="defer", now=now)
    assert ok is True
    r = _row(q, fp)
    from swarph_triage.priority import _to_epoch
    expected = now + timedelta(days=q.config["cooldown_default_days"])
    assert _to_epoch(r["cooldown_until"]) == _to_epoch(expected)


def test_reopen_from_terminal(tmp_path):
    q = _open(tmp_path)
    fp = q.ingest(fingerprint="E|x|1", occurred_at=_now())
    q.transition(fp, to_status="wontfix", actor="t", now=_now())
    assert _row(q, fp)["status"] == "wontfix"
    ok = q.reopen(fp, actor="human", note="actually it matters", now=_now())
    assert ok is True
    r = _row(q, fp)
    assert r["status"] == "new"
    # reopen does NOT set the regression flag (distinct from resurrect)
    assert r["regression"] == 0
    logs = [l for l in _logs(q, fp) if l["actor"] == "human"]
    assert len(logs) == 1
    assert logs[0]["from_status"] == "wontfix"
    assert logs[0]["to_status"] == "new"


def test_reopen_from_non_terminal_rejected(tmp_path):
    q = _open(tmp_path)
    fp = q.ingest(fingerprint="F|x|1", occurred_at=_now())
    # status is 'new' (non-terminal) -> reopen is a no-op/False
    ok = q.reopen(fp, actor="h", now=_now())
    assert ok is False
    assert _row(q, fp)["status"] == "new"


def test_transition_missing_row(tmp_path):
    q = _open(tmp_path)
    assert q.transition(9999, to_status="triaged", actor="t") is False
