"""
Meridinate Housekeeper Agent

Wallet reliability verifier and data integrity agent.
Runs BEFORE the Investigator to verify whether wallet-based conclusions
are safe to trust, flag low-confidence candidates, and fix data issues.

Has scoped WRITE access — constrained operations only.
Uses a separate Anthropic API key to keep costs trackable.
"""

import json
import re
import sqlite3
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

import anthropic

from meridinate import analyzed_tokens_db as db, settings
from meridinate.observability import log_error, log_info
from meridinate.credit_tracker import get_credit_tracker


def _execute_read(sql: str, params: list = None) -> List[Dict]:
    """Execute a read-only SQL query."""
    try:
        with db.get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(sql, params or [])
            return [dict(r) for r in cursor.fetchall()[:200]]
    except Exception as e:
        return [{"error": str(e)}]


def _fix_token_verdict(token_id: int, verdict: str, reason: str) -> Dict:
    """Set or replace a token verdict — SELF-VALIDATING.
    Recomputes the verdict rule server-side before applying."""
    if verdict not in ("verified-win", "verified-loss"):
        return {"error": f"Invalid verdict: {verdict}", "rows_affected": 0}
    try:
        with db.get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Look up the token's actual numbers
            cursor.execute(
                "SELECT market_cap_usd, market_cap_usd_current, market_cap_ath FROM analyzed_tokens WHERE id = ?",
                (token_id,),
            )
            row = cursor.fetchone()
            if not row:
                return {"error": f"Token {token_id} not found", "rows_affected": 0, "rejected": True}

            scan_mc = row["market_cap_usd"] or 0
            current_mc = row["market_cap_usd_current"] or 0
            ath = row["market_cap_ath"] or 0

            # Check if already has a verdict
            cursor.execute(
                "SELECT tag FROM token_tags WHERE token_id = ? AND tag IN ('verified-win', 'verified-loss')",
                (token_id,),
            )
            existing = cursor.fetchone()
            if existing:
                return {"error": f"Token {token_id} already has verdict '{existing['tag']}'. Remove first if correction needed.",
                        "rows_affected": 0, "rejected": True}

            # SERVER-SIDE INVARIANT CHECK — the model is NOT the authority on thresholds
            if verdict == "verified-win":
                # Rule: ATH >= 3x scan MC AND current >= 1x scan MC
                #    OR ATH >= 1.5x AND current >= 1.5x
                ath_multiple = ath / scan_mc if scan_mc > 0 else 0
                current_multiple = current_mc / scan_mc if scan_mc > 0 else 0
                win_ok = (ath_multiple >= 3.0 and current_multiple >= 1.0) or \
                         (ath_multiple >= 1.5 and current_multiple >= 1.5)
                if not win_ok:
                    return {
                        "error": f"REJECTED: verified-win invariant not met. "
                                 f"ATH={ath_multiple:.1f}x, current={current_multiple:.1f}x "
                                 f"(scan_MC=${scan_mc:,.0f}, current_MC=${current_mc:,.0f}, ATH=${ath:,.0f})",
                        "rows_affected": 0, "rejected": True,
                    }

            elif verdict == "verified-loss":
                # Rule: current < 10% of scan MC
                if scan_mc > 0 and current_mc > 0:
                    pct_of_scan = current_mc / scan_mc
                    if pct_of_scan >= 0.10:
                        return {
                            "error": f"REJECTED: verified-loss invariant not met. "
                                     f"Current MC is {pct_of_scan:.0%} of scan MC, not below 10%. "
                                     f"(scan_MC=${scan_mc:,.0f}, current_MC=${current_mc:,.0f})",
                            "rows_affected": 0, "rejected": True,
                        }

            # Invariant passed — apply the verdict
            conn.row_factory = None  # reset for writes
            cursor.execute("DELETE FROM token_tags WHERE token_id = ? AND tag IN ('verified-win', 'verified-loss')", (token_id,))
            cursor.execute(
                "INSERT INTO token_tags (token_id, tag, tier, source) VALUES (?, ?, 1, 'housekeeper')",
                (token_id, verdict),
            )
            log_info(f"[Housekeeper] fix_token_verdict: token {token_id} → {verdict} (validated) | {reason}")
            return {"rows_affected": 1, "success": True}
    except Exception as e:
        return {"error": str(e), "rows_affected": 0}


