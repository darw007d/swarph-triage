"""Task 7 — coverage sweep: empty-queue, terminal guards, backend parametrization."""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

import swarph_triage


def _now() -> datetime:
    return datetime(2026, 6, 21, 12, 0, 0, tzinfo=timezone.utc)


# ── backend parametrization: sqlite always, postgres if reachable ──────────────
def _backends(tmp_path):
    urls = [f"sqlite:///{tmp_path/'t.db'}"]
    pg = os.environ.get("SWARPH_TRIAGE_TEST_PG_URL")
    if pg:
        urls.append(pg)
    return urls


@pytest.fixture(params=["sqlite", "pg"])
def queue(request, tmp_path):
    if request.param == "sqlite":
        return swarph_triage.open(f"sqlite:///{tmp_path/'t.db'}")
    pg = os.environ.get("SWARPH_TRIAGE_TEST_PG_URL")
    if not pg:
        pytest.skip("no SWARPH_TRIAGE_TEST_PG_URL — postgres backend unavailable")
    # Unique schema-less throwaway: caller is responsible for a clean test DB.
    return swarph_triage.open(pg)


def test_empty_queue_list(queue):
    assert queue.list() == []


def test_empty_queue_stats(queue):
    s = queue.stats()
    assert s["total"] == 0
    assert s["by_status"] == {}
    assert s["regression_count"] == 0
    assert s["oldest_new_age_hours"] is None


def test_empty_queue_backlog(queue):
    md = queue.backlog_md()
    assert isinstance(md, str)
    assert "swarph-triage backlog" in md


def test_terminal_guard_no_forward_from_patched(queue):
    fp = queue.ingest(fingerprint="T|x|1", occurred_at=_now())
    queue.transition(fp, to_status="triaged", actor="t")
    queue.transition(fp, to_status="approved", actor="t")
    queue.transition(fp, to_status="patched", actor="t")
    # patched is terminal — no forward edge allowed.
    assert queue.transition(fp, to_status="triaged", actor="t") is False
    assert queue.transition(fp, to_status="approved", actor="t") is False
    assert queue.show(fp)["status"] == "patched"


def test_terminal_guard_reopen_only_path_out(queue):
    fp = queue.ingest(fingerprint="T2|x|1", occurred_at=_now())
    queue.transition(fp, to_status="wontfix", actor="t")
    # can't transition forward, but reopen works.
    assert queue.transition(fp, to_status="triaged", actor="t") is False
    assert queue.reopen(fp, actor="h") is True
    assert queue.show(fp)["status"] == "new"


def test_show_missing_on_backend(queue):
    assert queue.show(123456) == {}


def test_history_empty_on_missing(queue):
    assert queue.history(123456) == []
