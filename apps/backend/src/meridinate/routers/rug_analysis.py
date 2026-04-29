"""
Rug Analysis Router — Run and view rug detection analysis reports.
"""

import asyncio

import aiosqlite
from fastapi import APIRouter, HTTPException

from meridinate import settings
from meridinate.observability import log_info

router = APIRouter()


@router.post("/api/rug-analysis/run", status_code=202)
async def run_rug_analysis():
    """Trigger rug analysis agent in background. Returns immediately."""
    from meridinate.services.rug_analysis_agent import run_rug_analysis

    async def _run():
        await asyncio.to_thread(run_rug_analysis)

    asyncio.create_task(_run())
    log_info("[RugAnalysis] Triggered")
    return {"status": "started"}


@router.get("/api/rug-analysis/reports")
async def get_reports(limit: int = 10):
    """Get recent rug analysis reports."""
    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("""
            SELECT id, tokens_analyzed, fake_count, real_count, unsure_count,
                   tool_calls, input_tokens, output_tokens, duration_seconds, generated_at
            FROM rug_analysis_reports
            ORDER BY generated_at DESC LIMIT ?
        """, (limit,))
        rows = [dict(r) for r in await cursor.fetchall()]
    return {"reports": rows}


@router.get("/api/rug-analysis/reports/{report_id}")
async def get_report(report_id: int):
    """Get full rug analysis report by ID."""
    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM rug_analysis_reports WHERE id = ?", (report_id,)
        )
        row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Report not found")
    return dict(row)
