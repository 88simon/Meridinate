"""
Intel Recommendations API

Per-action review, approval, rejection, and reversion of Intel recommendations.
Also exposes the bot allowlist/denylist state and audit log.
"""

from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from meridinate.services.recommendation_executor import (
    approve_recommendation,
    reject_recommendation,
    revert_recommendation,
    get_recommendations,
    get_audit_log,
    get_bot_lists,
    ensure_tables,
)

router = APIRouter()


class RejectBody(BaseModel):
    reason: str = ""


@router.get("/api/intel/recommendations")
async def list_recommendations(
    status: Optional[str] = Query(None, description="Filter by status: proposed, active_for_bot, rejected, reverted, failed"),
    report_id: Optional[int] = Query(None, description="Filter by source report ID"),
    limit: int = Query(50, ge=1, le=200),
):
    """List Intel recommendations with optional filters."""
    recs = get_recommendations(status=status, report_id=report_id, limit=limit)
    # Count by status for the summary
    proposed = sum(1 for r in recs if r["status"] == "proposed")
    active = sum(1 for r in recs if r["status"] == "active_for_bot")
    return {
        "recommendations": recs,
        "counts": {"proposed": proposed, "active": active, "total": len(recs)},
    }


@router.post("/api/intel/recommendations/{rec_id}/approve")
async def approve(rec_id: int):
    """Approve a recommendation — applies immediately and makes bot-active."""
    return approve_recommendation(rec_id)


@router.post("/api/intel/recommendations/{rec_id}/reject")
async def reject(rec_id: int, body: RejectBody = RejectBody()):
    """Reject a recommendation — no system changes."""
    return reject_recommendation(rec_id, reason=body.reason)


@router.post("/api/intel/recommendations/{rec_id}/revert")
async def revert(rec_id: int):
    """Revert a previously approved recommendation."""
    return revert_recommendation(rec_id)


@router.get("/api/intel/audit-log")
async def audit_log(
    recommendation_id: Optional[int] = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    """Get the Intel audit log."""
    return {"log": get_audit_log(recommendation_id=recommendation_id, limit=limit)}


@router.get("/api/intel/bot-lists")
async def bot_lists():
    """Get current active bot allowlist and denylist."""
    return get_bot_lists()
