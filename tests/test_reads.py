"""Task 4 — queue reads: list / show / stats / history."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import swarph_triage


def _now() -> datetime:
    return datetime(2026, 6, 21, 12, 0, 0, tzinfo=timezone.utc)


def _open(tmp_path):
    return swarph_triage.open(f"sqlite:///{tmp_path/'t.db'}")


def _seed(tmp_path):
    q = _open(tmp_path)
    now = _now()
    # higher severity + count -> higher priority
    big = q.ingest(fingerprint="BIG|x|1", severity="critical", occurred_at=now)
    for _ in range(5):
        q.ingest(fingerprint="BIG|x|1", severity="critical",
                 occurred_at=now + timedelta(minutes=1))
    small = q.ingest(fingerprint="SMALL|y|2", severity="low", occurred_at=now)
    return q, big, small


def test_list_ordered_by_priority_desc(tmp_path):
    q, big, small = _seed(tmp_path)
    rows = q.list()
    ids = [r["id"] for r in rows]
    assert ids.index(big) < ids.index(small)
    # rows are plain dicts
    assert isinstance(rows[0], dict)
    assert rows[0]["priority_score"] >= rows[-1]["priority_score"]


def test_list_status_filter(tmp_path):
    q, big, small = _seed(tmp_path)
    q.transition(big, to_status="wontfix", actor="t")
    new_rows = q.list(status="new")
    assert all(r["status"] == "new" for r in new_rows)
    assert big not in [r["id"] for r in new_rows]
    wf = q.list(status="wontfix")
    assert [r["id"] for r in wf] == [big]


def test_list_pagination(tmp_path):
    q = _open(tmp_path)
    now = _now()
    ids = []
    for i in range(5):
        ids.append(q.ingest(fingerprint=f"P|{i}", severity="medium", occurred_at=now))
    page1 = q.list(limit=2, offset=0)
    page2 = q.list(limit=2, offset=2)
    assert len(page1) == 2
    assert len(page2) == 2
    assert {r["id"] for r in page1}.isdisjoint({r["id"] for r in page2})


def test_show_includes_history(tmp_path):
    q, big, small = _seed(tmp_path)
    q.transition(big, to_status="triaged", actor="oncall", note="hi")
    out = q.show(big, include_history=True)
    assert out["id"] == big
    assert out["fingerprint"] == "BIG|x|1"
    assert "occurrences" in out
    assert len(out["occurrences"]) >= 1
    assert "history" in out
    assert any(h["to_status"] == "triaged" for h in out["history"])


def test_show_without_history(tmp_path):
    q, big, small = _seed(tmp_path)
    out = q.show(big, include_history=False)
    assert out["id"] == big
    assert out.get("history") in (None, [])


def test_show_missing_returns_empty(tmp_path):
    q = _open(tmp_path)
    assert q.show(9999) in (None, {})


def test_stats(tmp_path):
    q, big, small = _seed(tmp_path)
    q.transition(small, to_status="triaged", actor="t")
    s = q.stats()
    assert s["by_status"]["new"] == 1
    assert s["by_status"]["triaged"] == 1
    assert s["total"] == 2
    assert "regression_count" in s
    assert s["regression_count"] == 0
    assert "oldest_new_age_hours" in s


def test_stats_regression_count(tmp_path):
    q = _open(tmp_path)
    t0 = _now()
    fp = q.ingest(fingerprint="RG|x|1", occurred_at=t0)
    from swarph_triage.schema import fingerprints
    from sqlalchemy import update
    with q.engine.begin() as conn:
        conn.execute(update(fingerprints).where(fingerprints.c.id == fp)
                     .values(status="patched", patched_at=t0))
    q.ingest(fingerprint="RG|x|1", occurred_at=t0 + timedelta(hours=2))
    s = q.stats()
    assert s["regression_count"] == 1


def test_history_oldest_first(tmp_path):
    q = _open(tmp_path)
    now = _now()
    fp = q.ingest(fingerprint="H|x|1", occurred_at=now)
    q.transition(fp, to_status="triaged", actor="t", now=now + timedelta(hours=1))
    q.transition(fp, to_status="approved", actor="t", now=now + timedelta(hours=2))
    hist = q.history(fp)
    statuses = [h["to_status"] for h in hist]
    # ingest logs 'new', then triaged, then approved — oldest first
    assert statuses == ["new", "triaged", "approved"]
    assert isinstance(hist[0], dict)
