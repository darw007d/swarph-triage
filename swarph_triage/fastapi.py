"""FastAPI APIRouter factory — JSON only, no HTML.

Templates / HTMX surface stays consumer-side; this module exposes the data
endpoints + SSE stream the consumer's UI binds against.

Optional install: ``pip install swarph-triage[fastapi]``
"""

from __future__ import annotations

from typing import Any  # noqa: F401  — used by future signature additions


def build_router(queue) -> Any:
    """Stub — return a FastAPI APIRouter mountable into the consumer's app.

    Routes (planned):

        GET  /list?status=...&limit=...&offset=...
        GET  /stats
        GET  /show/{fp_id}
        POST /{fp_id}/approve
        POST /{fp_id}/wontfix
        POST /{fp_id}/escalate
        POST /{fp_id}/reopen
        GET  /events  (SSE — polls state_log, emits transitions)
    """
    raise NotImplementedError(
        "fastapi.build_router — implementation lands with the routes commit"
    )
