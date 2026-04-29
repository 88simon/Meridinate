"""
Market Cap Tracker — Decay-Based Polling

Replaces the old fast/slow lane MC refresh with age-aware polling.
Newer tokens get checked frequently, older tokens decay to less frequent checks.
Dead tokens stop being polled entirely.

Polling intervals by token age:
  0-1h:   every 2 min
  1-6h:   every 5 min
  6-24h:  every 15 min
  1-3d:   every 1 hour
  3-7d:   every 4 hours
  7d+:    every 12 hours
  Dead:   stop polling

Also estimates ATH from DexScreener's 5-minute price change data.
Auto-verdicts are computed inline at every poll.
"""

import json
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional

from meridinate import analyzed_tokens_db as db
from meridinate.observability import log_error, log_info
from meridinate.services.dexscreener_service import get_dexscreener_service
from meridinate.settings import CURRENT_INGEST_SETTINGS

# Win multiplier tiers: (min_multiple, tag)
# Order: highest first so we match the tightest tier
WIN_MULTIPLIER_TIERS = [
    (100, "win:100x"),
    (50, "win:50x"),
    (25, "win:25x"),
    (10, "win:10x"),
    (5, "win:5x"),
    (3, "win:3x"),
]
WIN_MULTIPLIER_TAGS = [tag for _, tag in WIN_MULTIPLIER_TIERS]

# Loss severity tiers
LOSS_TIER_TAGS = ["loss:rug", "loss:90", "loss:70", "loss:dead", "loss:stale"]


# ============================================================================
# MC Trajectory Metrics
# ============================================================================

MC_HISTORY_MAX_ENTRIES = 20


def _update_mc_history(token_id: int, new_mc: float) -> List[dict]:
    """
    Append a new MC reading to the token's mc_history_json and trim to
    the last MC_HISTORY_MAX_ENTRIES entries.

    Returns the updated history list.
    """
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    new_entry = {"mc": new_mc, "timestamp": now_str}

    with db.get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT mc_history_json FROM analyzed_tokens WHERE id = ?", (token_id,))
        row = cursor.fetchone()

        history = []
        if row and row[0]:
            try:
                history = json.loads(row[0])
            except (json.JSONDecodeError, TypeError):
                history = []

        history.append(new_entry)
        # Trim to last N entries
        if len(history) > MC_HISTORY_MAX_ENTRIES:
            history = history[-MC_HISTORY_MAX_ENTRIES:]

        cursor.execute(
            "UPDATE analyzed_tokens SET mc_history_json = ? WHERE id = ?",
            (json.dumps(history), token_id)
        )

    return history


def _compute_mc_volatility(history: List[dict]) -> Optional[float]:
    """
    Compute coefficient of variation from MC history.
    volatility = (std_dev / mean) * 100

    Returns None if fewer than 3 data points.
    """
    mc_values = [entry["mc"] for entry in history if entry.get("mc") and entry["mc"] > 0]
    if len(mc_values) < 3:
        return None

    mean = sum(mc_values) / len(mc_values)
    if mean <= 0:
        return None

    variance = sum((v - mean) ** 2 for v in mc_values) / len(mc_values)
    std_dev = variance ** 0.5
    return round(std_dev / mean * 100, 2)


def _compute_mc_recovery_count(history: List[dict]) -> int:
    """
    Count how many times the MC dropped >30% from a local peak and then
    recovered above that peak.

    A local peak is any point where the MC is higher than both its predecessor
    and successor. We track the highest peak seen and count recoveries above it.
    """
    mc_values = [entry["mc"] for entry in history if entry.get("mc") and entry["mc"] > 0]
    if len(mc_values) < 3:
        return 0

    recoveries = 0
    peak = mc_values[0]
    in_dip = False

    for mc in mc_values[1:]:
        if mc > peak:
            if in_dip:
                recoveries += 1
                in_dip = False
            peak = mc
        elif mc < peak * 0.7:  # Dropped >30% from peak
            in_dip = True

    return recoveries


