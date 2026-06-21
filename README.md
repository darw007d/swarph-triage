# swarph-triage

> Generalizable ranked-queue triage primitive — fingerprint, priority, state machine, regression detector. Backend-agnostic via SQLAlchemy Core (sqlite + postgres).

**Status:** ✅ 0.1.0 — functional. Public API, priority formula, state machine, regression detector, CLI, and FastAPI router are implemented and tested (sqlite + postgres via SQLAlchemy Core).

Extracted from a production **error-triage** system (scan logs → fingerprint → prioritize → work the backlog down) and generalized: the same ranked-dedup-queue pattern fits any high-volume stream of observations that should collapse into prioritized, dispositionable rows.

## The pattern

A ranked queue where:

1. **Many concrete observations collapse to one logical row** via a `fingerprint_fn`. (Canonical case — error triage: 47 near-identical error log lines → 1 fingerprint with `count=47`. The pattern generalizes to any stream where many raw events map to one actionable unit.)
2. **Items rank by `severity × log(1+freq) × decay(age) × actionability`** — log on freq stops whales drowning fresh items, exp-decay on age makes hot items rise. All coefficients live in a calibration table (config-driven, not hardcoded).
3. **A small explicit state machine** (`new → triaged → approved → patched`, with branches to `wontfix` and `needs_review`) — every transition logged to `state_log`, no implicit "kinda done."
4. **A regression detector** — if a fingerprint with `status='patched'` gets a new occurrence within `regression_grace_hours`, resurrect to `new` with `regression=1`. Accepted dispositions don't silently mask returning problems.
5. **Cooldown semantics** — a `cooldown_until` timestamp on `let_cool` dispositions. The priority calc ramps back from zero as cooldown expires, so a deliberately-deferred item doesn't immediately re-surface.

## Public API surface (planned)

```python
from swarph_triage import open as open_triage

q = open_triage(
    "postgresql://user:pass@host:5433/mydb",  # or sqlite:///path.db
    config={"decay_half_life_hours": 72.0},
    proposer_fn=my_proposer,  # optional, domain-specific
)

# ingest one observation
fp_id = q.ingest(
    fingerprint="NullPointerError|auth.py|login",
    severity="high",
    actionability=0.7,
    context={"module": "auth", "first_seen": "..."},
)

# disposition
q.transition(fp_id, to_status="approved", actor="oncall", note="fix queued")

# top-N for the UI
for row in q.list(limit=20):
    print(row["fingerprint"], row["priority_score"], row["status"])
```

CLI:
```
swarph-triage list
swarph-triage show <id>
swarph-triage approve <id>
swarph-triage wontfix <id> "reason"
swarph-triage stats
swarph-triage backlog          # writes markdown snapshot
swarph-triage history <id>
```

FastAPI routes (optional install: `pip install swarph-triage[fastapi]`):
```python
from fastapi import FastAPI
from swarph_triage.fastapi import build_router

app = FastAPI()
app.include_router(build_router(q), prefix="/triage")
# → /list, /stats, /show/{id}, /{id}/{approve|wontfix|escalate|reopen}, /events (SSE)
```

## Configuration

Everything tunable lives in `swarph_triage.config.DEFAULT_CONFIG` — override per-consumer at `open()`:

```python
DEFAULT_CONFIG = {
    "decay_half_life_hours": 6.0,                                      # 6h for hourly, 72h for daily
    "severity_weights": {"critical": 1.0, "high": 0.7, "medium": 0.5, "low": 0.3},
    "freq_curve": "log",                                               # "log" | "linear" | "sqrt"
    "freq_log_base": 10,
    "actionability_floor": 0.1,
    "regression_grace_hours": 24,
    "cooldown_default_days": 14,
    "priority_min": 0.0,
    "priority_max": 100.0,
}
```

## Layout

```
swarph_triage/
  __init__.py        — public API surface
  config.py          — DEFAULT_CONFIG + load/merge helpers
  schema.py          — SQLAlchemy Core table definitions (3 tables, 6 indexes)
  state_machine.py   — Status enum + valid transition matrix + side effects
  priority.py        — score formula + decay + recompute_all
  regression.py      — patched-then-reappearance detector
  queue.py           — TriageQueue main class (ingest, transition, list, show)
  cli.py             — argparse-driven CLI
  fastapi.py         — APIRouter factory (optional extra)
```

## License

MIT. Pierre Samson + Claude, co-authored — matching the `phawkes` / `fisherrao` / `tailcor` lineage.
