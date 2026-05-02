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

            -- Operator override → structured rule for the Investigator's next run.
            -- Populated by override_analyst.py whenever Reclassify is used.
            CREATE TABLE IF NOT EXISTS intel_agent_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_recommendation_id INTEGER,
                source_report_id INTEGER,
                target_address TEXT,
                operator_category TEXT,
                operator_note TEXT,
                original_action_type TEXT,
                corrected_action_type TEXT,
                trigger_signal TEXT,
                wrong_conclusion TEXT,
                correct_conclusion TEXT,
                rule_text TEXT,
                example_evidence TEXT,
                created_at TEXT,
                times_referenced INTEGER DEFAULT 0,
                active INTEGER DEFAULT 1
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

    # Auto-add to Wallet Shadow so we accumulate trade data on every allowlisted wallet.
    # Track whether shadow was already present so a revert only undoes what we added.
    shadow_row = conn.execute(
        "SELECT active FROM wallet_shadow_targets WHERE wallet_address = ?", (target,)
    ).fetchone()
    shadow_already_active = bool(shadow_row and shadow_row[0] == 1)
    label = (rec.get("reason") or "Intel Allowlist")[:120]

    if shadow_row is None:
        conn.execute(
            "INSERT INTO wallet_shadow_targets (wallet_address, label, added_at, active) VALUES (?, ?, ?, 1)",
            (target, label, _now()),
        )
    elif not shadow_already_active:
        conn.execute(
            "UPDATE wallet_shadow_targets SET active = 1, label = ?, added_at = ? WHERE wallet_address = ?",
            (label, _now(), target),
        )

    if not shadow_already_active:
        conn.execute("DELETE FROM wallet_tags WHERE wallet_address = ? AND tag = 'Intel Monitor'", (target,))
        conn.execute(
            "INSERT INTO wallet_tags (wallet_address, tag, tier, source) VALUES (?, 'Intel Monitor', 2, 'intel')",
            (target,),
        )

    shadow_msg = "already shadowed" if shadow_already_active else "now shadowed"
    return {
        "success": True,
        "message": f"Added {target} to bot allowlist ({shadow_msg})",
        "revert_data": json.dumps({
            "action": "remove_bot_allowlist_wallet",
            "before": before,
            "shadow_already_active": shadow_already_active,
        }),
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

    # If this is a revert of an allowlist add that turned shadow on, undo the shadow too.
    # Default True (preserve shadow) for any other invocation — operator's manual tracking is sacred.
    payload = json.loads(rec.get("payload") or "{}")
    shadow_already_active = payload.get("shadow_already_active", True)
    if not shadow_already_active:
        conn.execute("UPDATE wallet_shadow_targets SET active = 0 WHERE wallet_address = ?", (target,))
        conn.execute("DELETE FROM wallet_tags WHERE wallet_address = ? AND tag = 'Intel Monitor'", (target,))

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


def _exec_monitor_wallet(conn, rec: Dict) -> Dict:
    """Add a wallet to Wallet Shadow real-time tracking."""
    target = rec["target_address"]
    payload = json.loads(rec.get("payload") or "{}")
    label = payload.get("label") or rec.get("reason") or "Intel Monitor"

    # Check if already tracked
    row = conn.execute(
        "SELECT 1 FROM wallet_shadow_targets WHERE wallet_address = ?", (target,)
    ).fetchone()

    if row:
        return {
            "success": True,
            "message": f"{target} is already being monitored in Wallet Shadow",
            "revert_data": None,
        }

    conn.execute(
        "INSERT INTO wallet_shadow_targets (wallet_address, label, added_at, active) VALUES (?, ?, ?, 1)",
        (target, label, _now()),
    )

    # Also add an Intel Monitor tag
    conn.execute("DELETE FROM wallet_tags WHERE wallet_address = ? AND tag = 'Intel Monitor'", (target,))
    conn.execute(
        "INSERT INTO wallet_tags (wallet_address, tag, tier, source) VALUES (?, 'Intel Monitor', 2, 'intel')",
        (target,),
    )

    return {
        "success": True,
        "message": f"Added {target} to Wallet Shadow monitoring as '{label}'",
        "revert_data": json.dumps({"action": "stop_monitor_wallet"}),
    }


def _exec_stop_monitor_wallet(conn, rec: Dict) -> Dict:
    """Remove a wallet from Wallet Shadow tracking."""
    target = rec["target_address"]
    conn.execute("DELETE FROM wallet_shadow_targets WHERE wallet_address = ?", (target,))
    conn.execute("DELETE FROM wallet_tags WHERE wallet_address = ? AND tag = 'Intel Monitor'", (target,))
    return {
        "success": True,
        "message": f"Removed {target} from Wallet Shadow monitoring",
        "revert_data": None,
    }


def _exec_probe_wallet(conn, rec: Dict) -> Dict:
    """Queue a Deep Bot Probe run on a wallet. The actual probe runs async when approved."""
    target = rec["target_address"]
    payload = json.loads(rec.get("payload") or "{}")

    # Create a bot probe run entry in queued state
    conn.execute("""
        INSERT INTO bot_probe_runs (wallet_address, status, requested_at, requested_by)
        VALUES (?, 'queued', ?, 'intel_agent')
    """, (target, _now()))

    return {
        "success": True,
        "message": f"Queued Bot Probe for {target} — will run when started from Bot Probe page",
        "revert_data": None,
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
    "monitor_wallet": _exec_monitor_wallet,
    "stop_monitor_wallet": _exec_stop_monitor_wallet,
    "probe_wallet": _exec_probe_wallet,
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


def reclassify_recommendation(
    rec_id: int,
    new_action_type: str,
    reason: str = "",
    payload: Optional[Dict] = None,
    operator_category: str = "other",
    operator_note: str = "",
) -> Dict:
    """
    Override a misclassified recommendation. Marks the original 'overridden',
    creates a fresh recommendation with the operator-chosen action, and
    auto-approves it.

    The operator picks a `operator_category` from a fixed list (see
    override_analyst.OVERRIDE_CATEGORIES). After the override is applied, the
    Override Analyst runs in-process and turns the override + wallet snapshot
    into a structured rule, persisted in intel_agent_rules. The next Intel
    run injects those rules into the Investigator's prompt so the same
    mistake isn't made twice.
    """
    ensure_tables()

    if new_action_type not in ACTION_HANDLERS:
        return {"success": False, "message": f"Unknown action type: {new_action_type}"}

    with db.get_db_connection() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM intel_recommendations WHERE id = ?", (rec_id,)).fetchone()
        if not row:
            return {"success": False, "message": f"Recommendation {rec_id} not found"}

        rec = dict(row)
        if rec["status"] != "proposed":
            return {"success": False, "message": f"Cannot reclassify — status is '{rec['status']}'"}

        now = _now()

        # 1. Mark the original as overridden (distinct from rejected so the feedback loop can tell them apart)
        conn.execute(
            "UPDATE intel_recommendations SET status = 'overridden', rejected_at = ? WHERE id = ?",
            (now, rec_id),
        )
        _log_audit(
            conn, rec_id, rec["report_id"], rec["action_type"],
            rec["target_address"], "proposed", "overridden",
            notes=f"Overridden -> {new_action_type}: {reason}",
        )

        # 2. Create the replacement recommendation
        cursor = conn.execute(
            """INSERT INTO intel_recommendations
               (report_id, action_type, target_type, target_address,
                payload, reason, confidence, expected_bot_effect, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'proposed', ?)""",
            (
                rec["report_id"],
                new_action_type,
                rec["target_type"],
                rec["target_address"],
                json.dumps(payload or {}),
                f"[Operator override of #{rec_id}] {reason}".strip(),
                "high",
                rec.get("expected_bot_effect", ""),
                now,
            ),
        )
        new_rec_id = cursor.lastrowid
        _log_audit(
            conn, new_rec_id, rec["report_id"], new_action_type,
            rec["target_address"], None, "proposed",
            notes=f"Created via override of #{rec_id}",
        )

        # 3. Auto-approve the replacement so the operator gets one-click correction
        new_rec = dict(conn.execute(
            "SELECT * FROM intel_recommendations WHERE id = ?", (new_rec_id,)
        ).fetchone())
        handler = ACTION_HANDLERS[new_action_type]
        result = handler(conn, new_rec)

        if result["success"]:
            conn.execute(
                """UPDATE intel_recommendations
                   SET status = 'active_for_bot', approved_at = ?, applied_at = ?, revert_data = ?
                   WHERE id = ?""",
                (now, now, result.get("revert_data"), new_rec_id),
            )
            _log_audit(
                conn, new_rec_id, rec["report_id"], new_action_type,
                rec["target_address"], "proposed", "active_for_bot",
                after_state=result.get("revert_data"),
                notes=f"Auto-approved via override: {result['message']}",
            )
        else:
            conn.execute(
                "UPDATE intel_recommendations SET status = 'failed' WHERE id = ?", (new_rec_id,)
            )
            _log_audit(
                conn, new_rec_id, rec["report_id"], new_action_type,
                rec["target_address"], "proposed", "failed",
                notes=f"Override failed: {result['message']}",
            )

        log_info(f"[RecommendationExecutor] Reclassified #{rec_id} -> #{new_rec_id} ({new_action_type})")

    # Outside the DB connection: run the Override Analyst to extract a rule.
    # Failures are non-fatal — the override is already applied; we'd just lose
    # the lesson for the next Intel run.
    rule = None
    try:
        from meridinate.services.override_analyst import extract_rule_from_override
        rule = extract_rule_from_override(
            recommendation=rec,
            new_action_type=new_action_type,
            operator_category=operator_category,
            operator_note=operator_note,
        )
    except Exception as e:
        log_error(f"[RecommendationExecutor] Override Analyst threw: {e}")

    return {
        "success": result["success"],
        "message": f"Reclassified to {new_action_type}: {result['message']}",
        "original_id": rec_id,
        "new_id": new_rec_id,
        "rule_extracted": bool(rule),
        "rule_text": rule.get("rule_text") if rule else None,
    }


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
