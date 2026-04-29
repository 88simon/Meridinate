"""
Rug Analysis Agent — Exploratory intelligence for fake chart detection.

Uses your manually labeled tokens (fake/real/unsure) as ground truth to:
1. Evaluate how well the current rug score formula performs
2. Discover new on-chain signals that distinguish fake from real charts
3. Suggest improvements to detection weights and thresholds

The agent has full read access to the Meridinate database and can query
any data to find distinguishing patterns.
"""

import json
import sqlite3
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import anthropic

from meridinate import analyzed_tokens_db as db, settings
from meridinate.observability import log_error, log_info


def _execute_query(sql: str, params: list = None) -> List[Dict]:
    """Execute a read-only SQL query against the Meridinate database."""
    try:
        with db.get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(sql, params or [])
            rows = cursor.fetchall()
            return [dict(r) for r in rows[:200]]
    except Exception as e:
        return [{"error": str(e)}]


TOOLS = [
    {
        "name": "query_database",
        "description": """Execute a read-only SQL query against the Meridinate database.

Key tables for rug analysis:

- analyzed_tokens: id, token_address, token_name, token_symbol, deployer_address,
  market_cap_usd (at scan), market_cap_usd_current, market_cap_ath, liquidity_usd,
  analysis_timestamp, rug_score, rug_score_json, rug_label, rug_label_at,
  clobr_score, clobr_support_usd, clobr_resistance_usd, clobr_sr_ratio,
  lp_trust_score, lp_trust_json, score_composite, score_momentum, score_smart_money,
  score_risk, has_meteora_pool, meteora_creator_linked, bundle_cluster_count,
  bundle_cluster_size, stealth_holder_count, stealth_holder_pct, fresh_wallet_pct,
  controlled_supply_score, fresh_supply_pct, holder_count_latest,
  holder_top1_pct, holder_top10_pct, holder_velocity, deployer_is_top_holder,
  early_buyer_holder_overlap, dex_id, wallets_found, credits_used

- early_buyer_wallets: wallet_address, token_id, total_usd, first_buy_timestamp,
  avg_entry_seconds, wallet_balance_usd, position (order)

- mtew_token_positions: wallet_address, token_id, total_bought_usd, total_sold_usd,
  realized_pnl, still_holding, pnl_source, buy_count, sell_count

- wallet_tags: wallet_address, tag, tier, source

- token_tags: token_id, tag (verified-win, verified-loss, win:Nx, loss:rug, etc.)

- wallet_enrichment_cache: wallet_address, funded_by_json, identity_json

- wallet_leaderboard_cache: wallet_address, total_pnl_usd, tokens_traded, win_rate, home_runs

- quick_dd_runs: token_address, token_id, market_cap_usd, clobr_score, lp_trust_score,
  credits_used, duration_seconds, report_json

Maximum 200 rows per query. Use LIMIT for large tables.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "SQL SELECT query (read-only)"},
                "params": {"type": "array", "items": {"type": "string"}, "description": "Query parameters for ? placeholders"}
            },
            "required": ["sql"]
        }
    },
    {
        "name": "get_token_early_buyers_stats",
        "description": "Get statistical summary of early buyer behavior for a token: buy size distribution, entry timing, wallet age, balance distribution.",
        "input_schema": {
            "type": "object",
            "properties": {
                "token_id": {"type": "integer", "description": "Token ID in analyzed_tokens"}
            },
            "required": ["token_id"]
        }
    },
    {
        "name": "get_deployer_profile",
        "description": "Get deployer info including funding source, other tokens deployed, and win/loss history.",
        "input_schema": {
            "type": "object",
            "properties": {
                "deployer_address": {"type": "string", "description": "Deployer wallet address"}
            },
            "required": ["deployer_address"]
        }
    },
]


def _handle_tool_call(tool_name: str, tool_input: dict) -> str:
    """Handle a tool call from the agent."""
    if tool_name == "query_database":
        sql = tool_input.get("sql", "")
        if any(kw in sql.upper() for kw in ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE"]):
            return json.dumps({"error": "Read-only queries only"})
        params = tool_input.get("params", [])
        result = _execute_query(sql, params)
        return json.dumps(result, default=str)

    elif tool_name == "get_token_early_buyers_stats":
        token_id = tool_input.get("token_id")
        rows = _execute_query("""
            SELECT total_usd, avg_entry_seconds, wallet_balance_usd
            FROM early_buyer_wallets WHERE token_id = ?
        """, [token_id])
        if not rows or "error" in rows[0]:
            return json.dumps({"error": "No data"})

        amounts = [r["total_usd"] or 0 for r in rows]
        entries = [r["avg_entry_seconds"] for r in rows if r["avg_entry_seconds"] is not None]
        balances = [r["wallet_balance_usd"] or 0 for r in rows]

        stats = {
            "buyer_count": len(rows),
            "buy_amounts": {
                "min": round(min(amounts), 2) if amounts else 0,
                "max": round(max(amounts), 2) if amounts else 0,
                "avg": round(sum(amounts) / len(amounts), 2) if amounts else 0,
                "median": round(sorted(amounts)[len(amounts) // 2], 2) if amounts else 0,
                "under_50": sum(1 for a in amounts if a < 50),
                "under_200": sum(1 for a in amounts if a < 200),
                "under_500": sum(1 for a in amounts if a < 500),
                "over_1000": sum(1 for a in amounts if a >= 1000),
                "over_5000": sum(1 for a in amounts if a >= 5000),
            },
            "entry_timing": {
                "avg_seconds": round(sum(entries) / len(entries), 1) if entries else None,
                "under_5s": sum(1 for e in entries if e < 5),
                "under_30s": sum(1 for e in entries if e < 30),
                "under_60s": sum(1 for e in entries if e < 60),
            },
            "wallet_balances": {
                "avg": round(sum(balances) / len(balances), 2) if balances else 0,
                "under_100": sum(1 for b in balances if b < 100),
                "over_10000": sum(1 for b in balances if b >= 10000),
            },
        }
        return json.dumps(stats)

    elif tool_name == "get_deployer_profile":
        deployer = tool_input.get("deployer_address")
        # Funding source
        funding = _execute_query(
            "SELECT funded_by_json FROM wallet_enrichment_cache WHERE wallet_address = ?",
            [deployer]
        )
        funded_by = None
        if funding and funding[0].get("funded_by_json"):
            try:
                funded_by = json.loads(funding[0]["funded_by_json"])
            except Exception:
                pass

        # Other tokens by this deployer
        other_tokens = _execute_query("""
            SELECT t.id, t.token_name, t.market_cap_usd_current, t.rug_score, t.rug_label,
                   (SELECT tag FROM token_tags tt WHERE tt.token_id = t.id AND tag IN ('verified-win', 'verified-loss') LIMIT 1) as verdict
            FROM analyzed_tokens t WHERE t.deployer_address = ? AND (t.deleted_at IS NULL OR t.deleted_at = '')
            ORDER BY t.analysis_timestamp DESC LIMIT 20
        """, [deployer])

        return json.dumps({
            "deployer_address": deployer,
            "funded_by": funded_by,
            "tokens_deployed": len(other_tokens),
            "tokens": other_tokens,
        }, default=str)

    return json.dumps({"error": f"Unknown tool: {tool_name}"})


def run_rug_analysis() -> Dict[str, Any]:
    """
    Run the rug analysis agent against all labeled tokens.
    Returns analysis report with findings and suggested improvements.
    """
    started_at = time.time()

    # Get all labeled tokens
    labeled = _execute_query("""
        SELECT id, token_address, token_name, token_symbol, rug_label, rug_score,
               market_cap_usd, market_cap_usd_current, liquidity_usd,
               deployer_address, clobr_score, lp_trust_score,
               fresh_wallet_pct, bundle_cluster_count, stealth_holder_count,
               holder_count_latest, holder_top1_pct, holder_top10_pct,
               holder_velocity, deployer_is_top_holder, early_buyer_holder_overlap,
               rug_score_json, wallets_found
        FROM analyzed_tokens
        WHERE rug_label IS NOT NULL AND (deleted_at IS NULL OR deleted_at = '')
        ORDER BY rug_label_at DESC
    """)

    if not labeled:
        return {
            "status": "no_data",
            "message": "No labeled tokens found. Label tokens as FAKE/REAL/UNSURE in the Token Leaderboard first.",
        }

    fake_count = sum(1 for t in labeled if t["rug_label"] == "fake")
    real_count = sum(1 for t in labeled if t["rug_label"] == "real")
    unsure_count = sum(1 for t in labeled if t["rug_label"] == "unsure")

    # Build summary for the agent
    summary_lines = []
    for t in labeled:
        score_detail = ""
        if t.get("rug_score_json"):
            try:
                rj = json.loads(t["rug_score_json"])
                triggered = [s["name"] for s in rj.get("signals", []) if s.get("triggered")]
                score_detail = f" signals=[{', '.join(triggered)}]"
            except Exception:
                pass

        summary_lines.append(
            f"  id={t['id']} name={t['token_name']} label={t['rug_label']} "
            f"rug_score={t.get('rug_score', '?')} mc=${t.get('market_cap_usd', 0):,.0f} "
            f"liq=${t.get('liquidity_usd', 0):,.0f} clobr={t.get('clobr_score', '?')} "
            f"lp_trust={t.get('lp_trust_score', '?')} deployer={t.get('deployer_address', '?')[:12]}..."
            f"{score_detail}"
        )

    system_prompt = f"""You are the Rug Analysis Agent for Meridinate, a Solana token intelligence platform.

The user has manually labeled {len(labeled)} tokens:
- {fake_count} labeled FAKE (manufactured/wash-traded price action)
- {real_count} labeled REAL (genuine market interest)
- {unsure_count} labeled UNSURE

Your job is to:
1. EVALUATE: How well does the current rug_score predict the user's labels? Find false positives (score says risky but user said REAL) and false negatives (score says safe but user said FAKE).

2. DISCOVER: Look beyond the current 7 signals. Query the database to find NEW patterns that distinguish FAKE from REAL tokens. Think creatively:
   - What about deployer history? Do serial ruggers have patterns?
   - What about early buyer wallet ages, balances, or tag distributions?
   - What about the ratio of unique wallets to total transactions?
   - What about holder concentration patterns?
   - What about the timing distribution of early buys?
   - What about the relationship between MC at different timepoints?
   - Any other measurable on-chain pattern you can think of?

3. RECOMMEND: Propose specific, measurable changes to the scoring formula — new signals, adjusted weights, new thresholds. Each recommendation must include the exact computation and why it would help.

IMPORTANT: Be exploratory. Don't just validate existing signals — ask "what ELSE can we look at?" Query the database to test hypotheses. Compare distributions between FAKE and REAL tokens.

Current rug score formula (7 signals, max 100 pts):
- vol_liq > 10x with <=3 pools: +20
- tx_density > 40 per $1K MC: +25
- deployer_dust_funding < 1 SOL: +10
- deployer_funder_unknown: +10
- early_buy_pct_under_200 > 50% AND high tx density: +15
- meteora_ghost_pool <$100 liq: +10
- low_pool_count <=3: +10

Labeled tokens:
{chr(10).join(summary_lines)}
"""

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    messages = [{"role": "user", "content": "Analyze the labeled tokens. Evaluate the current rug score accuracy, discover new distinguishing signals by querying the database, and recommend improvements. Be thorough and exploratory — query multiple hypotheses."}]

    report_parts = []
    tool_calls = 0
    input_tokens = 0
    output_tokens = 0
    max_iterations = 30

    for iteration in range(max_iterations):
        try:
            response = client.messages.create(
                model=settings.CURRENT_API_SETTINGS.get("intelModel", "claude-sonnet-4-20250514"),
                max_tokens=8192,
                system=system_prompt,
                tools=TOOLS,
                messages=messages,
            )
        except Exception as e:
            log_error(f"[RugAnalysis] API error: {e}")
            break

        input_tokens += response.usage.input_tokens
        output_tokens += response.usage.output_tokens

        # Process response
        assistant_content = response.content
        messages.append({"role": "assistant", "content": assistant_content})

        if response.stop_reason == "end_turn":
            # Extract text from final response
            for block in assistant_content:
                if hasattr(block, "text"):
                    report_parts.append(block.text)
            break

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in assistant_content:
                if block.type == "tool_use":
                    tool_calls += 1
                    result = _handle_tool_call(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })
                elif hasattr(block, "text") and block.text.strip():
                    report_parts.append(block.text)

            messages.append({"role": "user", "content": tool_results})

    report_text = "\n\n".join(report_parts)
    duration = round(time.time() - started_at, 1)

    result = {
        "report": report_text,
        "tokens_analyzed": len(labeled),
        "fake_count": fake_count,
        "real_count": real_count,
        "unsure_count": unsure_count,
        "tool_calls": tool_calls,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "duration_seconds": duration,
        "generated_at": datetime.now().isoformat(),
    }

    # Persist the report
    try:
        with db.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS rug_analysis_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    report_text TEXT,
                    report_json TEXT,
                    tokens_analyzed INTEGER,
                    fake_count INTEGER,
                    real_count INTEGER,
                    unsure_count INTEGER,
                    tool_calls INTEGER,
                    input_tokens INTEGER,
                    output_tokens INTEGER,
                    duration_seconds REAL,
                    generated_at TIMESTAMP
                )
            """)
            cursor.execute("""
                INSERT INTO rug_analysis_reports (
                    report_text, report_json, tokens_analyzed, fake_count, real_count,
                    unsure_count, tool_calls, input_tokens, output_tokens,
                    duration_seconds, generated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                report_text, json.dumps(result, default=str),
                len(labeled), fake_count, real_count, unsure_count,
                tool_calls, input_tokens, output_tokens, duration, result["generated_at"],
            ))
    except Exception as e:
        log_error(f"[RugAnalysis] Failed to persist report: {e}")

    log_info(f"[RugAnalysis] Complete: {len(labeled)} tokens, {tool_calls} queries, {duration}s")
    return result
