"""Task 1 — priority.compute + recompute_all.

Formula (from priority.py docstring + config):
    priority = severity_w * freq_curve(count_24h) * decay(hours_since_last_seen)
                 * max(actionability, actionability_floor)
clamped to [priority_min, priority_max]; cooldown ramps the score toward 0.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

from swarph_triage.config import load_config
from swarph_triage.priority import compute, recompute_all


def _now_dt() -> datetime:
    return datetime(2026, 6, 21, 12, 0, 0, tzinfo=timezone.utc)


def _now_ts() -> float:
    return _now_dt().timestamp()


def _row(**over) -> dict:
    base = {
        "severity": "high",
        "count_24h": 1,
        "last_seen": _now_dt(),
        "actionability": 1.0,
        "cooldown_until": None,
    }
    base.update(over)
    return base


def test_severity_weight_applied():
    cfg = load_config()
    now = _now_ts()
    hi = compute(_row(severity="high"), now_ts=now, config=cfg)
    crit = compute(_row(severity="critical"), now_ts=now, config=cfg)
    low = compute(_row(severity="low"), now_ts=now, config=cfg)
    # critical (1.0) > high (0.7) > low (0.3) for identical freq/recency.
    assert crit > hi > low


def test_unknown_severity_falls_back_to_half():
    cfg = load_config()
    now = _now_ts()
    unk = compute(_row(severity="bogus"), now_ts=now, config=cfg)
    med = compute(_row(severity="medium"), now_ts=now, config=cfg)
    # Unknown label falls back to 0.5, same as medium.
    assert unk == pytest.approx(med)


def test_higher_count_higher_score_but_log_not_linear():
    cfg = load_config()
    now = _now_ts()
    s1 = compute(_row(count_24h=1), now_ts=now, config=cfg)
    s2 = compute(_row(count_24h=2), now_ts=now, config=cfg)
    s10 = compute(_row(count_24h=10), now_ts=now, config=cfg)
    s100 = compute(_row(count_24h=100), now_ts=now, config=cfg)
    assert s100 > s10 > s2 > s1
    # Log curve: equal-sized count steps give diminishing increments (concave),
    # unlike a linear curve. The 1→2 step exceeds the much larger 10→100 step
    # measured per-unit; check concavity via the unit-step shrink.
    linear = compute(_row(count_24h=1), now_ts=now,
                     config=load_config({"freq_curve": "linear"}))
    linear2 = compute(_row(count_24h=2), now_ts=now,
                      config=load_config({"freq_curve": "linear"}))
    # On a linear curve the 1->2 jump is a fixed slope; on log it's smaller
    # relative to the absolute counts -> log compresses the high end.
    assert (s2 - s1) < (linear2 - linear)


def test_decay_half_life():
    cfg = load_config()  # decay_half_life_hours = 6.0
    now = _now_ts()
    fresh = compute(_row(last_seen=_now_dt()), now_ts=now, config=cfg)
    half_old = _now_dt() - timedelta(hours=cfg["decay_half_life_hours"])
    aged = compute(_row(last_seen=half_old), now_ts=now, config=cfg)
    # At exactly one half-life, the decay factor is ~0.5 of fresh.
    assert aged == pytest.approx(fresh * 0.5, rel=1e-6)


def test_actionability_floored():
    cfg = load_config()  # actionability_floor = 0.1
    now = _now_ts()
    below = compute(_row(actionability=0.0), now_ts=now, config=cfg)
    at_floor = compute(_row(actionability=cfg["actionability_floor"]), now_ts=now, config=cfg)
    # actionability below floor is treated as the floor.
    assert below == pytest.approx(at_floor)
    assert below > 0.0


def test_future_cooldown_ramps_toward_zero():
    cfg = load_config()
    now = _now_ts()
    no_cd = compute(_row(), now_ts=now, config=cfg)
    # Cooldown ends 10 days from now, started today -> early in the ramp -> near 0.
    cd_end = _now_dt() + timedelta(days=10)
    cooling = compute(_row(cooldown_until=cd_end), now_ts=now, config=cfg)
    assert cooling < no_cd
    assert cooling >= 0.0
    # Past cooldown does NOT suppress.
    past = _now_dt() - timedelta(days=1)
    expired = compute(_row(cooldown_until=past), now_ts=now, config=cfg)
    assert expired == pytest.approx(no_cd)


def test_clamped_to_range():
    # Tiny max forces the clamp regardless of the raw score magnitude.
    cfg = load_config({"priority_max": 0.5, "priority_min": 0.0})
    now = _now_ts()
    s = compute(_row(severity="critical", count_24h=10000), now_ts=now, config=cfg)
    assert s == pytest.approx(0.5)
    # priority_min floor: a near-zero raw score clamps up to min.
    cfg2 = load_config({"priority_min": 2.0, "priority_max": 100.0})
    tiny = compute(_row(severity="low", count_24h=0, actionability=0.0),
                   now_ts=now, config=cfg2)
    assert tiny == pytest.approx(2.0)


def test_deterministic_given_now_ts():
    cfg = load_config()
    now = _now_ts()
    a = compute(_row(count_24h=7), now_ts=now, config=cfg)
    b = compute(_row(count_24h=7), now_ts=now, config=cfg)
    assert a == b


def test_recompute_all_updates_non_terminal(tmp_path):
    """Direct-insert two rows (one terminal) and recompute. Self-contained:
    does not depend on ingest/transition (those are later tasks)."""
    import swarph_triage
    from sqlalchemy import insert
    from swarph_triage.schema import fingerprints

    db = f"sqlite:///{tmp_path/'t.db'}"
    q = swarph_triage.open(db)
    now = _now_dt()
    with q.engine.begin() as conn:
        r_active = conn.execute(insert(fingerprints).values(
            fingerprint="A|x|1", severity="critical", status="new",
            count_total=5, count_24h=5, first_seen=now, last_seen=now,
            actionability=1.0, priority_score=0.0,
        ))
        r_term = conn.execute(insert(fingerprints).values(
            fingerprint="B|y|2", severity="low", status="wontfix",
            count_total=1, count_24h=1, first_seen=now, last_seen=now,
            actionability=1.0, priority_score=0.0,
        ))
    id_active = r_active.inserted_primary_key[0]
    id_term = r_term.inserted_primary_key[0]

    n = recompute_all(q, now_ts=_now_ts())
    assert n == 1  # only the non-terminal row

    from sqlalchemy import select
    with q.engine.begin() as conn:
        scores = {
            row.id: row.priority_score
            for row in conn.execute(
                select(fingerprints.c.id, fingerprints.c.priority_score)
            )
        }
    assert scores[id_active] > 0.0
    assert scores[id_term] == 0.0
