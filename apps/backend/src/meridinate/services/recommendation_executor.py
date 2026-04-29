"""
Intel Recommendation Executor

Processes structured Intel recommendations through deterministic handlers.
Each action type has a named executor that validates, applies, logs, and
can revert changes. No freeform SQL — only constrained operations.

Tables managed:
  - intel_recommendations: lifecycle tracking for each recommendation
  - intel_audit_log: immutable record of every state change
  - intel_bot_allowlist: approved wallets for anti-rug confluence
  - intel_bot_denylist: wallets/clusters to filter out
"""

import json
import sqlite3
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Optional

from meridinate import analyzed_tokens_db as db
from meridinate.observability import log_info, log_error

CHICAGO_TZ = ZoneInfo("America/Chicago")


def _now() -> str:
    return datetime.now(CHICAGO_TZ).strftime("%Y-%m-%d %H:%M:%S %Z")


def ensure_tables():
    """Create recommendation tables if they don't exist."""
    with db.get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.executescript("""
            CREATE TABLE IF NOT EXISTS intel_recommendations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id INTEGER,
                action_type TEXT NOT NULL,
                target_type TEXT NOT NULL,
                target_address TEXT NOT NULL,
                payload TEXT,
                reason TEXT,
                confidence TEXT,
                expected_bot_effect TEXT,
                status TEXT NOT NULL DEFAULT 'proposed',
                created_at TEXT,
                approved_at TEXT,
                applied_at TEXT,
                reverted_at TEXT,
                rejected_at TEXT,
                revert_data TEXT
            );

            CREATE TABLE IF NOT EXISTS intel_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recommendation_id INTEGER,
                report_id INTEGER,
                action_type TEXT NOT NULL,
                target_address TEXT NOT NULL,
                old_status TEXT,
                new_status TEXT NOT NULL,
                before_state TEXT,
                after_state TEXT,
                performed_by TEXT DEFAULT 'simon',
                performed_at TEXT,
                notes TEXT
            );

            CREATE TABLE IF NOT EXISTS intel_bot_allowlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                wallet_address TEXT NOT NULL UNIQUE,
                reason TEXT,
                confidence TEXT,
                source_report_id INTEGER,
                source_recommendation_id INTEGER,
                added_at TEXT,
                active INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS intel_bot_denylist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                wallet_address TEXT NOT NULL UNIQUE,
                deny_type TEXT,
                reason TEXT,
                confidence TEXT,
                source_report_id INTEGER,
                source_recommendation_id INTEGER,
                added_at TEXT,
                active INTEGER NOT NULL DEFAULT 1
            );
        """)


def _log_audit(conn, rec_id: int, report_id: int, action_type: str,
               target: str, old_status: str, new_status: str,
               before_state: str = None, after_state: str = None,
               notes: str = None):
    """Write an immutable audit log entry."""
    conn.execute(
        """INSERT INTO intel_audit_log
           (recommendation_id, report_id, action_type, target_address,
            old_status, new_status, before_state, after_state,
            performed_by, performed_at, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'simon', ?, ?)""",
        (rec_id, report_id, action_type, target,
         old_status, new_status, before_state, after_state,
         _now(), notes),
    )


# ============================================================================
# Action Handlers — each returns {success, message, revert_data}
# ============================================================================

def _exec_add_bot_allowlist(conn, rec: Dict) -> Dict:
    target = rec["target_address"]
    # Capture before state
    row = conn.execute(
        "SELECT * FROM intel_bot_allowlist WHERE wallet_address = ?", (target,)
    ).fetchone()
    before = json.dumps(dict(row)) if row else None

    if row:
        conn.execute(
            "UPDATE intel_bot_allowlist SET active = 1, reason = ?, confidence = ?, "
            "source_report_id = ?, source_recommendation_id = ?, added_at = ? "
            "WHERE wallet_address = ?",
            (rec.get("reason"), rec.get("confidence"), rec.get("report_id"),
             rec["id"], _now(), target),
        )
    else:
        conn.execute(
            "INSERT INTO intel_bot_allowlist (wallet_address, reason, confidence, "
            "source_report_id, source_recommendation_id, added_at) VALUES (?, ?, ?, ?, ?, ?)",
            (target, rec.get("reason"), rec.get("confidence"),
             rec.get("report_id"), rec["id"], _now()),
        )

    # Also add an Intel-namespaced wallet tag
    conn.execute("DELETE FROM wallet_tags WHERE wallet_address = ? AND tag = 'Intel Allowlist'", (target,))
    conn.execute(
        "INSERT INTO wallet_tags (wallet_address, tag, tier, source) VALUES (?, 'Intel Allowlist', 2, 'intel')",
        (target,),
    )

    return {
        "success": True,
        "message": f"Added {target} to bot allowlist",
        "revert_data": json.dumps({"action": "remove_bot_allowlist_wallet", "before": before}),
    }


