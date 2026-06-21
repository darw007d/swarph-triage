"""FastAPI APIRouter factory — JSON only, no HTML.

Templates / HTMX surface stays consumer-side; this module exposes the data
endpoints the consumer's UI binds against.

Optional install: ``pip install swarph-triage[fastapi]``
"""

from __future__ import annotations

from typing import Any, Optional


def build_router(queue) -> Any:
    """Return a FastAPI ``APIRouter`` mountable into the consumer's app.

    Routes:

        GET  /list?status=...&limit=...&offset=...
        GET  /stats
        GET  /show/{fp_id}
        POST /transition/{fp_id}   body: {to_status, actor, note?}
    """
    from fastapi import APIRouter, Body

    router = APIRouter()

    @router.get("/list")
    def list_rows(status: Optional[str] = None, limit: int = 50, offset: int = 0):
        return queue.list(status=status, limit=limit, offset=offset)

    @router.get("/stats")
    def stats():
        return queue.stats()

    @router.get("/show/{fp_id}")
    def show(fp_id: int):
        return queue.show(fp_id)

    @router.post("/transition/{fp_id}")
    def transition(fp_id: int, body: dict = Body(...)):
        from fastapi import HTTPException
        # Auth is the consumer's responsibility (mount this router behind your
        # own auth middleware). Validate the required field → 422, not a 500.
        to_status = body.get("to_status")
        if not to_status:
            raise HTTPException(status_code=422, detail="to_status is required")
        ok = queue.transition(
            fp_id,
            to_status=to_status,
            actor=body.get("actor", "api"),
            note=body.get("note", ""),
        )
        return {"ok": ok}

    return router
