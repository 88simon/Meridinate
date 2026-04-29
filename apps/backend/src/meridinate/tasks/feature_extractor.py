"""
Win Predictor Feature Pipeline

Extracts a feature vector per token for ML classification (win vs loss).
All features are computed from data already in the database — no API calls.

Feature categories:
  1. Market metrics: MC at scan, liquidity, volume ratios
  2. Holder concentration: top1%, top10%, velocity, deployer holding
  3. Smart money: winner/sniper/cluster counts, smart flow direction
  4. Wallet signals: fresh wallet %, early buyer overlap, correlated wallets
  5. Token metadata: mint authority, freeze authority, cashback, dex_id
  6. MC trajectory: volatility, recovery count, ATH multiple
  7. Deployer profile: serial deployer, deployer win rate, deployer token count
"""

import json
import sqlite3
from typing import Dict, List, Any, Optional

from meridinate import analyzed_tokens_db as db
from meridinate.observability import log_error, log_info


def extract_features_for_token(token_id: int) -> Optional[Dict[str, Any]]:
    """
    Extract a flat feature dict for a single token.
    Returns None if token not found or insufficient data.
    """
    with db.get_db_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Token data
        cursor.execute("""
            SELECT id, token_address, token_name, market_cap_usd, market_cap_usd_current,
                   market_cap_ath, liquidity_usd, analysis_timestamp, is_cashback, dex_id,
                   mint_authority_revoked, freeze_authority_active,
                   holder_top1_pct, holder_top10_pct, holder_count_latest,
                   holder_top1_pct_previous, holder_top10_pct_previous, holder_velocity,
                   deployer_is_top_holder, early_buyer_holder_overlap, fresh_wallet_pct,
                   mc_volatility, mc_recovery_count, deployer_address,
                   score_momentum, score_smart_money, score_risk, score_composite,
                   smart_money_flow, avg_hold_hours
            FROM analyzed_tokens
            WHERE id = ? AND (deleted_at IS NULL OR deleted_at = '')
        """, (token_id,))
        row = cursor.fetchone()
        if not row:
            return None
        token = dict(row)

        # Verdict (label)
        cursor.execute(
            "SELECT tag FROM token_tags WHERE token_id = ? AND tag IN ('verified-win', 'verified-loss') LIMIT 1",
            (token_id,)
        )
        verdict_row = cursor.fetchone()
        verdict = verdict_row[0] if verdict_row else None

        # Early buyer wallet stats
        cursor.execute("""
            SELECT COUNT(*) as buyer_count,
                   AVG(total_usd) as avg_buy_usd,
                   MAX(total_usd) as max_buy_usd,
                   MIN(total_usd) as min_buy_usd,
                   AVG(wallet_balance_usd) as avg_wallet_balance
            FROM early_buyer_wallets
            WHERE token_id = ?
        """, (token_id,))
        buyer_stats = dict(cursor.fetchone())

        # Smart money wallet counts
        cursor.execute("""
            SELECT
                SUM(CASE WHEN wt.tag = 'Consistent Winner' THEN 1 ELSE 0 END) as winner_count,
                SUM(CASE WHEN wt.tag = 'Sniper' THEN 1 ELSE 0 END) as sniper_count,
                SUM(CASE WHEN wt.tag = 'Cluster' THEN 1 ELSE 0 END) as cluster_count,
                SUM(CASE WHEN wt.tag = 'Deployer' THEN 1 ELSE 0 END) as deployer_buyer_count,
                SUM(CASE WHEN wt.tag LIKE 'Fresh%%' THEN 1 ELSE 0 END) as fresh_count,
                SUM(CASE WHEN wt.tag = 'Correlated Wallet' THEN 1 ELSE 0 END) as correlated_count,
                SUM(CASE WHEN wt.tag = 'High SOL Balance' THEN 1 ELSE 0 END) as high_value_count
            FROM early_buyer_wallets ebw
            LEFT JOIN wallet_tags wt ON wt.wallet_address = ebw.wallet_address
            WHERE ebw.token_id = ?
        """, (token_id,))
        wallet_tag_counts = dict(cursor.fetchone())

        # Deployer profile (if deployer known)
        deployer_stats = {"deployer_token_count": 0, "deployer_win_rate": None, "deployer_is_serial": False}
        if token.get("deployer_address"):
            cursor.execute("""
                SELECT COUNT(*) as cnt,
                       SUM(CASE WHEN (SELECT tt.tag FROM token_tags tt WHERE tt.token_id = t.id AND tt.tag = 'verified-win' LIMIT 1) IS NOT NULL THEN 1 ELSE 0 END) as wins,
                       SUM(CASE WHEN (SELECT tt.tag FROM token_tags tt WHERE tt.token_id = t.id AND tt.tag = 'verified-loss' LIMIT 1) IS NOT NULL THEN 1 ELSE 0 END) as losses
                FROM analyzed_tokens t
                WHERE t.deployer_address = ? AND (t.deleted_at IS NULL OR t.deleted_at = '')
            """, (token["deployer_address"],))
            dep_row = cursor.fetchone()
            if dep_row:
                total_verdicts = (dep_row[1] or 0) + (dep_row[2] or 0)
                deployer_stats["deployer_token_count"] = dep_row[0] or 0
                deployer_stats["deployer_win_rate"] = (dep_row[1] / total_verdicts) if total_verdicts > 0 else None
                deployer_stats["deployer_is_serial"] = (dep_row[0] or 0) >= 2

            # Check deployer network tag
            cursor.execute(
                "SELECT 1 FROM wallet_tags WHERE wallet_address = ? AND tag = 'Deployer Network' LIMIT 1",
                (token["deployer_address"],)
            )
            deployer_stats["deployer_in_network"] = cursor.fetchone() is not None

    # Parse smart money flow JSON
    smart_flow = {}
    if token.get("smart_money_flow"):
        try:
            smart_flow = json.loads(token["smart_money_flow"]) if isinstance(token["smart_money_flow"], str) else token["smart_money_flow"]
        except Exception:
            pass

    analysis_mc = token.get("market_cap_usd") or 0
    current_mc = token.get("market_cap_usd_current") or analysis_mc
    ath_mc = token.get("market_cap_ath") or analysis_mc
    liquidity = token.get("liquidity_usd") or 0

    features = {
        # === Label ===
        "token_id": token_id,
        "token_name": token.get("token_name"),
        "verdict": verdict,
        "is_win": 1 if verdict == "verified-win" else (0 if verdict == "verified-loss" else None),

        # === Market Metrics ===
        "mc_at_scan": analysis_mc,
        "mc_current": current_mc,
        "mc_ath": ath_mc,
        "mc_ratio": (current_mc / analysis_mc) if analysis_mc > 0 else 1,
        "ath_multiple": (ath_mc / analysis_mc) if analysis_mc > 0 else 1,
        "liquidity_usd": liquidity,
        "liquidity_ratio": (liquidity / current_mc) if current_mc > 0 else 0,

        # === Holder Concentration ===
        "holder_top1_pct": token.get("holder_top1_pct"),
        "holder_top10_pct": token.get("holder_top10_pct"),
        "holder_count": token.get("holder_count_latest"),
        "holder_velocity": token.get("holder_velocity"),
        "deployer_is_top_holder": 1 if token.get("deployer_is_top_holder") else 0,
        "early_buyer_holder_overlap": token.get("early_buyer_holder_overlap") or 0,

        # === Smart Money ===
        "winner_wallet_count": wallet_tag_counts.get("winner_count") or 0,
        "sniper_wallet_count": wallet_tag_counts.get("sniper_count") or 0,
        "cluster_wallet_count": wallet_tag_counts.get("cluster_count") or 0,
        "high_value_wallet_count": wallet_tag_counts.get("high_value_count") or 0,
        "correlated_wallet_count": wallet_tag_counts.get("correlated_count") or 0,
        "smart_money_buying": smart_flow.get("smart_buying", 0),
        "smart_money_selling": smart_flow.get("smart_selling", 0),
        "smart_money_holding": smart_flow.get("smart_holding", 0),
        "smart_flow_direction": 1 if smart_flow.get("flow_direction") == "bullish" else (-1 if smart_flow.get("flow_direction") == "bearish" else 0),

        # === Wallet Signals ===
        "fresh_wallet_pct": token.get("fresh_wallet_pct") or 0,
        "fresh_wallet_count": wallet_tag_counts.get("fresh_count") or 0,
        "deployer_buyer_count": wallet_tag_counts.get("deployer_buyer_count") or 0,
        "buyer_count": buyer_stats.get("buyer_count") or 0,
        "avg_buy_usd": buyer_stats.get("avg_buy_usd") or 0,
        "max_buy_usd": buyer_stats.get("max_buy_usd") or 0,
        "avg_wallet_balance": buyer_stats.get("avg_wallet_balance") or 0,

        # === Token Metadata ===
        "mint_authority_revoked": 1 if token.get("mint_authority_revoked") else 0,
        "freeze_authority_active": 1 if token.get("freeze_authority_active") else 0,
        "is_cashback": 1 if token.get("is_cashback") else 0,
        "is_pumpswap": 1 if token.get("dex_id") == "pumpswap" else 0,

        # === MC Trajectory ===
        "mc_volatility": token.get("mc_volatility") or 0,
        "mc_recovery_count": token.get("mc_recovery_count") or 0,
        "avg_hold_hours": token.get("avg_hold_hours"),

        # === Existing Scores ===
        "score_momentum": token.get("score_momentum"),
        "score_smart_money": token.get("score_smart_money"),
        "score_risk": token.get("score_risk"),
        "score_composite": token.get("score_composite"),

        # === Deployer Profile ===
        "deployer_token_count": deployer_stats["deployer_token_count"],
        "deployer_win_rate": deployer_stats["deployer_win_rate"],
        "deployer_is_serial": 1 if deployer_stats["deployer_is_serial"] else 0,
        "deployer_in_network": 1 if deployer_stats.get("deployer_in_network") else 0,
    }

    return features