def _exec_remove_bot_allowlist(conn, rec: Dict) -> Dict:
    target = rec["target_address"]
    row = conn.execute(
        "SELECT * FROM intel_bot_allowlist WHERE wallet_address = ?", (target,)
    ).fetchone()
    before = json.dumps(dict(row)) if row else None

    if not row:
        return {"success": False, "message": f"Wallet {target} not on allowlist", "revert_data": None}

    conn.execute("UPDATE intel_bot_allowlist SET active = 0 WHERE wallet_address = ?", (target,))
    conn.execute("DELETE FROM wallet_tags WHERE wallet_address = ? AND tag = 'Intel Allowlist'", (target,))

    return {
        "success": True,
        "message": f"Removed {target} from bot allowlist",
        "revert_data": json.dumps({"action": "add_bot_allowlist_wallet", "before": before}),
    }


def _exec_add_bot_denylist(conn, rec: Dict) -> Dict:
    target = rec["target_address"]
    payload = json.loads(rec.get("payload") or "{}")
    deny_type = payload.get("deny_type", "toxic_flow")

    row = conn.execute(
        "SELECT * FROM intel_bot_denylist WHERE wallet_address = ?", (target,)
    ).fetchone()
    before = json.dumps(dict(row)) if row else None

    if row:
        conn.execute(
            "UPDATE intel_bot_denylist SET active = 1, deny_type = ?, reason = ?, confidence = ?, "
            "source_report_id = ?, source_recommendation_id = ?, added_at = ? "
            "WHERE wallet_address = ?",
            (deny_type, rec.get("reason"), rec.get("confidence"),
             rec.get("report_id"), rec["id"], _now(), target),
        )
    else:
        conn.execute(
            "INSERT INTO intel_bot_denylist (wallet_address, deny_type, reason, confidence, "
            "source_report_id, source_recommendation_id, added_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (target, deny_type, rec.get("reason"), rec.get("confidence"),
             rec.get("report_id"), rec["id"], _now()),
        )

    conn.execute("DELETE FROM wallet_tags WHERE wallet_address = ? AND tag = 'Intel Denylist'", (target,))
    conn.execute(
        "INSERT INTO wallet_tags (wallet_address, tag, tier, source) VALUES (?, 'Intel Denylist', 2, 'intel')",
        (target,),
    )

    return {
        "success": True,
        "message": f"Added {target} to bot denylist ({deny_type})",
        "revert_data": json.dumps({"action": "remove_bot_denylist_wallet", "before": before}),
    }


def _exec_remove_bot_denylist(conn, rec: Dict) -> Dict:
    target = rec["target_address"]
    row = conn.execute(
        "SELECT * FROM intel_bot_denylist WHERE wallet_address = ?", (target,)
    ).fetchone()
    before = json.dumps(dict(row)) if row else None

    if not row:
        return {"success": False, "message": f"Wallet {target} not on denylist", "revert_data": None}

    conn.execute("UPDATE intel_bot_denylist SET active = 0 WHERE wallet_address = ?", (target,))
    conn.execute("DELETE FROM wallet_tags WHERE wallet_address = ? AND tag = 'Intel Denylist'", (target,))

    return {
        "success": True,
        "message": f"Removed {target} from bot denylist",
        "revert_data": json.dumps({"action": "add_bot_denylist_wallet", "before": before}),
    }


def _exec_add_watch_wallet(conn, rec: Dict) -> Dict:
    target = rec["target_address"]
    conn.execute("DELETE FROM wallet_tags WHERE wallet_address = ? AND tag = 'Watchlist'", (target,))
    conn.execute(
        "INSERT INTO wallet_tags (wallet_address, tag, tier, source) VALUES (?, 'Watchlist', 3, 'intel')",
        (target,),
    )
    return {
        "success": True,
        "message": f"Added {target} to watchlist",
        "revert_data": json.dumps({"action": "remove_watch_wallet"}),
    }