def _fix_multiplier_tag(token_id: int, old_tag: str, new_tag: str, reason: str) -> Dict:
    """Replace a win multiplier tag — SELF-VALIDATING.
    Recomputes the correct multiplier server-side before applying."""
    if not new_tag.startswith("win:") or not new_tag.endswith("x"):
        return {"error": f"Invalid multiplier tag format: {new_tag}", "rows_affected": 0}
    try:
        with db.get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Look up the token's actual numbers
            cursor.execute(
                "SELECT market_cap_usd, market_cap_ath FROM analyzed_tokens WHERE id = ?",
                (token_id,),
            )
            row = cursor.fetchone()
            if not row:
                return {"error": f"Token {token_id} not found", "rows_affected": 0, "rejected": True}

            scan_mc = row["market_cap_usd"] or 0
            ath = row["market_cap_ath"] or 0

            if scan_mc <= 0:
                return {"error": f"Token {token_id} has zero scan MC, cannot compute multiplier",
                        "rows_affected": 0, "rejected": True}

            # SERVER-SIDE INVARIANT CHECK — compute the CORRECT multiplier
            correct_multiple = int(ath / scan_mc)  # floor division, same as int() on positive
            if correct_multiple < 3:
                return {
                    "error": f"REJECTED: ATH/MC ratio is {ath/scan_mc:.1f}x, floors to {correct_multiple}x. "
                             f"Minimum win multiplier is 3x. (ATH=${ath:,.0f}, scan_MC=${scan_mc:,.0f})",
                    "rows_affected": 0, "rejected": True,
                }

            correct_tag = f"win:{correct_multiple}x"

            # Reject if the model's proposed tag doesn't match the server-computed tag
            if new_tag != correct_tag:
                return {
                    "error": f"REJECTED: model proposed {new_tag} but server computed {correct_tag}. "
                             f"ATH=${ath:,.0f} / scan_MC=${scan_mc:,.0f} = {ath/scan_mc:.1f}x, "
                             f"floor = {correct_multiple}x. Applying {correct_tag} instead.",
                    "rows_affected": 0, "rejected": True,
                    "correct_tag": correct_tag,
                }

            # If old_tag already matches the correct tag, nothing to do
            if old_tag == correct_tag:
                return {"error": f"No change needed: {old_tag} is already correct", "rows_affected": 0}

            # Invariant passed — apply the fix
            conn.row_factory = None
            cursor.execute("DELETE FROM token_tags WHERE token_id = ? AND tag = ?", (token_id, old_tag))
            cursor.execute(
                "INSERT INTO token_tags (token_id, tag, tier, source) VALUES (?, ?, 1, 'housekeeper')",
                (token_id, correct_tag),
            )
            log_info(f"[Housekeeper] fix_multiplier: token {token_id} {old_tag} → {correct_tag} (validated) | {reason}")
            return {"rows_affected": 1, "success": True, "applied_tag": correct_tag}
    except Exception as e:
        return {"error": str(e), "rows_affected": 0}


def _update_wallet_tag(wallet_address: str, action: str, tag: str, reason: str) -> Dict:
    """Add or remove a wallet tag. Action must be 'add' or 'remove'."""
    if action not in ("add", "remove"):
        return {"error": f"Invalid action: {action}", "rows_affected": 0}
    try:
        with db.get_db_connection() as conn:
            cursor = conn.cursor()
            if action == "remove":
                cursor.execute("DELETE FROM wallet_tags WHERE wallet_address = ? AND tag = ?", (wallet_address, tag))
            else:
                cursor.execute("DELETE FROM wallet_tags WHERE wallet_address = ? AND tag = ?", (wallet_address, tag))
                cursor.execute(
                    "INSERT INTO wallet_tags (wallet_address, tag, tier, source) VALUES (?, ?, 2, 'housekeeper')",
                    (wallet_address, tag),
                )
            log_info(f"[Housekeeper] wallet_tag: {action} '{tag}' on {wallet_address[:16]}... | {reason}")
            return {"rows_affected": cursor.rowcount or 1, "success": True}
    except Exception as e:
        return {"error": str(e), "rows_affected": 0}


