"""
Override Analyst — Operator Feedback Rule Extractor

When the operator reclassifies an Intel recommendation, this service runs a
single-shot Anthropic call that turns the override into a structured rule the
next Intel run can learn from. The rule is stored in intel_agent_rules and
injected into the Investigator's system prompt at the next run.

Scope: this is a small, narrow agent. It does NOT do its own database work —
it receives the relevant wallet snapshot from the caller. Keeping it tool-less
means it always returns in one call.
"""

import json
import re
import sqlite3
from datetime import datetime
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

import anthropic

from meridinate import analyzed_tokens_db as db, settings
from meridinate.observability import log_error, log_info

CHICAGO_TZ = ZoneInfo("America/Chicago")


# Operator-facing categories. Keep this list short and concrete — the dropdown
# is the whole point of the design (no airtight prose required from the operator).
OVERRIDE_CATEGORIES = {
    "profitable_bot_misread_as_toxic": "Actually a profitable bot — Intel misread rug exposure / automation as toxic flow",
    "missed_cluster_or_sybil": "Coordinated team / sybil — Intel missed the cluster signal",
    "stale_data": "Stale data — Intel didn't see recent activity",
    "wrong_category_strength": "Wrong category strength — should be watch/monitor, not allowlist or denylist",
    "sample_too_small": "Sample too small — Intel was overconfident on insufficient data",
    "deployer_or_team_link": "Deployer- or team-linked — Intel missed the link, this should be denylist",
    "other": "Other (use note field)",
}


SYSTEM_PROMPT = """You are the Override Analyst for the Meridinate Intel pipeline.

The Investigator agent classified a wallet, and the operator just corrected it. Your job is to extract a single generalizable rule from this correction so the next Investigator run won't make the same mistake on a similar wallet.

You output ONE structured JSON object. No prose, no preamble. Just the JSON.

Schema:
{
  "trigger_signal": "Concise condition expressed in data terms — what pattern in the wallet's profile causes Intel to make this mistake. Example: 'rug_exposure > 80% AND realized_pnl > 10000'",
  "wrong_conclusion": "What Intel concluded (one phrase). Example: 'toxic_flow_denylist'",
  "correct_conclusion": "What Intel should have concluded (one phrase). Example: 'profitable_scalper_monitor'",
  "rule_text": "A single sentence the Investigator should remember. Example: 'High rug exposure with positive realized PnL = scalper trading the chart, not adversarial flow.'",
  "example_evidence": "The specific data points from this wallet that support the correct classification. Example: 'PnL +$47K across 38 helius_enhanced positions, 4min avg hold, 97% rug exposure'"
}

Rules for the rule:
- The rule must generalize beyond this one wallet. Don't write 'wallet 64hP97 is good' — write the pattern.
- Anchor on measurable signals (PnL, hold time, win rate, rug exposure, cluster tags, funder data). Avoid vibes.
- One rule per override. If you see two patterns, pick the dominant one — the operator's category tells you which.
- If the operator chose 'other' and the note is vague, do your best with the data provided.
"""


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    """Pull the first JSON object out of the model output."""
    # Try fenced first
    fenced = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass
    # Fall back to first {...} block
    raw = re.search(r"(\{.*\})", text, re.DOTALL)
    if raw:
        try:
            return json.loads(raw.group(1))
        except json.JSONDecodeError:
            pass
    return None


def _fetch_wallet_snapshot(wallet_address: str) -> Dict[str, Any]:
    """Pull the data the Override Analyst needs to write a generalizable rule."""
    with db.get_db_connection() as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        leaderboard = c.execute(
            """SELECT total_pnl_usd, realized_pnl_usd, tokens_traded, tokens_won,
                      tokens_lost, win_rate, home_runs, rugs, avg_entry_seconds,
                      avg_hold_hours_7d, wallet_balance_usd, tags_json
               FROM wallet_leaderboard_cache WHERE wallet_address = ?""",
            (wallet_address,),
        ).fetchone()

        positions = c.execute(
            """SELECT COUNT(*) AS total,
                      SUM(CASE WHEN pnl_source = 'helius_enhanced' THEN 1 ELSE 0 END) AS helius,
                      AVG(CASE WHEN still_holding = 0 AND entry_timestamp IS NOT NULL
                              AND COALESCE(last_sell_timestamp, exit_detected_at) IS NOT NULL
                          THEN (julianday(COALESCE(last_sell_timestamp, exit_detected_at))
                                - julianday(entry_timestamp)) * 24 * 60
                          END) AS avg_hold_minutes
               FROM mtew_token_positions WHERE wallet_address = ?""",
            (wallet_address,),
        ).fetchone()

        rug = c.execute(
            """SELECT COUNT(*) AS total_resolved,
                      SUM(CASE WHEN tt.tag = 'verified-loss' THEN 1 ELSE 0 END) AS losses,
                      SUM(CASE WHEN tt.tag = 'verified-win' THEN 1 ELSE 0 END) AS wins
               FROM early_buyer_wallets eb
               JOIN token_tags tt ON tt.token_id = eb.token_id
                   AND tt.tag IN ('verified-win', 'verified-loss')
               WHERE eb.wallet_address = ?""",
            (wallet_address,),
        ).fetchone()

        tags = [r["tag"] for r in c.execute(
            "SELECT tag FROM wallet_tags WHERE wallet_address = ?",
            (wallet_address,),
        ).fetchall()]

        funding = c.execute(
            "SELECT funded_by_json FROM wallet_enrichment_cache WHERE wallet_address = ?",
            (wallet_address,),
        ).fetchone()

    snapshot = {
        "wallet_address": wallet_address,
        "leaderboard": dict(leaderboard) if leaderboard else None,
        "positions": dict(positions) if positions else None,
        "rug_resolution": dict(rug) if rug else None,
        "tags": tags,
        "funding_json": funding[0] if funding and funding[0] else None,
    }
    return snapshot