def _exec_remove_watch_wallet(conn, rec: Dict) -> Dict:
    target = rec["target_address"]
    conn.execute("DELETE FROM wallet_tags WHERE wallet_address = ? AND tag = 'Watchlist' AND source = 'intel'", (target,))
    return {
        "success": True,
        "message": f"Removed {target} from watchlist",
        "revert_data": json.dumps({"action": "add_watch_wallet"}),
    }


def _exec_add_intel_tag(conn, rec: Dict) -> Dict:
    target = rec["target_address"]
    payload = json.loads(rec.get("payload") or "{}")
    tag = payload.get("tag", "")
    if not tag:
        return {"success": False, "message": "No tag specified in payload", "revert_data": None}

    # Namespace Intel tags
    namespaced_tag = f"intel:{tag}" if not tag.startswith("intel:") else tag
    target_type = rec.get("target_type", "wallet")

    if target_type == "wallet":
        conn.execute("DELETE FROM wallet_tags WHERE wallet_address = ? AND tag = ?", (target, namespaced_tag))
        conn.execute(
            "INSERT INTO wallet_tags (wallet_address, tag, tier, source) VALUES (?, ?, 2, 'intel')",
            (target, namespaced_tag),
        )
    elif target_type == "token":
        # Find token ID
        row = conn.execute("SELECT id FROM analyzed_tokens WHERE token_address = ?", (target,)).fetchone()
        if row:
            conn.execute("DELETE FROM token_tags WHERE token_id = ? AND tag = ?", (row[0], namespaced_tag))
            conn.execute(
                "INSERT INTO token_tags (token_id, tag, tier, source) VALUES (?, ?, 2, 'intel')",
                (row[0], namespaced_tag),
            )
        else:
            return {"success": False, "message": f"Token {target} not found", "revert_data": None}

    return {
        "success": True,
        "message": f"Added tag '{namespaced_tag}' to {target_type} {target}",
        "revert_data": json.dumps({"action": "remove_intel_tag", "tag": namespaced_tag}),
    }


def _exec_remove_intel_tag(conn, rec: Dict) -> Dict:
    target = rec["target_address"]
    payload = json.loads(rec.get("payload") or "{}")
    tag = payload.get("tag", "")
    if not tag:
        return {"success": False, "message": "No tag specified in payload", "revert_data": None}

    target_type = rec.get("target_type", "wallet")
    if target_type == "wallet":
        conn.execute("DELETE FROM wallet_tags WHERE wallet_address = ? AND tag = ? AND source = 'intel'", (target, tag))
    elif target_type == "token":
        row = conn.execute("SELECT id FROM analyzed_tokens WHERE token_address = ?", (target,)).fetchone()
        if row:
            conn.execute("DELETE FROM token_tags WHERE token_id = ? AND tag = ? AND source = 'intel'", (row[0], tag))

    return {
        "success": True,
        "message": f"Removed tag '{tag}' from {target_type} {target}",
        "revert_data": json.dumps({"action": "add_intel_tag", "tag": tag}),
    }


def _exec_add_nametag(conn, rec: Dict) -> Dict:
    target = rec["target_address"]
    payload = json.loads(rec.get("payload") or "{}")
    nametag = payload.get("nametag", "")
    if not nametag:
        return {"success": False, "message": "No nametag specified", "revert_data": None}

    row = conn.execute("SELECT nametag FROM wallet_nametags WHERE wallet_address = ?", (target,)).fetchone()
    old_nametag = row[0] if row else None

    conn.execute("DELETE FROM wallet_nametags WHERE wallet_address = ?", (target,))
    conn.execute(
        "INSERT INTO wallet_nametags (wallet_address, nametag) VALUES (?, ?)",
        (target, nametag),
    )

    return {
        "success": True,
        "message": f"Set nametag '{nametag}' for {target}",
        "revert_data": json.dumps({"action": "remove_nametag", "old_nametag": old_nametag}),
    }


def _exec_queue_refresh(conn, rec: Dict) -> Dict:
    """Queue a PnL or funding refresh — just logs the intent, actual refresh happens async."""
    target = rec["target_address"]
    action = rec["action_type"]
    return {
        "success": True,
        "message": f"Queued {action.replace('queue_', '')} for {target}",
        "revert_data": None,  # Refresh operations aren't revertible
    }


