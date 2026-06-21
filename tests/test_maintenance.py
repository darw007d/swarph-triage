"""Task 5 — recompute_priorities / prune_occurrences / backlog_md."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import swarph_triage
from swarph_triage.schema import fingerprints, occurrences
from sqlalchemy import select, func, update


def _now() -> datetime:
    return datetime(2026, 6, 21, 12, 0, 0, tzinfo=timezone.utc)


def _open(tmp_path):
    return swarph_triage.open(f"sqlite:///{tmp_path/'t.db'}")


def test_recompute_priorities_delegates(tmp_path):
    q = _open(tmp_path)
    now = _now()
    a = q.ingest(fingerprint="A|x|1", severity="critical", occurred_at=now)
    b = q.ingest(fingerprint="B|y|2", severity="low", occurred_at=now)
    q.transition(b, to_status="wontfix", actor="t")
    # zero out
    with q.engine.begin() as conn:
        conn.execute(update(fingerprints).values(priority_score=0.0))
    n = q.recompute_priorities()
    assert n == 1  # only the non-terminal row
    with q.engine.begin() as conn:
        score_a = conn.execute(select(fingerprints.c.priority_score)
                               .where(fingerprints.c.id == a)).scalar()
    assert score_a > 0.0


def test_prune_occurrences(tmp_path):
    q = _open(tmp_path)
    now = _now()
    fp = q.ingest(fingerprint="P|x|1", occurred_at=now - timedelta(days=40))
    q.ingest(fingerprint="P|x|1", occurred_at=now)
    with q.engine.begin() as conn:
        before = conn.execute(select(func.count()).select_from(occurrences)).scalar()
    assert before == 2
    pruned = q.prune_occurrences(older_than_days=30)
    assert pruned == 1
    with q.engine.begin() as conn:
        after = conn.execute(select(func.count()).select_from(occurrences)).scalar()
    assert after == 1


def test_prune_occurrences_nothing_to_prune(tmp_path):
    q = _open(tmp_path)
    now = _now()
    q.ingest(fingerprint="Q|x|1", occurred_at=now)
    pruned = q.prune_occurrences(older_than_days=30)
    assert pruned == 0


def test_backlog_md_renders_table(tmp_path):
    q = _open(tmp_path)
    now = _now()
    q.ingest(fingerprint="BIG|x|1", severity="critical", occurred_at=now)
    q.ingest(fingerprint="SMALL|y|2", severity="low", occurred_at=now)
    md = q.backlog_md()
    assert isinstance(md, str)
    # markdown table header + separator row
    assert "|" in md
    assert "---" in md
    # both fingerprints present, with their pipes ESCAPED so the table can't shatter
    assert "BIG\\|x\\|1" in md
    assert "SMALL\\|y\\|2" in md
    assert "BIG|x|1" not in md  # raw (unescaped) form must NOT appear
    # table integrity: every data row has exactly 6 columns (7 unescaped pipes)
    data_rows = [ln for ln in md.splitlines()
                 if ln.startswith("| ") and "---" not in ln and "ID" not in ln]
    for ln in data_rows:
        unescaped_pipes = ln.replace("\\|", "").count("|")
        assert unescaped_pipes == 7, f"row shattered the table: {ln!r}"
    # deterministic: same call twice -> identical string
    assert md == q.backlog_md()
    # higher-priority row sorts above lower
    assert md.index("BIG\\|x\\|1") < md.index("SMALL\\|y\\|2")


def test_backlog_md_empty_queue(tmp_path):
    q = _open(tmp_path)
    md = q.backlog_md()
    assert isinstance(md, str)
    assert "|" in md  # still renders a header
