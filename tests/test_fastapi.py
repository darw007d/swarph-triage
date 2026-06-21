"""Task 6 — fastapi.build_router. Skipped if fastapi is not installed."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

pytest.importorskip("fastapi")

import swarph_triage
from swarph_triage.fastapi import build_router


def _now() -> datetime:
    return datetime(2026, 6, 21, 12, 0, 0, tzinfo=timezone.utc)


def _client(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    q = swarph_triage.open(f"sqlite:///{tmp_path/'t.db'}")
    app = FastAPI()
    app.include_router(build_router(q), prefix="/triage")
    return q, TestClient(app)


def test_router_is_apirouter():
    from fastapi import APIRouter

    q = swarph_triage.open("sqlite:///:memory:")
    assert isinstance(build_router(q), APIRouter)


def test_list_endpoint(tmp_path):
    q, client = _client(tmp_path)
    q.ingest(fingerprint="A|x|1", severity="critical", occurred_at=_now())
    r = client.get("/triage/list")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert data[0]["fingerprint"] == "A|x|1"


def test_list_endpoint_status_filter(tmp_path):
    q, client = _client(tmp_path)
    fp = q.ingest(fingerprint="A|x|1", occurred_at=_now())
    q.transition(fp, to_status="wontfix", actor="t")
    r = client.get("/triage/list", params={"status": "new"})
    assert r.status_code == 200
    assert r.json() == []


def test_show_endpoint(tmp_path):
    q, client = _client(tmp_path)
    fp = q.ingest(fingerprint="A|x|1", occurred_at=_now())
    r = client.get(f"/triage/show/{fp}")
    assert r.status_code == 200
    assert r.json()["id"] == fp


def test_stats_endpoint(tmp_path):
    q, client = _client(tmp_path)
    q.ingest(fingerprint="A|x|1", occurred_at=_now())
    r = client.get("/triage/stats")
    assert r.status_code == 200
    assert r.json()["total"] == 1


def test_transition_endpoint(tmp_path):
    q, client = _client(tmp_path)
    fp = q.ingest(fingerprint="A|x|1", occurred_at=_now())
    r = client.post(f"/triage/transition/{fp}",
                    json={"to_status": "triaged", "actor": "api", "note": "go"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert q.show(fp)["status"] == "triaged"


def test_transition_endpoint_invalid(tmp_path):
    q, client = _client(tmp_path)
    fp = q.ingest(fingerprint="A|x|1", occurred_at=_now())
    # new -> approved invalid
    r = client.post(f"/triage/transition/{fp}",
                    json={"to_status": "approved", "actor": "api"})
    assert r.status_code == 200
    assert r.json()["ok"] is False