# Handler registry
ACTION_HANDLERS = {
    "add_bot_allowlist_wallet": _exec_add_bot_allowlist,
    "remove_bot_allowlist_wallet": _exec_remove_bot_allowlist,
    "add_bot_denylist_wallet": _exec_add_bot_denylist,
    "remove_bot_denylist_wallet": _exec_remove_bot_denylist,
    "add_watch_wallet": _exec_add_watch_wallet,
    "remove_watch_wallet": _exec_remove_watch_wallet,
    "add_intel_tag": _exec_add_intel_tag,
    "remove_intel_tag": _exec_remove_intel_tag,
    "add_nametag": _exec_add_nametag,
    "queue_wallet_pnl_refresh": _exec_queue_refresh,
    "queue_wallet_funding_refresh": _exec_queue_refresh,
}


# ============================================================================
# Public API
# ============================================================================

def create_recommendations_from_report(report_id: int, structured: Dict) -> List[Dict]:
    """
    Parse the Investigator's structured output and create recommendation rows.
    Returns list of created recommendations.
    """
    ensure_tables()
    created = []
    now = _now()

    actions = structured.get("recommended_actions", [])
    if not actions:
        return created

    with db.get_db_connection() as conn:
        conn.row_factory = sqlite3.Row
        for action in actions:
            action_type = action.get("action_type", "")
            if action_type not in ACTION_HANDLERS:
                log_error(f"[RecommendationExecutor] Unknown action type: {action_type}")
                continue

            cursor = conn.execute(
                """INSERT INTO intel_recommendations
                   (report_id, action_type, target_type, target_address,
                    payload, reason, confidence, expected_bot_effect, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'proposed', ?)""",
                (
                    report_id,
                    action_type,
                    action.get("target_type", "wallet"),
                    action.get("target_address", ""),
                    json.dumps(action.get("payload", {})),
                    action.get("reason", ""),
                    action.get("confidence", "medium"),
                    action.get("expected_bot_effect", ""),
                    now,
                ),
            )
            rec_id = cursor.lastrowid

            _log_audit(conn, rec_id, report_id, action_type,
                       action.get("target_address", ""),
                       None, "proposed", notes="Created from Intel report")

            created.append({
                "id": rec_id,
                "action_type": action_type,
                "target_address": action.get("target_address", ""),
                "status": "proposed",
            })

        log_info(f"[RecommendationExecutor] Created {len(created)} recommendations from report {report_id}")

    return created


def approve_recommendation(rec_id: int) -> Dict:
    """
    Approve a recommendation: apply immediately + make bot-active.
    Returns {success, message, recommendation}.
    """
    ensure_tables()

    with db.get_db_connection() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM intel_recommendations WHERE id = ?", (rec_id,)).fetchone()
        if not row:
            return {"success": False, "message": f"Recommendation {rec_id} not found"}

        rec = dict(row)
        if rec["status"] != "proposed":
            return {"success": False, "message": f"Cannot approve — status is '{rec['status']}'"}

        handler = ACTION_HANDLERS.get(rec["action_type"])
        if not handler:
            return {"success": False, "message": f"No handler for action type '{rec['action_type']}'"}

        # Execute the action
        now = _now()
        result = handler(conn, rec)

        if result["success"]:
            # Update recommendation status
            conn.execute(
                """UPDATE intel_recommendations
                   SET status = 'active_for_bot', approved_at = ?, applied_at = ?,
                       revert_data = ?
                   WHERE id = ?""",
                (now, now, result.get("revert_data"), rec_id),
            )

            # Audit: proposed → approved → applied → active_for_bot (single operation, multiple logical steps)
            _log_audit(conn, rec_id, rec["report_id"], rec["action_type"],
                       rec["target_address"], "proposed", "active_for_bot",
                       after_state=result.get("revert_data"),
                       notes=f"Approved and applied: {result['message']}")

            log_info(f"[RecommendationExecutor] Approved #{rec_id}: {result['message']}")
            rec["status"] = "active_for_bot"
            rec["approved_at"] = now
            rec["applied_at"] = now
        else:
            conn.execute(
                "UPDATE intel_recommendations SET status = 'failed' WHERE id = ?", (rec_id,)
            )
            _log_audit(conn, rec_id, rec["report_id"], rec["action_type"],
                       rec["target_address"], "proposed", "failed",
                       notes=f"Failed: {result['message']}")
            rec["status"] = "failed"

        return {"success": result["success"], "message": result["message"], "recommendation": rec}


