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
    reclassify_recommendation,
    get_recommendations,
    get_audit_log,
    get_bot_lists,
    ensure_tables,
)

router = APIRouter()


class RejectBody(BaseModel):
    reason: str = ""


class ReclassifyBody(BaseModel):
    action_type: str
    reason: str = ""
    payload: dict = {}
    # Operator-feedback-loop fields. Category is a key from
    # override_analyst.OVERRIDE_CATEGORIES; the analyst uses it to anchor the
    # rule extraction. Note is an optional one-line clarification.
    operator_category: str = "other"
    operator_note: str = ""


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


@router.post("/api/intel/recommendations/{rec_id}/reclassify")
async def reclassify(rec_id: int, body: ReclassifyBody):
    """
    Override a misclassified recommendation. Marks the original 'overridden',
    creates a replacement with the chosen action, auto-approves it, and fires
    the Override Analyst to extract a rule for the next Intel run.
    """
    return reclassify_recommendation(
        rec_id,
        new_action_type=body.action_type,
        reason=body.reason,
        payload=body.payload,
        operator_category=body.operator_category,
        operator_note=body.operator_note,
    )


@router.get("/api/intel/override-categories")
async def override_categories():
    """Operator-facing dropdown options for the Reclassify form."""
    from meridinate.services.override_analyst import OVERRIDE_CATEGORIES
    return {"categories": OVERRIDE_CATEGORIES}


@router.get("/api/intel/agent-rules")
async def agent_rules(limit: int = Query(50, ge=1, le=200)):
    """Active operator-override rules. Useful for verifying what the Investigator will see next run."""
    from meridinate.services.override_analyst import get_active_rules
    return {"rules": get_active_rules(limit=limit)}


class WalletNoteBody(BaseModel):
    note: str = ""


@router.post("/api/wallets/{wallet_address}/promote-to-allowlist")
async def promote_to_allowlist(wallet_address: str, body: WalletNoteBody = WalletNoteBody()):
    """
    Direct WIR action: promote a wallet to the Intel Allowlist + auto-shadow it.
    Synthesises an Intel-style recommendation row + audit entry so the action
    has the same audit trail as Investigator-proposed allowlist additions.
    """
    from meridinate.services.recommendation_executor import (
        ensure_tables, ACTION_HANDLERS, _now, _log_audit,
    )
    import json as _json
    import sqlite3 as _sqlite3
    from meridinate import analyzed_tokens_db as _db

    ensure_tables()
    handler = ACTION_HANDLERS.get("add_bot_allowlist_wallet")
    if not handler:
        return {"success": False, "message": "Allowlist handler not registered"}

    now = _now()
    with _db.get_db_connection() as conn:
        conn.row_factory = _sqlite3.Row
        cursor = conn.execute(
            """INSERT INTO intel_recommendations
               (report_id, action_type, target_type, target_address, payload,
                reason, confidence, expected_bot_effect, status, created_at)
               VALUES (NULL, 'add_bot_allowlist_wallet', 'wallet', ?, ?, ?, 'high',
                       'Wallet auto-shadowed and counted as anti-rug confluence', 'proposed', ?)""",
            (
                wallet_address,
                _json.dumps({}),
                f"Operator promoted to allowlist via WIR: {body.note}".strip(),
                now,
            ),
        )
        rec_id = cursor.lastrowid
        rec = dict(conn.execute(
            "SELECT * FROM intel_recommendations WHERE id = ?", (rec_id,)
        ).fetchone())

        result = handler(conn, rec)
        if result["success"]:
            conn.execute(
                """UPDATE intel_recommendations
                   SET status = 'active_for_bot', approved_at = ?, applied_at = ?, revert_data = ?
                   WHERE id = ?""",
                (now, now, result.get("revert_data"), rec_id),
            )
            _log_audit(
                conn, rec_id, None, "add_bot_allowlist_wallet",
                wallet_address, "proposed", "active_for_bot",
                after_state=result.get("revert_data"),
                notes=f"WIR promote-to-allowlist: {result['message']}",
            )
        else:
            conn.execute(
                "UPDATE intel_recommendations SET status = 'failed' WHERE id = ?", (rec_id,)
            )

    return {"success": result["success"], "message": result["message"], "recommendation_id": rec_id}


@router.post("/api/wallets/{wallet_address}/queue-bot-probe")
async def queue_bot_probe(wallet_address: str):
    """
    Direct WIR action: enqueue a Bot Probe for this wallet. The probe runs when
    started from the Bot Probe page. Idempotent — duplicate queues are skipped.
    """
    from meridinate.services.recommendation_executor import _now
    from meridinate import analyzed_tokens_db as _db

    now = _now()
    with _db.get_db_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM bot_probe_runs WHERE wallet_address = ? AND status = 'queued'",
            (wallet_address,),
        ).fetchone()
        if existing:
            return {
                "success": True,
                "message": f"Bot Probe already queued for {wallet_address}",
                "run_id": existing[0],
            }
        cursor = conn.execute(
            """INSERT INTO bot_probe_runs (wallet_address, status, requested_at, requested_by)
               VALUES (?, 'queued', ?, 'wir_button')""",
            (wallet_address, now),
        )
        run_id = cursor.lastrowid

    return {
        "success": True,
        "message": f"Bot Probe queued for {wallet_address}",
        "run_id": run_id,
    }


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
