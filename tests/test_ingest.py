"""Task 2 — queue.ingest UPSERT + occurrence append + regression-resurrect."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import swarph_triage
from swarph_triage.regression import is_regression, resurrect
from swarph_triage.schema import fingerprints, occurrences, state_log
from sqlalchemy import select, func, update


def _now() -> datetime:
    return datetime(2026, 6, 21, 12, 0, 0, tzinfo=timezone.utc)


def _open(tmp_path):
    return swarph_triage.open(f"sqlite:///{tmp_path/'t.db'}")


def _force_patched(q, fp_id, patched_at):
    """Set a row to patched directly (transition lands in Task 3)."""
    with q.engine.begin() as conn:
        conn.execute(update(fingerprints)
                     .where(fingerprints.c.id == fp_id)
                     .values(status="patched", patched_at=patched_at))


def _row(q, fp_id) -> dict:
    with q.engine.begin() as conn:
        r = conn.execute(
            select(fingerprints).where(fingerprints.c.id == fp_id)
        ).mappings().one()
    return dict(r)


def test_first_ingest_inserts(tmp_path):
    q = _open(tmp_path)
    now = _now()
    fp_id = q.ingest(fingerprint="NPE|auth.py|login", severity="high",
                     actionability=0.7, occurred_at=now)
    assert isinstance(fp_id, int)
    r = _row(q, fp_id)
    assert r["fingerprint"] == "NPE|auth.py|login"
    assert r["count_total"] == 1
    assert r["count_24h"] == 1
    assert r["status"] == "new"
    assert r["severity"] == "high"
    # first_seen == last_seen == now
    from swarph_triage.priority import _to_epoch
    assert _to_epoch(r["first_seen"]) == _to_epoch(now)
    assert _to_epoch(r["last_seen"]) == _to_epoch(now)
    # one occurrence row
    with q.engine.begin() as conn:
        n = conn.execute(select(func.count()).select_from(occurrences)
                         .where(occurrences.c.fingerprint_id == fp_id)).scalar()
    assert n == 1
    # priority recomputed on ingest
    assert r["priority_score"] > 0.0


def test_second_ingest_upserts(tmp_path):
    q = _open(tmp_path)
    t0 = _now()
    t1 = t0 + timedelta(hours=2)
    fp_id = q.ingest(fingerprint="E|x|1", severity="medium", occurred_at=t0)
    fp_id2 = q.ingest(fingerprint="E|x|1", severity="medium", occurred_at=t1)
    assert fp_id == fp_id2
    r = _row(q, fp_id)
    assert r["count_total"] == 2
    assert r["count_24h"] == 2
    from swarph_triage.priority import _to_epoch
    assert _to_epoch(r["last_seen"]) == _to_epoch(t1)
    assert _to_epoch(r["first_seen"]) == _to_epoch(t0)
    with q.engine.begin() as conn:
        n = conn.execute(select(func.count()).select_from(occurrences)
                         .where(occurrences.c.fingerprint_id == fp_id)).scalar()
    assert n == 2


def test_count_24h_window(tmp_path):
    """Occurrences older than 24h from the latest occurred_at don't count_24h."""
    q = _open(tmp_path)
    t_old = _now() - timedelta(hours=48)
    t_new = _now()
    fp_id = q.ingest(fingerprint="W|x|1", occurred_at=t_old)
    q.ingest(fingerprint="W|x|1", occurred_at=t_new)
    r = _row(q, fp_id)
    assert r["count_total"] == 2
    assert r["count_24h"] == 1  # only the recent one


def test_is_regression_within_grace(tmp_path):
    cfg = swarph_triage.load_config()  # regression_grace_hours = 24
    patched = _now()
    row = {"status": "patched", "patched_at": patched}
    # reappears 5h after patch -> within grace -> regression
    assert is_regression(row, occurred_at=patched + timedelta(hours=5), config=cfg)
    # reappears 30h after patch -> outside grace -> NOT regression
    assert not is_regression(row, occurred_at=patched + timedelta(hours=30), config=cfg)


def test_ingest_resurrects_patched_within_grace(tmp_path):
    q = _open(tmp_path)
    t0 = _now()
    fp_id = q.ingest(fingerprint="R|x|1", occurred_at=t0)
    _force_patched(q, fp_id, t0)
    assert _row(q, fp_id)["status"] == "patched"

    # reappears within grace -> resurrect
    q.ingest(fingerprint="R|x|1", occurred_at=t0 + timedelta(hours=3))
    r = _row(q, fp_id)
    assert r["status"] == "new"
    assert r["regression"] == 1
    # a state_log row with actor 'ingest' for the patched->new move
    with q.engine.begin() as conn:
        logs = conn.execute(
            select(state_log).where(state_log.c.fingerprint_id == fp_id)
        ).mappings().all()
    assert any(l["from_status"] == "patched" and l["to_status"] == "new"
               and l["actor"] == "ingest" for l in logs)


def test_ingest_does_not_resurrect_after_grace(tmp_path):
    q = _open(tmp_path)
    t0 = _now()
    fp_id = q.ingest(fingerprint="N|x|1", occurred_at=t0)
    _force_patched(q, fp_id, t0)

    # reappears AFTER grace -> stays patched, no regression flag
    q.ingest(fingerprint="N|x|1", occurred_at=t0 + timedelta(hours=48))
    r = _row(q, fp_id)
    assert r["status"] == "patched"
    assert r["regression"] == 0


def test_resurrect_direct(tmp_path):
    q = _open(tmp_path)
    t0 = _now()
    fp_id = q.ingest(fingerprint="D|x|1", occurred_at=t0)
    _force_patched(q, fp_id, t0)
    ok = resurrect(q, fp_id, note="manual regression")
    assert ok is True
    r = _row(q, fp_id)
    assert r["status"] == "new"
    assert r["regression"] == 1
