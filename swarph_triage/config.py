"""Calibration table — every tunable lives here.

DSPy-style retunes / per-consumer overrides go in here, not in worker code.
Pass overrides via ``swarph_triage.open(..., config={...})``.
"""

from __future__ import annotations

from typing import Any, Mapping

DEFAULT_CONFIG: dict[str, Any] = {
    # ─── priority decay ───
    # Used in priority.compute(): score *= exp(-hours_since_last_seen / half_life).
    # Tune to ingest cadence: 6h for hourly cron, 48–72h for daily refresh.
    "decay_half_life_hours": 6.0,

    # ─── severity → weight ───
    # Map your severity labels to multipliers. Unknown labels fall back to 0.5.
    "severity_weights": {
        "critical": 1.0,
        "high": 0.7,
        "medium": 0.5,
        "low": 0.3,
    },

    # ─── frequency curve ───
    # "log" → log_base(1 + freq). "linear" → freq. "sqrt" → sqrt(freq).
    # log is the production-tested default; whales don't drown fresh items.
    "freq_curve": "log",
    "freq_log_base": 10,

    # ─── actionability ───
    # Floor on the multiplier so nothing is truly zero (small items still
    # accumulate via the freq term and bubble up over time).
    "actionability_floor": 0.1,

    # ─── regression detector ───
    # After a `patched_at` timestamp, a new occurrence within this window
    # resurrects the row to `new` + sets regression=1. Default: 24h.
    "regression_grace_hours": 24,

    # ─── cooldown semantics ───
    # When a row is sent to `let_cool`, cooldown_until = now + N days.
    # Priority ramps DURING the cooldown window — 0 at cooldown-start, linearly
    # back to full at expiry (not "after"); see priority.compute's cooldown ramp.
    "cooldown_default_days": 14,

    # ─── normalization ───
    "priority_min": 0.0,
    "priority_max": 100.0,
}


def load_config(overrides: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Merge ``overrides`` shallow-on-top-of-DEFAULT_CONFIG.

    Nested dicts (e.g. ``severity_weights``) are replaced wholesale, not merged.
    If you need partial-merge for a nested dict, pass the full merged dict.
    """
    cfg: dict[str, Any] = {**DEFAULT_CONFIG}
    if overrides:
        cfg.update(overrides)
    return cfg
