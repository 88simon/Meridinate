"""
Meridinate Intel Agent — Bot-Operator Intelligence Classifier

Produces actionable intelligence for a Solana trading bot operator.
Classifies wallets and clusters as: allowlist candidate, denylist candidate,
watch-only, or unclear. Outputs structured JSON alongside prose.

Uses Claude API with database query tools to reason about wallet behavior,
token patterns, and adversarial flow detection.
"""

import json
import re
import sqlite3
import time
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from typing import Any, Dict, List

import anthropic
import traceback

from meridinate import analyzed_tokens_db as db, settings
from meridinate.observability import log_error, log_info


# ============================================================================
# Database Query Tools — what the agent can access
# ============================================================================

def _execute_query(sql: str, params: list = None) -> List[Dict]:
    """Execute a read-only SQL query against the Meridinate database."""
    try:
        with db.get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(sql, params or [])
            rows = cursor.fetchall()
            return [dict(r) for r in rows[:200]]  # cap at 200 rows
    except Exception as e:
        return [{"error": str(e)}]


# Tool definitions for Claude
TOOLS = [
    {
        "name": "query_database",
        "description": """Execute a read-only SQL query against the Meridinate Solana token intelligence database.

Available tables and key columns:

- analyzed_tokens: id, token_address, token_name, token_symbol, deployer_address, market_cap_usd (at scan), market_cap_usd_current, market_cap_ath, liquidity_usd, analysis_timestamp, score_composite, score_momentum, score_smart_money, score_risk, verdict (from token_tags), has_meteora_pool, meteora_creator_linked, bundle_cluster_count, bundle_cluster_size, stealth_holder_count, fresh_wallet_pct, controlled_supply_score, credits_used

- early_buyer_wallets: wallet_address, token_id, total_usd, first_buy_timestamp, avg_entry_seconds, wallet_balance_usd

- mtew_token_positions: wallet_address, token_id, total_bought_usd, total_sold_usd, realized_pnl, still_holding, entry_timestamp, exit_detected_at, last_sell_timestamp, pnl_source, buy_count, sell_count

- wallet_tags: wallet_address, tag, tier, source (tags: Consistent Winner, Consistent Loser, Sniper, Lightning Buyer, Deployer, Fresh at Entry (<24h), Cluster, Sniper Bot, Automated (Nozomi), Bundled (Jito), etc.)

- token_tags: token_id, tag (tags: verified-win, verified-loss, win:3x through win:100x, loss:rug, loss:90, loss:70, loss:dead, loss:stale, meteora-stealth-sell)

- wallet_enrichment_cache: wallet_address, funded_by_json (JSON with funder, funderName, funderType, amount, date, signature), identity_json

- starred_items: item_type (wallet/token), item_address, nametag, starred_at

- wallet_leaderboard_cache: wallet_address, total_pnl_usd, realized_pnl_usd, tokens_traded, tokens_won, tokens_lost, win_rate, home_runs, rugs, tier_score, avg_entry_seconds, avg_hold_hours_7d, wallet_balance_usd

Maximum 200 rows returned per query. Use LIMIT for large tables.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "The SQL SELECT query to execute. Must be read-only (no INSERT/UPDATE/DELETE)."
                },
                "params": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional query parameters for ? placeholders"
                }
            },
            "required": ["sql"]
        }
    },
    {
        "name": "trace_wallet_funding",
        "description": "Get the funding source of a wallet from the enrichment cache. Returns the funder address, name, type, amount, and date. Zero credits — reads from cache.",
        "input_schema": {
            "type": "object",
            "properties": {
                "wallet_address": {
                    "type": "string",
                    "description": "The wallet address to trace funding for"
                }
            },
            "required": ["wallet_address"]
        }
    }
]


def _handle_tool_call(tool_name: str, tool_input: Dict) -> str:
    """Execute a tool call and return the result as a string."""
    if tool_name == "query_database":
        sql = tool_input.get("sql", "")
        # Safety: only allow SELECT
        if not sql.strip().upper().startswith("SELECT"):
            return json.dumps({"error": "Only SELECT queries are allowed"})
        params = tool_input.get("params", [])
        result = _execute_query(sql, params)
        return json.dumps(result, default=str)

    elif tool_name == "trace_wallet_funding":
        addr = tool_input.get("wallet_address", "")
        try:
            with db.get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT funded_by_json FROM wallet_enrichment_cache WHERE wallet_address = ?",
                    (addr,)
                )
                row = cursor.fetchone()
                if row and row[0]:
                    return row[0]
                return json.dumps({"result": "No funding data cached for this wallet"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    return json.dumps({"error": f"Unknown tool: {tool_name}"})


# ============================================================================
# Agent Runner
# ============================================================================

SYSTEM_PROMPT = """You are the Meridinate Intel Agent — a bot-operator intelligence classifier for a Solana memecoin trading platform (SQLite database).

You are producing a BOT-OPERATOR REPORT, not a generic intelligence report. Your goal is to expand allowlists (trusted traders for anti-rug confirmation) and denylists (toxic flow to filter out).

CRITICAL RULES:
- The data in your prompt is ALREADY QUERIED. Do NOT re-query it. Go straight to classification.
- Only use query_database for NEW questions the provided data doesn't answer.
- Use SQLite syntax only. No PostgreSQL features.
- Every query should answer a SPECIFIC question. No exploratory broad scans.
- Convergence is NOT automatically bullish — coordinated behavior can be team support OR adversarial bait flow.
- Do NOT recommend a token buy unless evidence also clears it as not likely adversarial flow.
- Do NOT issue strong conclusions without checking for disconfirming evidence.

ADDRESS FORMATTING:
- NEVER truncate wallet or token addresses. Always output the FULL address (all 32-44 characters).
- Wrong: "8EmAjS1V..." or "64hP97...abc"
- Right: "8EmAjS1VtSBnGivqsJUgpFnDexjGv43G3B7bM1gYpump" (full address)

WALLET RELIABILITY DATA:
You will receive structured reliability data from the Housekeeper with TWO separate labels:
- data_reliable: whether the data is complete enough to reason about (real PnL, sufficient samples)
- trust_quality: whether the wallet is actually trustworthy for allowlist use (high/medium/low)

USE THESE LABELS:
- If data_reliable=false → do not reason about this wallet at all
- If data_reliable=true BUT trust_quality="low" → safe to mention but NOT for allowlist. A wallet with 50-60% rug exposure is data-reliable but NOT trustworthy.
- If trust_quality="medium" → WATCH-ONLY at best, not allowlist
- Only trust_quality="high" wallets should be considered ALLOWLIST CANDIDATES
- If a wallet is a Sniper Bot, check its BOT BEHAVIOR PROFILE before dismissing it.
  A Sniper with 45% win rate and consistent daily PnL is a profitable bot, NOT toxic flow.
  Use the strategy classification (Sniper, Scalper, Accumulator, Runner, Spray Bot) to understand HOW it trades.
  Only classify as denylist if the wallet is genuinely adversarial (rug deployer, sybil, coordinated extraction) — NOT because it's automated

CLASSIFICATION BUCKETS — every major finding MUST end in one of these:
- ALLOWLIST CANDIDATE: wallet is trustworthy enough to use as anti-rug confirmation signal (low rug exposure + high PnL + clean profile)
- CRASH TRADER / PROFITABLE SCALPER: wallet has HIGH rug exposure AND HIGH PnL — they make money trading the chart, not the project. NOT toxic flow. Shadow them, do NOT denylist. Most memecoins die; a profitable scalper will appear on lots of losers because they exit before the dump. Their presence on a token says nothing about token quality, but their behavior is worth observing.
- DENYLIST CANDIDATE: wallet/cluster is genuinely adversarial. Requires rug exposure AND at least one of: clustered with deployer, shared funder with deployer, flat/negative PnL despite high volume, sybil pattern. "High rug exposure alone" is NOT enough — that's a Crash Trader, not toxic flow.
- WATCH-ONLY: interesting but not enough evidence to classify — monitor for repeat behavior
- UNCLEAR: insufficient data to make any determination

DEFAULT-TO-SHADOW RULE: When a wallet shows trading activity but you can't confidently place it in allowlist or denylist, the right answer is almost always Crash Trader / Watch-Only with a monitor_wallet recommendation. Wallet Shadow is zero-cost (WebSocket-based) so the cost of monitoring a wallet that turns out to be uninteresting is near zero. The cost of NOT monitoring a wallet that turns out to be a profitable bot is multiple weeks of lost data accumulation. Bias TOWARD monitoring.

FOR EACH CLASSIFICATION, answer:
- Does this cluster validate a token as likely non-rug, or could it be adversarial bait?
- Should these wallets be tracked as trusted traders, or filtered out?
- Is this signal usable as anti-rug confluence? What would disqualify it?
- When this wallet appears early on a token, what is the downstream outcome pattern?

WORKING SQL EXAMPLES:
-- Check if two wallets share a funder:
SELECT wallet_address, funded_by_json FROM wallet_enrichment_cache WHERE wallet_address IN ('addr1', 'addr2')

-- Find what tokens a wallet bought recently:
SELECT at.token_name, at.token_address, ebw.total_usd, at.analysis_timestamp FROM early_buyer_wallets ebw JOIN analyzed_tokens at ON at.id = ebw.token_id WHERE ebw.wallet_address = 'addr' ORDER BY at.analysis_timestamp DESC LIMIT 10

-- Find wallets that appear in multiple of the same tokens:
SELECT ebw.wallet_address, COUNT(DISTINCT ebw.token_id) as shared_tokens FROM early_buyer_wallets ebw WHERE ebw.token_id IN (1,2,3) GROUP BY ebw.wallet_address HAVING shared_tokens >= 2

-- Check outcome pattern for a wallet's tokens:
SELECT tt.tag, COUNT(*) FROM early_buyer_wallets ebw JOIN token_tags tt ON tt.token_id = ebw.token_id AND tt.tag IN ('verified-win', 'verified-loss') WHERE ebw.wallet_address = 'addr' GROUP BY tt.tag

EVIDENCE DISCIPLINE:
- Do NOT say "classic bait flow" or "coordinated adversarial flow" without listing the specific signals that support it
- Every classification must cite at least one concrete data point (win rate, rug rate, shared funder address, token outcome, entry timing)
- If you cannot cite a specific data point, the classification is UNCLEAR, not a strong conclusion
- "Likely" requires 2+ supporting signals. "Confirmed" requires 3+ with no contradicting signals.

STRUCTURED OUTPUT REQUIREMENT:
After your prose report, you MUST output a JSON block fenced with ```json ... ``` containing:
{
  "allowlist_candidates": [{"address": "full_wallet_address", "confidence": "high|medium|low", "reason": "one sentence", "supporting_signals": ["signal1: value", "signal2: value"], "disqualifying_if": "what would change this classification"}],
  "profitable_scalper_candidates": [{"address": "full_wallet_address", "confidence": "high|medium|low", "reason": "one sentence — explain the high PnL + high rug exposure pattern", "supporting_signals": ["pnl: $X", "rug_exposure: Y%", "avg_hold: Z min", "win_rate: W%"]}],
  "denylist_candidates": [{"address": "full_wallet_address", "type": "toxic_flow|sybil|rug_deployer|deployer_linked|cluster_coordinated", "confidence": "high|medium|low", "reason": "one sentence", "supporting_signals": ["signal1: value", "signal2: value"], "scalper_check": "why this is NOT just a profitable scalper (must address this)"}],
  "watch_only": [{"address": "full_wallet_address", "reason": "one sentence", "monitor_for": "specific behavior to watch", "promote_to": "allowlist|denylist", "promote_when": "condition"}],
  "supporting_tokens": [{"address": "token_address", "name": "token_name", "verdict": "win|loss|pending", "relevance": "why this token matters to the classifications above"}],
  "open_questions": ["specific question that, if answered, would change a classification"],
  "report_confidence": "high|medium|low",
  "confidence_blockers": ["specific reasons confidence is not higher"],
  "recommended_actions": [
    {
      "action_type": "add_bot_denylist_wallet|add_bot_allowlist_wallet|add_watch_wallet|remove_bot_allowlist_wallet|remove_bot_denylist_wallet|remove_watch_wallet|add_intel_tag|add_nametag|queue_wallet_pnl_refresh|queue_wallet_funding_refresh|monitor_wallet|probe_wallet",
      "target_type": "wallet|token",
      "target_address": "FULL_ADDRESS",
      "payload": {},
      "reason": "one sentence justification",
      "confidence": "high|medium|low",
      "expected_bot_effect": "what changes for the bot when this is approved"
    }
  ]
}

IMPORTANT: Every entry in allowlist_candidates and denylist_candidates MUST have supporting_signals with actual data values — not prose descriptions. Example: "win_rate: 67%", "rug_exposure: 12%", "shared_funder: 5Tz9vK2mE8gR4fNpY7aB1cX6dW0hJ9qL3uT5oI8rE2s", "appeared_on_3_verified_losses".

RECOMMENDED ACTIONS:
For every ALLOWLIST CANDIDATE with confidence high or medium, emit: add_bot_allowlist_wallet (auto-shadows on approval)
For every PROFITABLE SCALPER CANDIDATE, emit: monitor_wallet with payload {"label": "Scalper - X% WR / Y% rug"} — these are profitable wallets with high rug exposure that should be observed but NOT trusted as anti-rug signal
For every DENYLIST CANDIDATE with confidence high or medium, emit: add_bot_denylist_wallet — but ONLY if you have at least one signal beyond "high rug exposure" (clustered, deployer-linked, flat PnL, sybil)
For every WATCH-ONLY wallet, emit: add_watch_wallet AND monitor_wallet — watchlist is metadata, monitor_wallet is the actual real-time tracker
For any other wallet that appeared in your data with non-trivial PnL but you couldn't confidently classify, emit: monitor_wallet — default to shadow on uncertainty (zero-cost, weeks of data lost if not monitored)
For wallets with missing PnL data, emit: queue_wallet_pnl_refresh
For wallets with missing funding data, emit: queue_wallet_funding_refresh
For interesting wallets worth naming, emit: add_nametag with payload {"nametag": "descriptive name"}
For Intel-specific flags, emit: add_intel_tag with payload {"tag": "tag_name"}
For wallets with exceptional profiles worth deep reverse-engineering, emit: probe_wallet — this queues a full Bot Probe analysis
These actions are NOT applied immediately — they become proposals that Simon reviews one-by-one.
Only emit actions you are confident enough to defend. Every action needs a reason and expected_bot_effect.

PESSIMISTIC DENYLIST RULE: Before emitting add_bot_denylist_wallet, ask yourself: "Is this wallet just a profitable scalper trading bad tokens?" If you cannot rule that out, downgrade to monitor_wallet. False denylist on a profitable wallet costs more (lost data + lost confluence signal) than a missed denylist (bot still filters via other heuristics).

CONFIDENCE CALIBRATION — report_confidence must reflect reality:
- "high" = ALL of: >10 resolved tokens for key wallets, all allowlist candidates have trust_quality="high", no report_blockers, >3 supporting signals per classification
- "medium" = SOME of: limited sample sizes, some candidates have trust_quality="medium", 1-2 blockers, classifications based on 2 signals
- "low" = ANY of: small verified set (<5 resolved per wallet), tagging may be polluted, candidates have trust_quality="low" or data_reliable=false, weak evidence
- Do NOT say "high" when blockers exist. If you list confidence_blockers, your confidence is at best "medium".
- The prose summary must match the structured section. If the JSON has 4 denylist wallets, do not say "20+ wallets flagged" in prose.

Write your prose with emoji headers. Include full wallet/token addresses. Be specific and actionable — use operator language (add to watchlist, flag as toxic, monitor for repeat) not analyst language (interesting, notable, worth investigating)."""


def _extract_structured_json(text: str) -> Dict[str, Any]:
    """Extract the structured JSON block from agent output."""
    match = re.search(r'```json\s*(\{.*?\})\s*```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            log_error(f"[IntelAgent] Failed to parse structured JSON from output")
    return {}


def _annotate_leads_with_housekeeper(leads_text: str, housekeeper_structured: Dict[str, Any]) -> str:
    """
    Splice each wallet's trust_quality from the Housekeeper into the lead line that
    mentions that wallet. Saves the Investigator from having to cross-reference a
    separate JSON blob (which it usually doesn't).
    """
    if not leads_text:
        return leads_text
    if not housekeeper_structured:
        return leads_text

    reliability = housekeeper_structured.get("wallet_reliability") or []
    unreliable = housekeeper_structured.get("unreliable_wallets") or []

    # Build {address: annotation} map. Unreliable wins over reliability if the same
    # address shows up in both lists.
    annotations: Dict[str, str] = {}
    for entry in reliability:
        addr = (entry.get("address") or "").strip()
        if not addr:
            continue
        trust = (entry.get("trust_quality") or "").upper() or "?"
        data_ok = entry.get("data_reliable")
        data_marker = "data-ok" if data_ok else "data-suspect"
        annotations[addr] = f"   ↳ Housekeeper: trust={trust} | {data_marker}"

    for entry in unreliable:
        addr = (entry.get("address") or "").strip()
        if not addr:
            continue
        reason = (entry.get("reason") or "").strip() or "data quality issue"
        annotations[addr] = f"   ↳ Housekeeper: UNRELIABLE — {reason[:120]}"

    if not annotations:
        return leads_text

    # Append the annotation to each line that mentions a known address.
    # A wallet may appear on multiple lines (convergence + cold + allowlist) — annotate each.
    out_lines = []
    for line in leads_text.splitlines():
        out_lines.append(line)
        for addr, note in annotations.items():
            if addr in line:
                out_lines.append(note)
                break  # one annotation per line is enough
    return "\n".join(out_lines)


def run_intel_report(
    focus: str = "general",
    precomputed_snapshot: str = "",
    precomputed_leads: str = "",
    housekeeper_report: str = "",
    housekeeper_structured: Dict[str, Any] = None,
    on_dialogue=None,
    on_usage=None,
) -> Dict[str, Any]:
    """
    Run the Intel Agent to produce a bot-operator intelligence report.

    Args:
        focus: What to focus on.
        precomputed_snapshot: Pre-computed database snapshot
        precomputed_leads: Pre-computed investigation leads
        housekeeper_report: Housekeeper's prose report (for context)
        housekeeper_structured: Housekeeper's structured JSON output (typed data)

    Returns:
        {report: str, structured: dict, tool_calls: int, tokens_used: int, duration_seconds: float}
    """
    if not settings.ANTHROPIC_API_KEY:
        return {"error": "Anthropic API key not configured", "report": ""}

    t0 = time.time()
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    now = datetime.now(ZoneInfo("America/Chicago")).strftime("%b %d, %Y %I:%M %p %Z")

    # Pull operator-override rules captured by past Reclassify actions. These get
    # appended to the system prompt so the Investigator applies the operator's
    # lessons before its default classification logic.
    rules_block = ""
    try:
        from meridinate.services.override_analyst import get_active_rules, format_rules_for_prompt
        rules = get_active_rules(limit=50)
        if rules:
            rules_block = "\n\n" + format_rules_for_prompt(rules)
            log_info(f"[IntelAgent] Injected {len(rules)} operator-override rules into system prompt")
    except Exception as e:
        log_error(f"[IntelAgent] Failed to load operator rules (non-fatal): {e}")
    system_prompt_with_rules = SYSTEM_PROMPT + rules_block

    # Build context from pre-computation
    context_block = ""
    if precomputed_snapshot:
        context_block += f"\n{precomputed_snapshot}\n"

    # Splice Housekeeper's per-wallet trust_quality directly into each lead line so the
    # Investigator doesn't need to mentally cross-reference a separate JSON blob.
    annotated_leads = _annotate_leads_with_housekeeper(precomputed_leads, housekeeper_structured)
    if annotated_leads:
        context_block += f"\nINVESTIGATION LEADS (pre-computed):\n{annotated_leads}\n"

    # Pass structured housekeeper data (typed JSON, not truncated prose).
    # Even with inline annotation, the structured block carries unreliable_wallets +
    # report_blockers + data_fixes counts that aren't on a per-wallet line.
    if housekeeper_structured:
        context_block += f"\nHOUSEKEEPER WALLET RELIABILITY DATA (structured):\n{json.dumps(housekeeper_structured, indent=2)}\n"
    elif housekeeper_report:
        context_block += f"\nHOUSEKEEPER VERIFICATION REPORT:\n{housekeeper_report}\n"

    focus_instructions = {
        "starred": "Focus on the starred items listed above. For each starred wallet, classify as allowlist/denylist/watch-only. Check recent token outcomes and funding connections.",
        "convergence": """Focus on the convergence alerts. The token data and winner wallets are already listed — do NOT re-query them.
For each convergence: determine whether this is organic smart money alignment or coordinated/adversarial flow.
Check: do the converging wallets share funders? Is the deployer reputable? Are any wallets flagged unreliable by the Housekeeper?
Classify each converging wallet as allowlist candidate, denylist candidate, or watch-only.""",
        "deployer": """Focus on the deployer watch data. Deployers and win rates are already listed.
Classify each deployer network: are the early buyers on their tokens real traders or coordinated clusters?
Check for Meteora pools, linked buyers, and fresh-funded wallets near their launches.""",
        "migrations": """Focus on the cold wallets listed. PnL and funding data are provided.
Use trace_wallet_funding to find forward hops. Check if recipient wallets are active.
Classify migrated wallets: are they allowlist candidates (skilled trader rolling to new wallet) or denylist candidates (rugger moving funds)?""",
        "general": """Investigate ALL the leads provided. The data is already queried — go straight to classification.
Your PRIMARY GOALS:
1. Find wallets worthy of the ALLOWLIST — traders whose early presence on a token signals it's likely not a rug
2. Find wallets/clusters for the DENYLIST — toxic flow, adversarial bait, coordinated rug infrastructure
3. Flag WATCH-ONLY candidates that need more data before classification
For each lead category: read the provided data, make 1-2 targeted follow-up queries, then CLASSIFY.
Do NOT run broad scanning queries. Every query should answer a specific classification question.""",
        "forensics": """TOP PnL FORENSICS MODE. You are analyzing the top PnL wallets on the leaderboard.

The casefiles above contain pre-computed data for each wallet. DO NOT re-query casefile data.

For EACH casefile, you MUST classify the wallet into EXACTLY ONE of these categories:
- repeatable_operator: trades many tokens with consistent edge, realized profits, diversified
- single_home_run: one big win carries the entire PnL, not repeatable
- open_position_mirage: PnL is mostly unrealized/mark-to-market, not real profit yet
- deployer_or_team_linked: wallet is connected to token deployment, insider activity
- coordinated_setup_beneficiary: wallet profited from coordinated/wash trading setup
- wash_amplified: PnL inflated by wash trading or self-dealing
- unclear: not enough data to determine

For each wallet's BEST TRADE, classify the chart:
- organic: natural price action from real demand
- team_supported: price propped up by coordinated buying from related wallets
- wash_amplified: volume/price inflated by wash trades
- deployer_self_buy_setup: deployer or linked wallets creating artificial demand
- extraction_pattern: price pumped specifically to extract from followers/bots
- unclear: insufficient data

Also answer the TRAIL QUESTION for cold/inactive wallets:
- Where did the SOL or proceeds go? Use trace_wallet_funding if needed.
- Did a recipient become active? Should the recipient be watched?

Your JSON output should use this structure instead of the standard allowlist/denylist format:
```json
{
  "forensic_classifications": [
    {
      "address": "FULL_ADDRESS",
      "wallet_type": "repeatable_operator|single_home_run|open_position_mirage|deployer_or_team_linked|coordinated_setup_beneficiary|wash_amplified|unclear",
      "leaderboard_truth": "realized|mixed|mark_to_market_heavy|contaminated",
      "best_trade_chart": "organic|team_supported|wash_amplified|deployer_self_buy_setup|extraction_pattern|unclear",
      "trail_status": "active|cold_migrated|recipient_now_active|trail_ended|unknown",
      "confidence": "high|medium|low",
      "supporting_signals": ["signal: value"],
      "verdict": "copy|watch|ignore|investigate_further",
      "reason": "one sentence summary"
    }
  ],
  "trail_findings": [
    {"source_wallet": "addr", "recipient_wallet": "addr", "status": "active|inactive", "recommendation": "watch|ignore"}
  ],
  "open_questions": ["..."],
  "report_confidence": "high|medium|low",
  "recommended_actions": []
}
```

Be forensic. "Is this leaderboard result real?" is the core question for every casefile.""",
    }

    user_prompt = f"""Current time: {now}
{context_block}

INSTRUCTIONS: {focus_instructions.get(focus, focus_instructions['general'])}

REMINDER: All lead data above is ALREADY QUERIED. Do not re-query it. Only query for NEW information the leads don't contain.
REMINDER: Every finding must end in a classification: ALLOWLIST CANDIDATE, DENYLIST CANDIDATE, WATCH-ONLY, or UNCLEAR.
REMINDER: You MUST include the structured JSON block at the end of your report."""

    messages = [{"role": "user", "content": user_prompt}]
    tool_calls = 0
    total_input_tokens = 0
    total_output_tokens = 0

    # Agent loop — let Claude reason and call tools iteratively
    max_iterations = 20
    for iteration in range(max_iterations):
        # Rate-limit aware API call with retry
        response = None
        for attempt in range(3):
            try:
                time.sleep(1.5 if attempt == 0 else 10 * (attempt + 1))  # pace requests
                from meridinate.settings import CURRENT_API_SETTINGS
                response = client.messages.create(
                    model=CURRENT_API_SETTINGS.get("intelModel", "claude-sonnet-4-20250514"),
                    max_tokens=CURRENT_API_SETTINGS.get("intelMaxTokens", 8192),
                    system=system_prompt_with_rules,
                    tools=TOOLS,
                    messages=messages,
                )
                break
            except anthropic.RateLimitError:
                log_info(f"[IntelAgent] Rate limited, waiting {10 * (attempt + 2)}s (attempt {attempt + 1}/3)")
                time.sleep(10 * (attempt + 2))
            except Exception as e:
                log_error(f"[IntelAgent] Claude API error: {e}")
                return {"error": str(e), "report": "", "tool_calls": tool_calls}
        if not response:
            return {"error": "Rate limited after 3 retries", "report": "", "tool_calls": tool_calls}

        total_input_tokens += response.usage.input_tokens
        total_output_tokens += response.usage.output_tokens
        if on_usage:
            on_usage(response.usage.input_tokens, response.usage.output_tokens, 0)

        # Emit any thinking text
        for block in response.content:
            if hasattr(block, "text") and block.text and on_dialogue:
                on_dialogue("thinking", block.text[:300])

        # Check if the agent wants to use tools
        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    tool_calls += 1
                    if on_dialogue:
                        if block.name == "query_database":
                            on_dialogue("tool_call", f"SQL: {block.input.get('sql', '')[:200]}")
                        elif block.name == "trace_wallet_funding":
                            on_dialogue("tool_call", f"Tracing funding for {block.input.get('wallet_address', '')[:20]}...")
                        else:
                            on_dialogue("tool_call", f"{block.name}: {json.dumps(block.input)[:200]}")
                    if on_usage:
                        on_usage(0, 0, 1)
                    result = _handle_tool_call(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

            # Add assistant response + tool results to conversation
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

        elif response.stop_reason == "end_turn":
            # Agent is done — extract the final text
            report_text = ""
            for block in response.content:
                if hasattr(block, "text"):
                    report_text += block.text

            duration = round(time.time() - t0, 1)

            # Extract structured JSON from the report
            structured = _extract_structured_json(report_text)

            log_info(
                f"[IntelAgent] Report complete: {tool_calls} tool calls, "
                f"{total_input_tokens + total_output_tokens} tokens, {duration}s"
                f", structured={'yes' if structured else 'no'}"
            )

            return {
                "report": report_text,
                "structured": structured,
                "tool_calls": tool_calls,
                "input_tokens": total_input_tokens,
                "output_tokens": total_output_tokens,
                "duration_seconds": duration,
                "focus": focus,
                "generated_at": now,
            }
        else:
            # stop_reason is "max_tokens" or unexpected — salvage whatever text was produced
            report_text = ""
            for block in response.content:
                if hasattr(block, "text"):
                    report_text += block.text
            if report_text:
                log_info(f"[IntelAgent] Response truncated (stop_reason={response.stop_reason}), salvaging {len(report_text)} chars")
                duration = round(time.time() - t0, 1)
                structured = _extract_structured_json(report_text)
                return {
                    "report": report_text + "\n\n⚠️ *Report was truncated due to output length limit.*",
                    "structured": structured,
                    "tool_calls": tool_calls,
                    "input_tokens": total_input_tokens,
                    "output_tokens": total_output_tokens,
                    "duration_seconds": duration,
                    "focus": focus,
                    "generated_at": now,
                }
            break

    return {
        "error": "Agent reached max iterations",
        "report": "",
        "tool_calls": tool_calls,
    }