HOUSEKEEPER_TOOLS = [
    {
        "name": "query_database",
        "description": """Execute a read-only SELECT query. Use ONLY for narrow confirmation queries about specific wallets/tokens.
Do NOT use for: schema discovery, broad scans, SELECT * LIMIT 1, PRAGMA, or any query that explores table structure.
All wallet reliability data is ALREADY in the prompt payload. Only query if you need a specific fact about a specific address that is NOT in the provided data.
Tables: analyzed_tokens, early_buyer_wallets, mtew_token_positions, wallet_tags, token_tags, wallet_enrichment_cache, wallet_leaderboard_cache.
Max 200 rows.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "SELECT query"},
                "params": {"type": "array", "items": {"type": "string"}, "description": "Query parameters"}
            },
            "required": ["sql"]
        }
    },
    {
        "name": "fix_token_verdict",
        "description": "Set a token's verdict. SELF-VALIDATING: the backend recomputes the verdict rule from actual MC/ATH data and REJECTS if the threshold is not met. Propose the verdict you believe is correct — the backend will verify.",
        "input_schema": {
            "type": "object",
            "properties": {
                "token_id": {"type": "integer", "description": "Token ID from analyzed_tokens"},
                "verdict": {"type": "string", "enum": ["verified-win", "verified-loss"], "description": "The verdict to set"},
                "reason": {"type": "string", "description": "Why this verdict is correct"}
            },
            "required": ["token_id", "verdict", "reason"]
        }
    },
    {
        "name": "fix_multiplier_tag",
        "description": "Replace a win multiplier tag. SELF-VALIDATING: the backend computes floor(ATH/scan_MC) and REJECTS if the proposed tag doesn't match. You do not need to do the math — just propose what you think is correct and the backend will verify or reject.",
        "input_schema": {
            "type": "object",
            "properties": {
                "token_id": {"type": "integer", "description": "Token ID"},
                "old_tag": {"type": "string", "description": "Current tag to remove (e.g. win:5x)"},
                "new_tag": {"type": "string", "description": "Correct tag to set (e.g. win:9x)"},
                "reason": {"type": "string", "description": "Why the correction is needed"}
            },
            "required": ["token_id", "old_tag", "new_tag", "reason"]
        }
    },
    {
        "name": "update_wallet_tag",
        "description": "Add or remove a wallet tag. Use to fix incorrect tags or flag unreliable wallets.",
        "input_schema": {
            "type": "object",
            "properties": {
                "wallet_address": {"type": "string", "description": "Full wallet address"},
                "action": {"type": "string", "enum": ["add", "remove"], "description": "Whether to add or remove the tag"},
                "tag": {"type": "string", "description": "Tag name (e.g. 'Consistent Winner', 'Sniper Bot')"},
                "reason": {"type": "string", "description": "Why this change is needed"}
            },
            "required": ["wallet_address", "action", "tag", "reason"]
        }
    },
    {
        "name": "trace_wallet_funding",
        "description": "Get funding source for a wallet from enrichment cache. Zero credits.",
        "input_schema": {
            "type": "object",
            "properties": {
                "wallet_address": {"type": "string"}
            },
            "required": ["wallet_address"]
        }
    }
]


def _handle_tool_call(tool_name: str, tool_input: Dict) -> str:
    """Execute a housekeeper tool call."""
    if tool_name == "query_database":
        sql = tool_input.get("sql", "")
        if not sql.strip().upper().startswith("SELECT"):
            return json.dumps({"error": "Only SELECT queries allowed. Use scoped write tools."})
        # Block schema-discovery queries — the prompt already provides all schema info
        upper = sql.strip().upper()
        if "PRAGMA" in upper or "SQLITE_MASTER" in upper:
            return json.dumps({"error": "Schema discovery not allowed. All table schemas are described in the system prompt."})
        if "SELECT *" in upper and "LIMIT 1" in upper and "WHERE" not in upper:
            return json.dumps({"error": "Schema-probing queries (SELECT * ... LIMIT 1) not allowed. All column info is in the system prompt. Query specific columns for specific wallets/tokens."})
        return json.dumps(_execute_read(sql, tool_input.get("params", [])), default=str)

    elif tool_name == "fix_token_verdict":
        result = _fix_token_verdict(
            tool_input["token_id"], tool_input["verdict"], tool_input.get("reason", "")
        )
        if result.get("rejected"):
            log_info(f"[Housekeeper] REJECTED fix_token_verdict: token {tool_input['token_id']} "
                     f"→ {tool_input['verdict']} | {result.get('error', '')}")
        return json.dumps(result, default=str)

    elif tool_name == "fix_multiplier_tag":
        result = _fix_multiplier_tag(
            tool_input["token_id"], tool_input["old_tag"], tool_input["new_tag"], tool_input.get("reason", "")
        )
        if result.get("rejected"):
            log_info(f"[Housekeeper] REJECTED fix_multiplier: token {tool_input['token_id']} "
                     f"{tool_input['old_tag']} → {tool_input['new_tag']} | {result.get('error', '')}")
        return json.dumps(result, default=str)

    elif tool_name == "update_wallet_tag":
        return json.dumps(_update_wallet_tag(
            tool_input["wallet_address"], tool_input["action"], tool_input["tag"], tool_input.get("reason", "")
        ), default=str)

    elif tool_name == "trace_wallet_funding":
        addr = tool_input.get("wallet_address", "")
        try:
            with db.get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT funded_by_json FROM wallet_enrichment_cache WHERE wallet_address = ?", (addr,))
                row = cursor.fetchone()
                return row[0] if row and row[0] else json.dumps({"result": "No funding data"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    return json.dumps({"error": f"Unknown tool: {tool_name}"})


HOUSEKEEPER_SYSTEM = """You are the Meridinate Housekeeper — a wallet reliability verifier and data integrity agent for a Solana token intelligence platform (SQLite database).

Your PRIMARY role is to verify whether wallet-based conclusions are safe to trust in a downstream bot-operator report. Your SECONDARY role is to fix data quality issues.

IMPORTANT RULES:
- This is SQLite — use SQLite syntax only (no ::numeric, no ILIKE, use LIKE instead)
- The data you receive in the prompt is ALREADY QUERIED — do NOT re-query the same data
- Go straight to verification and fixes using the pre-computed data below
- Do NOT run schema discovery queries (PRAGMA, sqlite_master, SELECT * LIMIT 1)
- Do NOT guess column names. The ONLY columns that exist are listed below. If you need data not provided, mark it as a report_blocker — do NOT probe for it.
- Your fix tools are SELF-VALIDATING. The backend will recompute thresholds server-side and REJECT incorrect proposals. You do not need to be 100% sure of the arithmetic — the backend is the authority. But do not waste iterations on clearly wrong proposals.
- Ideal behavior: very few SQL queries, most conclusions derived from pre-computed data below, narrow confirmation queries only for edge cases

Database tables: analyzed_tokens, early_buyer_wallets, mtew_token_positions, wallet_tags, token_tags, wallet_enrichment_cache, wallet_leaderboard_cache, starred_items

Key columns in token_tags: token_id, tag (e.g. 'verified-win', 'win:9x', 'loss:rug'), tier, source
Key columns in analyzed_tokens: id, token_name, token_address, market_cap_usd (at scan), market_cap_usd_current, market_cap_ath, deployer_address

Win multiplier tags use GRANULAR integer multiples: win:3x, win:7x, win:9x, win:15x, win:42x, etc. The tag value = floor(market_cap_ath / market_cap_usd). Minimum win:3x.

ADDRESS FORMATTING:
- NEVER truncate wallet or token addresses. Always output the FULL address (all 32-44 characters).
- Wrong: "8EmAjS1V..." or "64hP97...abc"
- Right: "8EmAjS1VtSBnGivqsJUgpFnDexjGv43G3B7bM1gYpump" (full address)

YOUR TASKS (in priority order):

1. WALLET RELIABILITY VERIFICATION — For each candidate wallet in the leads, determine TWO separate things:
   a) DATA-RELIABLE: Is the data on this wallet complete enough to reason about? Check:
      - Does it have real PnL (pnl_source = 'helius_enhanced') or only estimated?
      - Is it tagged Sniper Bot? (inflates quality metrics)
      - Does it have funding data cached? (wallet_enrichment_cache)
      - How many resolved tokens does it have? (small sample = low confidence)
      - How many tokens are still unresolved? (high unresolved share = incomplete picture)
      - Is it still active or gone cold? (last appearance in early_buyer_wallets)
   b) TRUST QUALITY: Even if data-reliable, is this wallet actually trustworthy? Check:
      - What is its rug exposure? (tokens that ended as verified-loss / total resolved)
      - 50-60% rug exposure means the wallet is data-reliable but NOT trust-approved
      - A wallet can be safe to reason about but unsafe to recommend for an allowlist
      - Only wallets with <40% rug exposure AND >5 resolved tokens should be marked trust-quality: high

