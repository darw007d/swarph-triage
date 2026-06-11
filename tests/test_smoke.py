"""Smoke tests — what's testable on the skeleton alone (no implementation yet).

These pass on the skeleton commit and serve as the floor for CI; real coverage
lands with each implementation commit.
"""

from __future__ import annotations


def test_imports():
    """Public API surface is importable + version string present."""
    import swarph_triage

    assert hasattr(swarph_triage, "__version__")
    assert swarph_triage.__version__.startswith("0.1.0")
    assert hasattr(swarph_triage, "open")
    assert hasattr(swarph_triage, "TriageQueue")
    assert hasattr(swarph_triage, "Status")
    assert hasattr(swarph_triage, "DEFAULT_CONFIG")


def test_default_config_has_all_documented_keys():
    """README documents 9 config keys; DEFAULT_CONFIG must match exactly."""
    from swarph_triage.config import DEFAULT_CONFIG

    expected = {
        "decay_half_life_hours",
        "severity_weights",
        "freq_curve",
        "freq_log_base",
        "actionability_floor",
        "regression_grace_hours",
        "cooldown_default_days",
        "priority_min",
        "priority_max",
    }
    assert set(DEFAULT_CONFIG.keys()) == expected


def test_load_config_overrides():
    """Overrides apply on top of defaults; non-overridden keys preserved."""
    from swarph_triage.config import DEFAULT_CONFIG, load_config

    cfg = load_config({"decay_half_life_hours": 72.0})
    assert cfg["decay_half_life_hours"] == 72.0
    assert cfg["priority_max"] == DEFAULT_CONFIG["priority_max"]


def test_state_machine_matrix_well_formed():
    """No state may transition to itself; terminal states have empty forward set."""
    from swarph_triage.state_machine import Status, VALID_TRANSITIONS, TERMINAL

    # every Status has an entry
    for s in Status:
        assert s in VALID_TRANSITIONS

    # no self-loops
    for s, targets in VALID_TRANSITIONS.items():
        assert s not in targets, f"self-loop on {s}"

    # terminals are empty
    for t in TERMINAL:
        assert VALID_TRANSITIONS[t] == set()


def test_can_transition_known_edges():
    """A handful of explicit edges as a sanity check."""
    from swarph_triage.state_machine import Status, can_transition

    assert can_transition(Status.NEW, Status.TRIAGED)
    assert can_transition(Status.TRIAGED, Status.APPROVED)
    assert can_transition(Status.APPROVED, Status.PATCHED)
    assert not can_transition(Status.PATCHED, Status.NEW)  # via reopen() only
    assert not can_transition(Status.NEW, Status.NEW)


def test_schema_tables_present():
    """Schema metadata declares the 3 documented tables."""
    from swarph_triage.schema import metadata

    expected = {
        "swarph_triage_fingerprints",
        "swarph_triage_occurrences",
        "swarph_triage_state_log",
    }
    assert expected.issubset(set(metadata.tables.keys()))


def test_open_creates_tables_against_sqlite():
    """End-to-end smoke: open against an in-memory sqlite, tables exist."""
    import swarph_triage
    from sqlalchemy import inspect

    q = swarph_triage.open("sqlite:///:memory:")
    inspector = inspect(q.engine)
    tables = set(inspector.get_table_names())
    assert "swarph_triage_fingerprints" in tables
    assert "swarph_triage_occurrences" in tables
    assert "swarph_triage_state_log" in tables