def update_mc_trajectory_metrics(token_id: int, new_mc: float) -> None:
    """
    Update MC trajectory metrics for a token after a new MC reading.
    Appends to mc_history_json, then recomputes mc_volatility and mc_recovery_count.
    """
    try:
        history = _update_mc_history(token_id, new_mc)
        volatility = _compute_mc_volatility(history)
        recovery_count = _compute_mc_recovery_count(history)

        with db.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE analyzed_tokens
                SET mc_volatility = ?,
                    mc_recovery_count = ?
                WHERE id = ?
            """, (volatility, recovery_count, token_id))

    except Exception as e:
        log_error(f"[MC Tracker] Trajectory metrics error for token {token_id}: {e}")


def get_poll_interval_minutes(age_hours: float) -> int:
    """Get the appropriate poll interval based on token age."""
    if age_hours <= 1:
        return 2
    elif age_hours <= 6:
        return 5
    elif age_hours <= 24:
        return 15
    elif age_hours <= 72:  # 3 days
        return 60
    elif age_hours <= 168:  # 7 days
        return 240
    else:
        return 720  # 12 hours


def _parse_timestamp(ts_str: str) -> Optional[datetime]:
    """Parse ISO or basic timestamp string to datetime."""
    if not ts_str:
        return None
    try:
        if "T" in str(ts_str):
            return datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
        return datetime.strptime(str(ts_str), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _has_open_positions(conn, token_id: int) -> bool:
    """Check if any wallets are still holding this token."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM mtew_token_positions WHERE token_id = ? AND still_holding = 1 LIMIT 1",
        (token_id,)
    )
    return cursor.fetchone() is not None