2. MULTIPLIER VERIFICATION — if the actual_multiple differs from the tag, fix with fix_multiplier_tag

3. PENDING VERDICTS — if current_MC < 10% of scan_MC, set verified-loss. If ATH >= 3x and current >= 1x, set verified-win

4. TAG CORRECTIONS — remove incorrect wallet tags using update_wallet_tag

STRUCTURED OUTPUT REQUIREMENT:
After your prose report, you MUST output a JSON block fenced with ```json ... ``` containing:
{
  "wallet_reliability": [
    {
      "address": "FULL_ADDRESS_HERE",
      "data_reliable": true,
      "trust_quality": "high|medium|low",
      "real_pnl_coverage": 0.8,
      "resolved_sample": 12,
      "unresolved_share": 0.3,
      "rug_exposure": 0.45,
      "has_funding_data": true,
      "is_active": true,
      "is_sniper_bot": false,
      "notes": "data-reliable but 45% rug exposure — not trust-approved"
    }
  ],
  "unreliable_wallets": [{"address": "FULL_ADDRESS", "reason": "estimated PnL only, 2 resolved tokens"}],
  "refresh_needed": ["full_addr_needing_pnl_recompute"],
  "report_blockers": ["any issues that make downstream reasoning unsafe"],
  "data_fixes": {"verdicts_set": 3, "multipliers_fixed": 1, "tags_corrected": 0}
}