def reject_recommendation(rec_id: int, reason: str = "") -> Dict:
    """Reject a recommendation — no system changes."""
    ensure_tables()

    with db.get_db_connection() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM intel_recommendations WHERE id = ?", (rec_id,)).fetchone()
        if not row:
            return {"success": False, "message": f"Recommendation {rec_id} not found"}

        rec = dict(row)
        if rec["status"] != "proposed":
            return {"success": False, "message": f"Cannot reject — status is '{rec['status']}'"}

        now = _now()
        conn.execute(
            "UPDATE intel_recommendations SET status = 'rejected', rejected_at = ? WHERE id = ?",
            (now, rec_id),
        )
        _log_audit(conn, rec_id, rec["report_id"], rec["action_type"],
                   rec["target_address"], "proposed", "rejected",
                   notes=f"Rejected: {reason}")

        log_info(f"[RecommendationExecutor] Rejected #{rec_id}: {reason}")
        return {"success": True, "message": f"Rejected recommendation #{rec_id}"}


def revert_recommendation(rec_id: int) -> Dict:
    """Revert a previously approved recommendation."""
    ensure_tables()

    with db.get_db_connection() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM intel_recommendations WHERE id = ?", (rec_id,)).fetchone()
        if not row:
            return {"success": False, "message": f"Recommendation {rec_id} not found"}

        rec = dict(row)
        if rec["status"] != "active_for_bot":
            return {"success": False, "message": f"Cannot revert — status is '{rec['status']}'"}

        revert_data = json.loads(rec.get("revert_data") or "{}")
        revert_action = revert_data.get("action")
        if not revert_action:
            return {"success": False, "message": "No revert data available"}

        # Build a synthetic recommendation for the revert handler
        revert_rec = {
            "id": rec_id,
            "action_type": revert_action,
            "target_type": rec["target_type"],
            "target_address": rec["target_address"],
            "payload": json.dumps(revert_data),
            "reason": f"Revert of recommendation #{rec_id}",
            "confidence": rec["confidence"],
            "report_id": rec["report_id"],
        }

        handler = ACTION_HANDLERS.get(revert_action)
        if not handler:
            return {"success": False, "message": f"No handler for revert action '{revert_action}'"}

        result = handler(conn, revert_rec)
        if result["success"]:
            now = _now()
            conn.execute(
                "UPDATE intel_recommendations SET status = 'reverted', reverted_at = ? WHERE id = ?",
                (now, rec_id),
            )
            _log_audit(conn, rec_id, rec["report_id"], rec["action_type"],
                       rec["target_address"], "active_for_bot", "reverted",
                       notes=f"Reverted: {result['message']}")

            log_info(f"[RecommendationExecutor] Reverted #{rec_id}: {result['message']}")

        return {"success": result["success"], "message": result["message"]}


def get_recommendations(status: str = None, report_id: int = None, limit: int = 50) -> List[Dict]:
    """Get recommendations with optional filters."""
    ensure_tables()

    with db.get_db_connection() as conn:
        conn.row_factory = sqlite3.Row
        query = "SELECT * FROM intel_recommendations WHERE 1=1"
        params = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if report_id:
            query += " AND report_id = ?"
            params.append(report_id)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def get_audit_log(recommendation_id: int = None, limit: int = 100) -> List[Dict]:
    """Get audit log entries."""
    ensure_tables()

    with db.get_db_connection() as conn:
        conn.row_factory = sqlite3.Row
        if recommendation_id:
            rows = conn.execute(
                "SELECT * FROM intel_audit_log WHERE recommendation_id = ? ORDER BY performed_at DESC LIMIT ?",
                (recommendation_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM intel_audit_log ORDER BY performed_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]


def get_bot_lists() -> Dict:
    """Get current active bot allowlist and denylist."""
    ensure_tables()

    with db.get_db_connection() as conn:
        conn.row_factory = sqlite3.Row
        allowlist = [dict(r) for r in conn.execute(
            "SELECT * FROM intel_bot_allowlist WHERE active = 1"
        ).fetchall()]
        denylist = [dict(r) for r in conn.execute(
            "SELECT * FROM intel_bot_denylist WHERE active = 1"
        ).fetchall()]

    return {"allowlist": allowlist, "denylist": denylist}