def extract_all_features() -> List[Dict[str, Any]]:
    """
    Extract feature vectors for all tokens with verdicts (labeled data).
    Returns list of feature dicts ready for pandas DataFrame / ML training.
    """
    with db.get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT t.id
            FROM analyzed_tokens t
            JOIN token_tags tt ON tt.token_id = t.id AND tt.tag IN ('verified-win', 'verified-loss')
            WHERE t.deleted_at IS NULL OR t.deleted_at = ''
        """)
        token_ids = [row[0] for row in cursor.fetchall()]

    log_info(f"[FeatureExtractor] Extracting features for {len(token_ids)} labeled tokens")

    features = []
    for token_id in token_ids:
        try:
            f = extract_features_for_token(token_id)
            if f and f["is_win"] is not None:
                features.append(f)
        except Exception as e:
            log_error(f"[FeatureExtractor] Error extracting features for token {token_id}: {e}")

    log_info(f"[FeatureExtractor] Extracted {len(features)} feature vectors ({sum(1 for f in features if f['is_win'] == 1)} wins, {sum(1 for f in features if f['is_win'] == 0)} losses)")
    return features


def export_features_csv(output_path: str = "data/ml/features.csv") -> str:
    """
    Export feature vectors to CSV for external ML training.
    Returns the output file path.
    """
    import csv
    import os

    features = extract_all_features()
    if not features:
        log_info("[FeatureExtractor] No features to export")
        return ""

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Exclude non-numeric metadata columns from the feature set
    exclude_cols = {"token_id", "token_name", "verdict"}
    feature_cols = [k for k in features[0].keys() if k not in exclude_cols]

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["token_id", "token_name", "verdict"] + feature_cols)
        writer.writeheader()
        for feat in features:
            writer.writerow(feat)

    log_info(f"[FeatureExtractor] Exported {len(features)} rows × {len(feature_cols)} features to {output_path}")
    return output_path
