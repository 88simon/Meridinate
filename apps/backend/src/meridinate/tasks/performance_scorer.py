"""
Performance Scoring Engine for Token Categorization.

This module provides rule-based, explainable scoring of tokens
based on their performance metrics (MC, volume, liquidity, holders, etc.).

Buckets:
- Prime (score >= 65): High-quality tokens ready for promotion
- Monitor (score 40-64): Tokens worth watching
- Cull (score < 40): Low-quality tokens
- Excluded: Explicitly flagged/blacklisted tokens
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from meridinate import analyzed_tokens_db as db
from meridinate.observability.structured_logger import log_info, log_error
from meridinate.settings import CURRENT_INGEST_SETTINGS, save_ingest_settings


def get_score_weights() -> Dict[str, int]:
    """Get current score weights from settings."""
    return CURRENT_INGEST_SETTINGS.get("score_weights", {})


def get_bucket_thresholds() -> Tuple[int, int]:
    """Get bucket thresholds (prime, monitor) from settings."""
    prime = CURRENT_INGEST_SETTINGS.get("performance_prime_threshold", 65)
    monitor = CURRENT_INGEST_SETTINGS.get("performance_monitor_threshold", 40)
    return prime, monitor


def score_to_bucket(score: float) -> str:
    """
    Convert a score to a bucket name.

    Args:
        score: Performance score (0-100)

    Returns:
        Bucket name (prime|monitor|cull)
    """
    prime_threshold, monitor_threshold = get_bucket_thresholds()
    if score >= prime_threshold:
        return "prime"
    elif score >= monitor_threshold:
        return "monitor"
    else:
        return "cull"


def calculate_token_score(
    current_snapshot: Dict,
    first_snapshot: Optional[Dict] = None,
    high_win_rate_wallet_count: int = 0,
    age_hours: Optional[float] = None,
) -> Tuple[float, List[Dict]]:
    """
    Calculate performance score for a token based on its snapshots.

    Uses rule-based scoring with configurable weights.

    Args:
        current_snapshot: Current metrics snapshot
        first_snapshot: First recorded snapshot (for momentum calculations)
        high_win_rate_wallet_count: Number of high-win-rate wallets in this token
        age_hours: Token age in hours

    Returns:
        Tuple of (score, list of triggered rules with weights)
    """
    weights = get_score_weights()
    triggered_rules = []
    base_score = 50  # Start at neutral

    # Get values from current snapshot
    mc_usd = current_snapshot.get("mc_usd") or 0
    volume_24h = current_snapshot.get("volume_24h_usd") or 0
    liquidity = current_snapshot.get("liquidity_usd") or 0
    top_holder_share = current_snapshot.get("top_holder_share")
    lp_locked = current_snapshot.get("lp_locked")
    pnl = current_snapshot.get("our_positions_pnl_usd")

    # Get first snapshot values for momentum
    first_mc = first_snapshot.get("mc_usd") if first_snapshot else None
    first_liquidity = first_snapshot.get("liquidity_usd") if first_snapshot else None

    # === MC/Price Momentum Rules ===
    if first_mc and first_mc > 0 and mc_usd > 0:
        mc_change_pct = ((mc_usd - first_mc) / first_mc) * 100

        # MC change >= 50% (approximating 30m momentum)
        if mc_change_pct >= 50:
            weight = weights.get("mc_change_30m_50pct", 15)
            base_score += weight
            triggered_rules.append({
                "rule": "mc_change_30m_50pct",
                "weight": weight,
                "reason": f"MC up {mc_change_pct:.1f}% from first seen",
            })
        # MC change >= 30% (approximating 2h momentum)
        elif mc_change_pct >= 30:
            weight = weights.get("mc_change_2h_30pct", 10)
            base_score += weight
            triggered_rules.append({
                "rule": "mc_change_2h_30pct",
                "weight": weight,
                "reason": f"MC up {mc_change_pct:.1f}% from first seen",
            })

        # Drawdown check (if MC dropped significantly from first seen)
        if mc_change_pct <= -35:
            weight = weights.get("drawdown_35pct", -10)
            base_score += weight
            triggered_rules.append({
                "rule": "drawdown_35pct",
                "weight": weight,
                "reason": f"MC down {abs(mc_change_pct):.1f}% from first seen",
            })

    # === Liquidity Rules ===
    if first_liquidity and first_liquidity > 0 and liquidity > 0:
        liquidity_ratio = liquidity / first_liquidity

        if liquidity_ratio >= 1.3:
            weight = weights.get("liquidity_up_30pct", 10)
            base_score += weight
            triggered_rules.append({
                "rule": "liquidity_up_30pct",
                "weight": weight,
                "reason": f"Liquidity up {(liquidity_ratio - 1) * 100:.1f}%",
            })
        elif liquidity_ratio < 0.6:
            weight = weights.get("liquidity_down_40pct", -15)
            base_score += weight
            triggered_rules.append({
                "rule": "liquidity_down_40pct",
                "weight": weight,
                "reason": f"Liquidity down {(1 - liquidity_ratio) * 100:.1f}%",
            })

    # === Volume Rules ===
    if volume_24h >= 100000:
        weight = weights.get("volume_24h_100k", 10)
        base_score += weight
        triggered_rules.append({
            "rule": "volume_24h_100k",
            "weight": weight,
            "reason": f"High volume: ${volume_24h:,.0f}",
        })
    elif volume_24h < 10000:
        weight = weights.get("volume_24h_10k", -10)
        base_score += weight
        triggered_rules.append({
            "rule": "volume_24h_10k",
            "weight": weight,
            "reason": f"Low volume: ${volume_24h:,.0f}",
        })

    # === Holder Quality Rules ===
    if high_win_rate_wallet_count >= 3:
        weight = weights.get("high_win_rate_3plus", 12)
        base_score += weight
        triggered_rules.append({
            "rule": "high_win_rate_3plus",
            "weight": weight,
            "reason": f"{high_win_rate_wallet_count} high-win-rate wallets",
        })
    elif high_win_rate_wallet_count >= 1:
        weight = weights.get("high_win_rate_1_2", 6)
        base_score += weight
        triggered_rules.append({
            "rule": "high_win_rate_1_2",
            "weight": weight,
            "reason": f"{high_win_rate_wallet_count} high-win-rate wallet(s)",
        })

    if top_holder_share is not None and top_holder_share > 0.45:
        weight = weights.get("top_holder_concentrated", -8)
        base_score += weight
        triggered_rules.append({
            "rule": "top_holder_concentrated",
            "weight": weight,
            "reason": f"Top holder owns {top_holder_share * 100:.1f}%",
        })

    # === Age/Lock Rules ===
    if age_hours is not None and age_hours < 1 and lp_locked is False:
        weight = weights.get("young_unlocked_lp", -10)
        base_score += weight
        triggered_rules.append({
            "rule": "young_unlocked_lp",
            "weight": weight,
            "reason": f"Young token ({age_hours:.1f}h) with unlocked LP",
        })

    # === PnL Feedback Rules ===
    if pnl is not None:
        if pnl > 0:
            weight = weights.get("positions_positive_pnl", 8)
            base_score += weight
            triggered_rules.append({
                "rule": "positions_positive_pnl",
                "weight": weight,
                "reason": f"Our positions profitable: ${pnl:,.2f}",
            })
        elif pnl < 0:
            weight = weights.get("positions_negative_pnl", -8)
            base_score += weight
            triggered_rules.append({
                "rule": "positions_negative_pnl",
                "weight": weight,
                "reason": f"Our positions losing: ${pnl:,.2f}",
            })

    # Clamp score to 0-100
    final_score = max(0, min(100, base_score))

    return final_score, triggered_rules


def score_token(token_address: str) -> Optional[Dict]:
    """
    Score a single token and update its performance data.

    Args:
        token_address: Token address to score

    Returns:
        Dict with score, bucket, explanation or None if no snapshots
    """
    # Get snapshots
    snapshots = db.get_performance_snapshots(token_address, limit=10)
    if not snapshots:
        return None

    current_snapshot = snapshots[0]  # Most recent
    first_snapshot = db.get_first_snapshot(token_address)

    # Get age from ingest queue if available
    age_hours = None
    try:
        from meridinate.analyzed_tokens_db import get_db_connection
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT age_hours FROM token_ingest_queue WHERE token_address = ?",
                (token_address,),
            )
            row = cursor.fetchone()
            if row:
                age_hours = row[0]
    except Exception:
        pass

    # Get high-win-rate wallet count (from MTEW analysis if available)
    high_win_rate_count = 0
    try:
        from meridinate.analyzed_tokens_db import get_db_connection
        with get_db_connection() as conn:
            cursor = conn.cursor()
            # Count wallets with high win rate in this token's analysis
            cursor.execute(
                """
                SELECT COUNT(DISTINCT m.wallet_address)
                FROM multi_token_wallet_metadata m
                JOIN mtew_token_positions p ON m.wallet_address = p.wallet_address
                JOIN analyzed_tokens t ON p.token_id = t.id
                WHERE t.token_address = ?
                AND m.win_rate >= 0.6
            """,
                (token_address,),
            )
            row = cursor.fetchone()
            if row:
                high_win_rate_count = row[0] or 0
    except Exception:
        pass

    # Calculate score
    score, rules = calculate_token_score(
        current_snapshot=current_snapshot,
        first_snapshot=first_snapshot,
        high_win_rate_wallet_count=high_win_rate_count,
        age_hours=age_hours,
    )

    bucket = score_to_bucket(score)
    explanation = json.dumps(rules)

    # Update database
    db.update_token_performance_score(token_address, score, bucket, explanation)
    db.update_ingest_queue_score(token_address, score, bucket)

    return {
        "token_address": token_address,
        "score": score,
        "bucket": bucket,
        "rules": rules,
    }


async def score_tokens(token_addresses: List[str]) -> Dict[str, Any]:
    """
    Score multiple tokens.

    Args:
        token_addresses: List of token addresses to score

    Returns:
        Dict with scoring results
    """
    if not CURRENT_INGEST_SETTINGS.get("score_enabled", False):
        return {
            "status": "disabled",
            "message": "Performance scoring is disabled in settings",
        }

    result = {
        "tokens_scored": 0,
        "tokens_skipped": 0,
        "by_bucket": {"prime": 0, "monitor": 0, "cull": 0},
        "errors": [],
        "started_at": datetime.now().isoformat(),
        "completed_at": None,
    }

    for address in token_addresses:
        try:
            score_result = score_token(address)
            if score_result:
                result["tokens_scored"] += 1
                bucket = score_result["bucket"]
                result["by_bucket"][bucket] = result["by_bucket"].get(bucket, 0) + 1
            else:
                result["tokens_skipped"] += 1
        except Exception as e:
            log_error(f"[Scorer] Error scoring {address}: {e}")
            result["errors"].append(f"{address}: {str(e)}")

    # Update last run timestamp
    CURRENT_INGEST_SETTINGS["last_score_run_at"] = datetime.now().isoformat()
    save_ingest_settings(CURRENT_INGEST_SETTINGS)

    result["completed_at"] = datetime.now().isoformat()
    log_info(
        f"[Scorer] Complete: {result['tokens_scored']} scored, "
        f"{result['tokens_skipped']} skipped, "
        f"Prime={result['by_bucket']['prime']}, "
        f"Monitor={result['by_bucket']['monitor']}, "
        f"Cull={result['by_bucket']['cull']}"
    )

    return result


async def score_all_hot_tokens() -> Dict[str, Any]:
    """
    Score all tokens in the hot refresh window.

    Returns:
        Scoring results
    """
    max_age = CURRENT_INGEST_SETTINGS.get("hot_refresh_age_hours", 48)
    max_tokens = CURRENT_INGEST_SETTINGS.get("hot_refresh_max_tokens", 100)

    # Get hot tokens
    hot_tokens = db.get_hot_ingest_tokens(max_age_hours=max_age, limit=max_tokens)
    addresses = [t["token_address"] for t in hot_tokens]

    log_info(f"[Scorer] Scoring {len(addresses)} hot tokens")
    return await score_tokens(addresses)


async def run_control_cohort_selection() -> Dict[str, Any]:
    """
    Select random low-score tokens for control cohort tracking.

    This helps validate scoring by tracking some tokens that
    would normally be culled to see if they perform well.

    Returns:
        Selection results
    """
    quota = CURRENT_INGEST_SETTINGS.get("control_cohort_daily_quota", 5)
    monitor_threshold = CURRENT_INGEST_SETTINGS.get("performance_monitor_threshold", 40)

    result = {
        "tokens_selected": 0,
        "selected_addresses": [],
        "started_at": datetime.now().isoformat(),
        "completed_at": None,
    }

    try:
        # Get random low-score tokens
        candidates = db.get_random_low_score_tokens(
            max_score=monitor_threshold,
            count=quota,
            exclude_control_cohort=True,
        )

        if candidates:
            addresses = [t["token_address"] for t in candidates]
            marked = db.mark_control_cohort(addresses)
            result["tokens_selected"] = marked
            result["selected_addresses"] = addresses

            log_info(f"[Control Cohort] Selected {marked} tokens for control cohort")

        # Update last run timestamp
        CURRENT_INGEST_SETTINGS["last_control_cohort_run_at"] = datetime.now().isoformat()
        save_ingest_settings(CURRENT_INGEST_SETTINGS)

    except Exception as e:
        log_error(f"[Control Cohort] Error: {e}")
        result["error"] = str(e)

    result["completed_at"] = datetime.now().isoformat()
    return result