CRITICAL DISTINCTIONS in wallet_reliability:
- data_reliable=true means "safe to reason about" — the data is real, not estimated or contaminated
- trust_quality="high" means "safe to recommend for allowlist" — low rug exposure, good sample, real PnL
- trust_quality="medium" means "data looks okay but rug exposure 40-60% or sample <8"
- trust_quality="low" means "data-reliable but would NOT recommend for allowlist"
- A wallet can be data_reliable=true AND trust_quality="low" — these are DIFFERENT labels

This JSON is consumed by the downstream Investigator agent. Be precise. NEVER truncate addresses."""


def _extract_structured_json(text: str) -> Dict[str, Any]:
    """Extract the structured JSON block from agent output."""
    match = re.search(r'```json\s*(\{.*?\})\s*```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            log_error(f"[Housekeeper] Failed to parse structured JSON from output")
    return {}


def run_housekeeper(snapshot: str, quality_flags: str, raw_data: Dict,
                    on_dialogue=None, on_usage=None,
                    focus: str = "general", forensics_data: Dict = None) -> Dict[str, Any]:
    """
    Run the Housekeeper Agent to verify and fix database integrity.

    Args:
        focus: "general" for standard verification, "forensics" for top-PnL casefile mode
        forensics_data: output from generate_forensics_packet() when focus is "forensics"

    Returns:
        {report: str, structured: dict, fixes_applied: int, tool_calls: int, tokens_used: int, duration_seconds: float}
    """
    if not settings.ANTHROPIC_HOUSEKEEPER_KEY:
        return {"error": "Housekeeper API key not configured", "report": ""}

    t0 = time.time()
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_HOUSEKEEPER_KEY)

    # Build the multiplier verification data
    multiplier_data = ""
    if raw_data.get("multiplier_check"):
        multiplier_data = "\n\nWIN MULTIPLIER VERIFICATION DATA:\n"
        for m in raw_data["multiplier_check"]:
            multiplier_data += f"  Token '{m.get('token_name')}' (ID {m['id']}): tag={m['multiplier_tag']}, ATH=${m.get('market_cap_ath', 0):,.0f}, scan_MC=${m.get('market_cap_usd', 0):,.0f}, actual_multiple={m.get('actual_multiple', '?')}x\n"

    pending_data = ""
    if raw_data.get("pending_verdicts"):
        pending_data = "\n\nPENDING VERDICT TOKENS (>14 days old, no verdict):\n"
        for p in raw_data["pending_verdicts"]:
            pending_data += f"  Token '{p.get('token_name')}' (ID {p['id']}): scan_MC=${p.get('market_cap_usd', 0):,.0f}, current_MC=${p.get('market_cap_usd_current', 0):,.0f}, scanned={p.get('analysis_timestamp')}\n"

    # Build allowlist candidate data with FULL pre-computed reliability fields
    # so Housekeeper doesn't need ad hoc queries
    candidate_data = ""
    if raw_data.get("allowlist_candidates"):
        borderline_count = sum(1 for ac in raw_data["allowlist_candidates"] if ac.get("_borderline"))
        if borderline_count == len(raw_data["allowlist_candidates"]):
            candidate_data = "\n\nALLOWLIST CANDIDATE WALLETS — BORDERLINE (no wallets met strict thresholds, showing best-available):\n"
        else:
            candidate_data = "\n\nALLOWLIST CANDIDATE WALLETS — PRE-FILTERED (>=50% real PnL, <50% rug exposure, >=5 resolved):\n"
        candidate_data += "ALL RELIABILITY FIELDS PRE-COMPUTED — do NOT re-query these.\n"
        for ac in raw_data["allowlist_candidates"][:15]:
            borderline_note = f" ⚠ BORDERLINE: {ac['_filter_note']}" if ac.get("_borderline") else ""
            candidate_data += (
                f"  {ac['wallet_address']}{borderline_note}\n"
                f"    PnL: +${ac.get('total_pnl_usd', 0):,.0f} | Win rate: {ac.get('win_rate', 0):.0%} | "
                f"Tokens traded: {ac.get('tokens_traded', 0)} | Home runs: {ac.get('home_runs', 0)}\n"
                f"    real_pnl_coverage: {ac.get('real_pnl_coverage', 0):.0%} "
                f"({ac.get('real_pnl_count', 0)}/{ac.get('total_positions', 0)}) | "
                f"rug_exposure: {ac.get('rug_exposure', 0):.0%} "
                f"({ac.get('loss_tokens', 0)}/{ac.get('resolved_tokens', 0)} resolved) | "
                f"unresolved_share: {ac.get('unresolved_share', 0):.0%} "
                f"({ac.get('unresolved_tokens', 0)} unresolved)\n"
                f"    is_sniper_bot: {ac.get('is_sniper_bot', False)} | "
                f"has_funding_data: {ac.get('has_funding_data', False)} | "
                f"last_seen: {ac.get('last_seen', 'unknown')}\n"
            )

    if focus == "forensics" and forensics_data:
        # Forensics mode: verify casefiles instead of allowlist candidates
        user_prompt = f"""{snapshot}