def extract_rule_from_override(
    recommendation: Dict[str, Any],
    new_action_type: str,
    operator_category: str,
    operator_note: str = "",
) -> Optional[Dict[str, Any]]:
    """
    Run the Override Analyst on a single override and persist the resulting rule.

    Args:
        recommendation: the original (now overridden) intel_recommendations row
        new_action_type: the action the operator picked instead
        operator_category: key from OVERRIDE_CATEGORIES
        operator_note: optional one-line clarification (especially when category='other')

    Returns:
        The rule dict that was stored, or None if extraction failed.
        Failure is non-fatal — the override still completes; we just lose the rule.
    """
    if not settings.ANTHROPIC_API_KEY:
        log_error("[OverrideAnalyst] No Anthropic API key configured — skipping rule extraction")
        return None

    target = recommendation.get("target_address", "")
    if not target:
        return None

    snapshot = _fetch_wallet_snapshot(target)

    category_label = OVERRIDE_CATEGORIES.get(operator_category, operator_category)

    user_prompt = f"""ORIGINAL INTEL RECOMMENDATION (now overridden):
- Action: {recommendation.get('action_type')}
- Target: {target}
- Reason given by Investigator: {recommendation.get('reason', '')}
- Confidence: {recommendation.get('confidence', '')}
- Expected effect: {recommendation.get('expected_bot_effect', '')}

OPERATOR OVERRIDE:
- Replaced with action: {new_action_type}
- Category: {operator_category} — {category_label}
- Operator note: {operator_note or '(none)'}

WALLET SNAPSHOT (data the Investigator had access to):
{json.dumps(snapshot, indent=2, default=str)}

Output the rule JSON now."""

    try:
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        from meridinate.settings import CURRENT_API_SETTINGS
        response = client.messages.create(
            model=CURRENT_API_SETTINGS.get("intelModel", "claude-sonnet-4-20250514"),
            max_tokens=600,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        text = "".join(b.text for b in response.content if hasattr(b, "text"))
        rule = _extract_json(text)
    except Exception as e:
        log_error(f"[OverrideAnalyst] Anthropic call failed: {e}")
        return None

    if not rule:
        log_error(f"[OverrideAnalyst] Failed to parse JSON from model output for rec {recommendation.get('id')}")
        return None

    # Persist the rule. If the table doesn't exist yet we can't help — but
    # ensure_tables runs at startup so this is a non-issue in practice.
    now = datetime.now(CHICAGO_TZ).strftime("%Y-%m-%d %H:%M:%S %Z")
    try:
        with db.get_db_connection() as conn:
            conn.execute(
                """INSERT INTO intel_agent_rules (
                       source_recommendation_id, source_report_id, target_address,
                       operator_category, operator_note, original_action_type,
                       corrected_action_type, trigger_signal, wrong_conclusion,
                       correct_conclusion, rule_text, example_evidence, created_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    recommendation.get("id"),
                    recommendation.get("report_id"),
                    target,
                    operator_category,
                    operator_note,
                    recommendation.get("action_type"),
                    new_action_type,
                    rule.get("trigger_signal", ""),
                    rule.get("wrong_conclusion", ""),
                    rule.get("correct_conclusion", ""),
                    rule.get("rule_text", ""),
                    rule.get("example_evidence", ""),
                    now,
                ),
            )
        log_info(
            f"[OverrideAnalyst] Stored rule for rec {recommendation.get('id')} "
            f"({operator_category}): {rule.get('rule_text', '')[:100]}"
        )
    except Exception as e:
        log_error(f"[OverrideAnalyst] Failed to persist rule: {e}")
        return None

    return rule


def get_active_rules(limit: int = 50) -> list:
    """
    Fetch the most-recent active operator override rules. Used to inject lessons
    into the Investigator's system prompt at the next run.
    """
    try:
        with db.get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM intel_agent_rules
                   WHERE active = 1
                   ORDER BY created_at DESC
                   LIMIT ?""",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        log_error(f"[OverrideAnalyst] Failed to fetch rules: {e}")
        return []


def format_rules_for_prompt(rules: list) -> str:
    """Compact, prompt-ready representation of the override rules."""
    if not rules:
        return ""
    lines = [
        "=== OPERATOR OVERRIDE RULES (lessons from past corrections) ===",
        "These are rules extracted from past operator corrections. Apply them BEFORE",
        "your default classification logic. If a wallet matches a trigger_signal,",
        "use the correct_conclusion, NOT the default rule.",
        "",
    ]
    for r in rules:
        lines.append(f"- WHEN {r.get('trigger_signal', '?')}")
        lines.append(f"  THEN: {r.get('correct_conclusion', '?')} (NOT {r.get('wrong_conclusion', '?')})")
        lines.append(f"  RULE: {r.get('rule_text', '?')}")
        if r.get("example_evidence"):
            lines.append(f"  PRIOR EXAMPLE: {r['example_evidence']}")
        lines.append("")
    return "\n".join(lines)
