"""Task 6 — CLI wiring. Drives main([...]) against a tmp-file DB."""

from __future__ import annotations

from datetime import datetime, timezone

import swarph_triage
from swarph_triage.cli import main


def _now() -> datetime:
    return datetime(2026, 6, 21, 12, 0, 0, tzinfo=timezone.utc)


def _seed(tmp_path):
    db = f"sqlite:///{tmp_path/'t.db'}"
    q = swarph_triage.open(db)
    fp = q.ingest(fingerprint="A|x|1", severity="critical", occurred_at=_now())
    return db, q, fp


def test_cli_requires_db(capsys):
    rc = main(["list"])
    assert rc == 2


def test_cli_list(tmp_path, capsys):
    db, q, fp = _seed(tmp_path)
    rc = main(["--db-url", db, "list"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "A|x|1" in out


def test_cli_stats(tmp_path, capsys):
    db, q, fp = _seed(tmp_path)
    rc = main(["--db-url", db, "stats"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "total" in out.lower() or "1" in out


def test_cli_show(tmp_path, capsys):
    db, q, fp = _seed(tmp_path)
    rc = main(["--db-url", db, "show", str(fp)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "A|x|1" in out


def test_cli_approve_drives_transition(tmp_path, capsys):
    db, q, fp = _seed(tmp_path)
    # approve needs triaged first; drive it
    q.transition(fp, to_status="triaged", actor="t")
    rc = main(["--db-url", db, "approve", str(fp), "lgtm"])
    assert rc == 0
    assert q.show(fp)["status"] == "approved"


def test_cli_wontfix(tmp_path, capsys):
    db, q, fp = _seed(tmp_path)
    rc = main(["--db-url", db, "wontfix", str(fp), "noise"])
    assert rc == 0
    assert q.show(fp)["status"] == "wontfix"


def test_cli_escalate(tmp_path, capsys):
    db, q, fp = _seed(tmp_path)
    rc = main(["--db-url", db, "escalate", str(fp)])
    assert rc == 0
    assert q.show(fp)["status"] == "needs_review"


def test_cli_reopen(tmp_path, capsys):
    db, q, fp = _seed(tmp_path)
    q.transition(fp, to_status="wontfix", actor="t")
    rc = main(["--db-url", db, "reopen", str(fp)])
    assert rc == 0
    assert q.show(fp)["status"] == "new"


def test_cli_history(tmp_path, capsys):
    db, q, fp = _seed(tmp_path)
    q.transition(fp, to_status="triaged", actor="t")
    rc = main(["--db-url", db, "history", str(fp)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "triaged" in out


def test_cli_backlog(tmp_path, capsys):
    db, q, fp = _seed(tmp_path)
    rc = main(["--db-url", db, "backlog"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "A\\|x\\|1" in out  # fingerprint pipes escaped in the markdown table


def test_cli_db_url_from_env(tmp_path, capsys, monkeypatch):
    db, q, fp = _seed(tmp_path)
    monkeypatch.setenv("SWARPH_TRIAGE_DB_URL", db)
    rc = main(["list"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "A|x|1" in out