FORENSICS MODE — TOP PnL CASEFILE VERIFICATION

You are verifying forensic casefiles for the top PnL wallets. For each casefile below, verify:
1. Is the leaderboard_truth assessment correct? (realized / mixed / mark_to_market_heavy / contaminated)
2. Is the PnL data real (helius_enhanced) or estimated?
3. Are there contamination signals the casefile missed?
4. Is the best trade data trustworthy?
5. Is the trail status accurate?

DO NOT re-query data that is already in the casefiles. Only query for specific missing facts.

{forensics_data.get('leads', '')}

Output structured JSON at the end with:
```json
{{
  "wallet_reliability": [
    {{
      "address": "FULL_ADDRESS",
      "data_reliable": true,
      "leaderboard_truth": "realized|mixed|mark_to_market_heavy|contaminated",
      "real_pnl_coverage": 0.8,
      "forensics_ready": true,
      "notes": "brief note"
    }}
  ],
  "unreliable_wallets": [{{"address": "FULL_ADDRESS", "reason": "..."}}],
  "report_blockers": ["..."],
  "data_fixes": {{"verdicts_set": 0, "multipliers_fixed": 0, "tags_corrected": 0}}
}}
```"""
    else:
        user_prompt = f"""{snapshot}

QUALITY FLAGS:
{quality_flags}
{multiplier_data}
{pending_data}
{candidate_data}

