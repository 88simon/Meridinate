"""
Quick DD Router — On-demand token due diligence endpoints.
"""

import asyncio

from fastapi import APIRouter, Body
from pydantic import BaseModel

from meridinate import analyzed_tokens_db as db
from meridinate.observability import log_info

router = APIRouter()


class QuickDDRequest(BaseModel):
    token_address: str


@router.post("/api/quick-dd/run", status_code=202)
async def run_quick_dd(request: QuickDDRequest):
    """Trigger Quick DD pipeline in background. Returns immediately."""
    from meridinate.services.quick_dd import run_quick_dd, _dd_progress

    if _dd_progress["running"]:
        return {"status": "already_running", "token_address": _dd_progress["token_address"]}

    async def _run():
        await asyncio.to_thread(run_quick_dd, request.token_address)

    asyncio.create_task(_run())
    log_info(f"[QuickDD] Started for {request.token_address[:12]}...")
    return {"status": "started", "token_address": request.token_address}


@router.get("/api/quick-dd/progress")
async def get_dd_progress():
    """Get current Quick DD progress (lightweight, no DB query)."""
    from meridinate.services.quick_dd import get_dd_progress
    return get_dd_progress()


@router.get("/api/quick-dd/history")
async def get_dd_history(limit: int = 20):
    """Get recent Quick DD runs."""
    import aiosqlite
    from meridinate import settings

    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT id, token_address, token_id, token_name, token_symbol, "
            "market_cap_usd, clobr_score, lp_trust_score, credits_used, "
            "duration_seconds, started_at, completed_at "
            "FROM quick_dd_runs ORDER BY started_at DESC LIMIT ?",
            (limit,),
        )
        rows = [dict(r) for r in await cursor.fetchall()]

    return {"runs": rows, "count": len(rows)}


@router.get("/api/quick-dd/run/{run_id}")
async def get_dd_run(run_id: int):
    """Get full Quick DD report by run ID."""
    import aiosqlite
    from meridinate import settings

    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM quick_dd_runs WHERE id = ?", (run_id,)
        )
        row = await cursor.fetchone()

    if not row:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="DD run not found")

    return dict(row)