def get_tokens_due_for_refresh() -> List[Dict]:
    """
    Get all active tokens that are due for an MC refresh based on decay-based intervals.
    Returns tokens sorted by priority (newest first).

    Retirement rules (stop polling):
      1. Dead token: MC < $1k after 24h → auto verified-loss, stop
      2. Finalized + no holders: has verdict AND no open positions → stop
      3. Stale: age > 14 days with no verdict → auto verified-loss, stop
      4. Finalized + old: has verdict AND age > 7 days → slow to 1 check/24h
    """
    with db.get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, token_address, token_name, token_symbol,
                   analysis_timestamp, market_cap_usd, market_cap_usd_current,
                   market_cap_ath, market_cap_ath_timestamp, market_cap_updated_at
            FROM analyzed_tokens
            WHERE (deleted_at IS NULL OR deleted_at = '')
            ORDER BY analysis_timestamp DESC
        """)
        columns = [desc[0] for desc in cursor.description]
        tokens = [dict(zip(columns, row)) for row in cursor.fetchall()]

        # Fetch all verdict tags in one query
        cursor.execute(
            "SELECT token_id, tag FROM token_tags WHERE tag IN ('verified-win', 'verified-loss')"
        )
        verdict_map = {}
        for row in cursor.fetchall():
            verdict_map[row[0]] = row[1]

        # Pre-fetch all token IDs with open positions (avoids N+1 queries in the loop)
        cursor.execute("SELECT DISTINCT token_id FROM mtew_token_positions WHERE still_holding = 1")
        tokens_with_positions = {row[0] for row in cursor.fetchall()}

    now = datetime.now(timezone.utc)
    due_tokens = []

    for token in tokens:
        token_id = token["id"]
        analysis_ts = token.get("analysis_timestamp")
        if not analysis_ts:
            continue

        analysis_time = _parse_timestamp(str(analysis_ts))
        if not analysis_time:
            continue

        age_hours = (now - analysis_time).total_seconds() / 3600
        current_mc = token.get("market_cap_usd_current") or token.get("market_cap_usd") or 0
        verdict = verdict_map.get(token_id)

        # Rule 1: Dead token — MC < $1k after 24h → auto-loss, stop polling
        if current_mc < 1000 and age_hours > 24:
            if not verdict:
                compute_auto_verdict(token_id, token.get("market_cap_usd") or 0, current_mc,
                                     token.get("market_cap_ath") or 0, age_hours)
            continue

        # Rule 2: Has verdict + no open positions → stop polling
        if verdict:
            has_positions = token_id in tokens_with_positions
            if not has_positions:
                # Rule 4: Has verdict + old (>7d) → 1 check per 24h (even with positions)
                # But with no positions, stop entirely
                continue

        # Rule 3: Age > 14 days with no verdict → auto verified-loss, stop
        if not verdict and age_hours > 336:  # 14 days
            compute_auto_verdict(token_id, token.get("market_cap_usd") or 0, current_mc,
                                 token.get("market_cap_ath") or 0, age_hours)
            continue

        # Rule 4: Has verdict + positions + age > 7d → slow to 24h interval
        if verdict and age_hours > 168:
            interval_minutes = 1440  # 24 hours
        else:
            interval_minutes = get_poll_interval_minutes(age_hours)

        # Check if due based on interval
        last_updated = token.get("market_cap_updated_at")
        if last_updated:
            last_update_time = _parse_timestamp(str(last_updated))
            if last_update_time:
                minutes_since_update = (now - last_update_time).total_seconds() / 60
                if minutes_since_update < interval_minutes:
                    continue  # Not due yet

        token["age_hours"] = age_hours
        token["interval_minutes"] = interval_minutes
        due_tokens.append(token)

    return due_tokens


def estimate_ath_from_price_change(current_mc: float, price_change_m5: Optional[float]) -> Optional[float]:
    """
    Estimate a higher ATH from DexScreener's 5-minute price change.
    If price dropped 50% in 5 min, the MC was 2x higher 5 minutes ago.
    """
    if not price_change_m5 or not current_mc or current_mc <= 0:
        return None

    if price_change_m5 < -1:  # Price dropped — MC was higher recently
        # price_change_m5 is a percentage, e.g., -50 means dropped 50%
        # If current = 100 and change = -50%, then 5 min ago = 100 / (1 + (-50/100)) = 100 / 0.5 = 200
        try:
            factor = 1 + (price_change_m5 / 100)
            if factor > 0:
                estimated_peak = current_mc / factor
                return estimated_peak
        except Exception:
            pass

    return None


def compute_auto_verdict(token_id: int, original_mc: float, current_mc: float,
                         ath_mc: float, age_hours: float) -> Optional[str]:
    """
    Compute auto-verdict based on MC performance. Returns 'verified-win', 'verified-loss', or None.
    Does not overwrite existing manual (tier=3) verdicts.

    Win rules:
      1. ATH >= 3x original AND current >= 1x original (must still be at break-even)
      2. ATH >= 1.5x original AND current >= 1.5x original

    Loss rules:
      1. age >= 6h AND current < 0.1x original (90%+ loss with 6-hour age gate)
      2. age >= 72h AND current < 0.3x original (70%+ loss after 3 days)
      3. current < $1000 AND age >= 24h (dead token auto-loss)
    """
    if not original_mc or original_mc <= 0:
        return None

    # Check for existing manual verdict
    with db.get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT 1 FROM token_tags WHERE token_id = ? AND tag IN ('verified-win', 'verified-loss') AND tier = 3",
            (token_id,)
        )
        if cursor.fetchone():
            return None  # Don't overwrite manual verdict

    verdict = None
    loss_tier = None

    # Win conditions
    if ath_mc and ath_mc >= original_mc * 3 and current_mc >= original_mc:
        verdict = "verified-win"
    elif ath_mc and ath_mc >= original_mc * 1.5 and current_mc >= original_mc * 1.5:
        verdict = "verified-win"

    # Loss conditions (with severity tiers)
    if not verdict:
        loss_pct = (1 - current_mc / original_mc) * 100 if original_mc > 0 else 0

        if age_hours <= 1 and loss_pct >= 95:
            # 95%+ drop within 1 hour = rug pull
            verdict = "verified-loss"
            loss_tier = "loss:rug"
        elif age_hours >= 6 and current_mc < original_mc * 0.1:
            verdict = "verified-loss"
            loss_tier = "loss:90"
        elif age_hours >= 72 and current_mc < original_mc * 0.3:
            verdict = "verified-loss"
            loss_tier = "loss:70"
        elif current_mc < 1000 and age_hours >= 24:
            verdict = "verified-loss"
            loss_tier = "loss:dead"
        elif age_hours >= 336:
            verdict = "verified-loss"
            loss_tier = "loss:stale"

    if verdict:
        with db.get_db_connection() as conn:
            cursor = conn.cursor()
            # Remove existing auto-verdicts, win multiplier tags, and loss tier tags
            cursor.execute(
                "DELETE FROM token_tags WHERE token_id = ? AND tag IN ('verified-win', 'verified-loss') AND tier = 1",
                (token_id,)
            )
            # Remove ALL win:* and loss:* tags (granular multipliers + old fixed tiers)
            cursor.execute(
                "DELETE FROM token_tags WHERE token_id = ? AND (tag LIKE 'win:%' OR tag LIKE 'loss:%')",
                (token_id,)
            )
            # Insert verdict
            cursor.execute(
                "INSERT OR IGNORE INTO token_tags (token_id, tag, tier, source, updated_at) VALUES (?, ?, 1, 'auto:mc-performance', CURRENT_TIMESTAMP)",
                (token_id, verdict)
            )
            # Insert win multiplier tag (granular — actual multiple rounded down)
            if verdict == "verified-win" and ath_mc and original_mc > 0:
                multiple = ath_mc / original_mc
                rounded = int(multiple)  # floor to integer
                if rounded >= 3:
                    tag = f"win:{rounded}x"
                    cursor.execute(
                        "INSERT OR IGNORE INTO token_tags (token_id, tag, tier, source, updated_at) VALUES (?, ?, 1, 'auto:mc-performance', CURRENT_TIMESTAMP)",
                        (token_id, tag)
                    )
            # Insert loss tier tag
            if verdict == "verified-loss" and loss_tier:
                cursor.execute(
                    "INSERT OR IGNORE INTO token_tags (token_id, tag, tier, source, updated_at) VALUES (?, ?, 1, 'auto:mc-performance', CURRENT_TIMESTAMP)",
                    (token_id, loss_tier)
                )

    return verdict


def run_mc_tracker() -> Dict[str, Any]:
    """
    Run the decay-based MC tracker. Fully synchronous — safe to run in a thread.

    1. Gets all tokens due for refresh based on age-decay intervals
    2. Fetches current MC from DexScreener (free)
    3. Estimates ATH from 5-min price change
    4. Updates database
    5. Computes auto-verdicts inline
    """
    result = {
        "tokens_checked": 0,
        "tokens_updated": 0,
        "tokens_dead": 0,
        "verdicts_computed": 0,
        "ath_improved": 0,
        "started_at": datetime.now().isoformat(),
        "completed_at": None,
    }

    try:
        due_tokens = get_tokens_due_for_refresh()
        result["tokens_due"] = len(due_tokens)

        if not due_tokens:
            log_info("[MC Tracker] No tokens due for refresh")
            result["completed_at"] = datetime.now().isoformat()
            return result

        log_info(f"[MC Tracker] {len(due_tokens)} tokens due for refresh")

        dexscreener = get_dexscreener_service()

        # CLOBr enrichment setup (if enabled)
        clobr_svc = None
        clobr_positions = set()
        if CURRENT_INGEST_SETTINGS.get("clobr_enabled"):
            from meridinate.services.clobr_service import get_clobr_service
            clobr_svc = get_clobr_service()
            if clobr_svc:
                with db.get_db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT DISTINCT token_id FROM mtew_token_positions WHERE still_holding = 1")
                    clobr_positions = {row[0] for row in cursor.fetchall()}

        for token in due_tokens:
            token_id = token["id"]
            address = token["token_address"]
            original_mc = token.get("market_cap_usd") or 0
            current_ath = token.get("market_cap_ath") or original_mc
            age_hours = token.get("age_hours", 0)

            try:
                # Get full snapshot from DexScreener (free)
                snapshot = dexscreener.get_token_snapshot(address)
                if not snapshot:
                    result["tokens_checked"] += 1
                    continue

                new_mc = snapshot.get("market_cap_usd")
                if new_mc is None:
                    result["tokens_checked"] += 1
                    continue

                result["tokens_checked"] += 1

                # Get liquidity (also from DexScreener, free)
                new_liquidity = snapshot.get("liquidity_usd")

                # Estimate ATH from 5-minute price change
                price_change_m5 = snapshot.get("price_change_m5") or snapshot.get("price_change_h1")
                estimated_peak = estimate_ath_from_price_change(new_mc, price_change_m5)

                # Determine true ATH
                new_ath = current_ath
                ath_timestamp = None
                candidates = [c for c in [current_ath, new_mc, estimated_peak] if c and c > 0]
                if candidates:
                    true_highest = max(candidates)
                    if true_highest > (current_ath or 0):
                        new_ath = true_highest
                        ath_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                        result["ath_improved"] += 1

                # Update database
                with db.get_db_connection() as conn:
                    cursor = conn.cursor()
                    if ath_timestamp:
                        cursor.execute("""
                            UPDATE analyzed_tokens
                            SET market_cap_usd_previous = market_cap_usd_current,
                                market_cap_usd_current = ?,
                                market_cap_ath = ?,
                                market_cap_ath_timestamp = ?,
                                liquidity_usd = COALESCE(?, liquidity_usd),
                                market_cap_updated_at = CURRENT_TIMESTAMP
                            WHERE id = ?
                        """, (new_mc, new_ath, ath_timestamp, new_liquidity, token_id))
                    else:
                        cursor.execute("""
                            UPDATE analyzed_tokens
                            SET market_cap_usd_previous = market_cap_usd_current,
                                market_cap_usd_current = ?,
                                liquidity_usd = COALESCE(?, liquidity_usd),
                                market_cap_updated_at = CURRENT_TIMESTAMP
                            WHERE id = ?
                        """, (new_mc, new_liquidity, token_id))

                result["tokens_updated"] += 1

                # CLOBr liquidity enrichment (score for all, depth for position-tracked)
                if clobr_svc and new_mc >= 5000:  # Skip dead/micro tokens
                    try:
                        has_pos = token_id in clobr_positions
                        clobr_data = clobr_svc.enrich_token(address, has_positions=has_pos)
                        if clobr_data:
                            with db.get_db_connection() as clobr_conn:
                                c = clobr_conn.cursor()
                                if has_pos and "support_usd" in clobr_data:
                                    c.execute("""
                                        UPDATE analyzed_tokens
                                        SET clobr_score = ?, clobr_support_usd = ?,
                                            clobr_resistance_usd = ?, clobr_sr_ratio = ?,
                                            clobr_updated_at = CURRENT_TIMESTAMP
                                        WHERE id = ?
                                    """, (clobr_data["clobr_score"], clobr_data["support_usd"],
                                          clobr_data["resistance_usd"], clobr_data["sr_ratio"], token_id))
                                else:
                                    c.execute("""
                                        UPDATE analyzed_tokens
                                        SET clobr_score = ?, clobr_updated_at = CURRENT_TIMESTAMP
                                        WHERE id = ?
                                    """, (clobr_data["clobr_score"], token_id))
                            result["clobr_enriched"] = result.get("clobr_enriched", 0) + 1
                    except Exception as clobr_err:
                        log_error(f"[MC Tracker] CLOBr enrichment failed for {address[:12]}: {clobr_err}")

                # Update MC trajectory metrics (history, volatility, recovery count)
                update_mc_trajectory_metrics(token_id, new_mc)

                # Check if dead
                if new_mc < 1000:
                    result["tokens_dead"] += 1

                # Compute auto-verdict inline
                verdict = compute_auto_verdict(token_id, original_mc, new_mc, new_ath, age_hours)
                if verdict:
                    result["verdicts_computed"] += 1
                    log_info(f"[MC Tracker] Auto-verdict for {token.get('token_name', '?')}: {verdict} (ATH {new_ath/original_mc:.1f}x)" if original_mc > 0 else f"[MC Tracker] Auto-verdict: {verdict}")

                # Meteora stealth-sell detection (Phase 1 is free from snapshot data)
                meteora_pools = snapshot.get("meteora_pools", [])
                if meteora_pools and (not token.get("has_meteora_pool") or not token.get("meteora_lp_activity_json")):
                    try:
                        from meridinate.services.meteora_detector import process_token_meteora
                        from meridinate.settings import HELIUS_API_KEY
                        met_result = process_token_meteora(
                            token_id, address,
                            token.get("deployer_address"),
                            meteora_pools, HELIUS_API_KEY,
                        )
                        if met_result.get("detected"):
                            result["credits_used"] = result.get("credits_used", 0) + met_result.get("credits_used", 0)
                            log_info(
                                f"[MC Tracker] Meteora pool detected for {token.get('token_name', '?')}: "
                                f"{met_result.get('lp_events', 0)} LP events, "
                                f"{'LINKED' if met_result.get('linked') else 'unlinked'} to insiders"
                            )
                    except Exception as met_err:
                        log_error(f"[MC Tracker] Meteora detection failed for {address[:12]}: {met_err}")

            except Exception as e:
                log_error(f"[MC Tracker] Error refreshing {address}: {e}")

        # Invalidate tokens cache
        try:
            from meridinate.routers.tokens import cache as tokens_cache
            tokens_cache.invalidate("tokens_history")
        except Exception:
            pass

        result["completed_at"] = datetime.now().isoformat()
        log_info(
            f"[MC Tracker] Complete: {result['tokens_updated']}/{result['tokens_checked']} updated, "
            f"{result['ath_improved']} ATH improved, {result['verdicts_computed']} verdicts, "
            f"{result['tokens_dead']} dead"
        )

        # Run token scoring after MC refresh (no extra API calls for scores, metadata fetched only once)
        try:
            from meridinate.tasks.token_scorer import score_all_tokens
            from meridinate.settings import HELIUS_API_KEY
            score_result = score_all_tokens(HELIUS_API_KEY, fetch_metadata=True)
            result["tokens_scored"] = score_result.get("tokens_scored", 0)
            result["scoring_credits"] = score_result.get("credits_used", 0)
        except Exception as e:
            log_error(f"[MC Tracker] Scoring failed: {e}")

        # Log operation
        from meridinate.credit_tracker import get_credit_tracker
        get_credit_tracker().record_operation(
            operation="mc_tracker", label="MC Tracker",
            credits=result.get("scoring_credits", 0), call_count=result["tokens_checked"],
            context={"updated": result["tokens_updated"], "verdicts": result["verdicts_computed"],
                     "scored": result.get("tokens_scored", 0)},
        )

    except Exception as e:
        log_error(f"[MC Tracker] Fatal error: {e}")
        result["completed_at"] = datetime.now().isoformat()

    return result