PRIORITY: Verify allowlist candidate wallets first (check PnL source, sniper bot status, rug exposure, activity recency, funding cache). Then fix multipliers and pending verdicts. Output structured JSON at the end."""

    messages = [{"role": "user", "content": user_prompt}]
    tool_calls = 0
    fixes_applied = 0
    total_input_tokens = 0
    total_output_tokens = 0

    max_iterations = 25
    for iteration in range(max_iterations):
        response = None
        for attempt in range(3):
            try:
                time.sleep(1.5 if attempt == 0 else 10 * (attempt + 1))
                from meridinate.settings import CURRENT_API_SETTINGS
                response = client.messages.create(
                    model=CURRENT_API_SETTINGS.get("intelModel", "claude-sonnet-4-20250514"),
                    max_tokens=CURRENT_API_SETTINGS.get("intelHousekeeperMaxTokens", 8192),
                    system=HOUSEKEEPER_SYSTEM,
                    tools=HOUSEKEEPER_TOOLS,
                    messages=messages,
                )
                break
            except anthropic.RateLimitError:
                log_info(f"[Housekeeper] Rate limited, waiting {10 * (attempt + 2)}s (attempt {attempt + 1}/3)")
                time.sleep(10 * (attempt + 2))
            except Exception as e:
                log_error(f"[Housekeeper] Claude API error: {e}")
                return {"error": str(e), "report": "", "fixes_applied": 0}
        if not response:
            return {"error": "Rate limited after 3 retries", "report": "", "fixes_applied": 0}

        total_input_tokens += response.usage.input_tokens
        total_output_tokens += response.usage.output_tokens
        if on_usage:
            on_usage(response.usage.input_tokens, response.usage.output_tokens, 0, 0)

        # Emit any thinking text
        for block in response.content:
            if hasattr(block, "text") and block.text and on_dialogue:
                on_dialogue("thinking", block.text[:300])

        WRITE_TOOLS = {"fix_token_verdict", "fix_multiplier_tag", "update_wallet_tag"}

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    tool_calls += 1
                    # Emit tool call dialogue
                    if on_dialogue:
                        if block.name == "query_database":
                            on_dialogue("tool_call", f"SQL: {block.input.get('sql', '')[:200]}")
                        elif block.name in WRITE_TOOLS:
                            on_dialogue("fix", f"FIX [{block.name}]: {block.input.get('reason', '')} | {json.dumps({k: v for k, v in block.input.items() if k != 'reason'})[:150]}")
                        else:
                            on_dialogue("tool_call", f"{block.name}: {json.dumps(block.input)[:200]}")

                    result_str = _handle_tool_call(block.name, block.input)
                    # Count fixes from scoped write tools
                    if block.name in WRITE_TOOLS:
                        try:
                            r = json.loads(result_str)
                            if r.get("success") and r.get("rows_affected", 0) > 0:
                                fixes_applied += r["rows_affected"]
                                if on_usage:
                                    on_usage(0, 0, 1, r["rows_affected"])
                            else:
                                if on_usage:
                                    on_usage(0, 0, 1, 0)
                        except Exception:
                            if on_usage:
                                on_usage(0, 0, 1, 0)
                    else:
                        if on_usage:
                            on_usage(0, 0, 1, 0)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_str,
                    })

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

        elif response.stop_reason == "end_turn":
            report_text = ""
            for block in response.content:
                if hasattr(block, "text"):
                    report_text += block.text

            duration = round(time.time() - t0, 1)

            # Extract structured JSON from the report
            structured = _extract_structured_json(report_text)

            log_info(
                f"[Housekeeper] Complete: {fixes_applied} fixes, {tool_calls} queries, "
                f"{total_input_tokens + total_output_tokens} tokens, {duration}s"
                f", structured={'yes' if structured else 'no'}"
            )

            return {
                "report": report_text,
                "structured": structured,
                "fixes_applied": fixes_applied,
                "tool_calls": tool_calls,
                "input_tokens": total_input_tokens,
                "output_tokens": total_output_tokens,
                "duration_seconds": duration,
            }
        else:
            # Truncated — salvage what we have
            report_text = ""
            for block in response.content:
                if hasattr(block, "text"):
                    report_text += block.text
            if report_text:
                log_info(f"[Housekeeper] Response truncated (stop_reason={response.stop_reason}), salvaging {len(report_text)} chars")
                duration = round(time.time() - t0, 1)
                structured = _extract_structured_json(report_text)
                return {
                    "report": report_text,
                    "structured": structured,
                    "fixes_applied": fixes_applied,
                    "tool_calls": tool_calls,
                    "input_tokens": total_input_tokens,
                    "output_tokens": total_output_tokens,
                    "duration_seconds": duration,
                }
            break

    return {"error": "Housekeeper reached max iterations", "report": "", "fixes_applied": 0}
