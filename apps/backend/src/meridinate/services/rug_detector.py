"""
Rug Score Detector — Fake chart detection from measurable on-chain signals.

Computes a 0-100 rug risk score based on signals derived from analyzing
confirmed fake charts. Higher score = more likely to be manufactured price action.

Signals (derived from empirical analysis of confirmed rugs vs organic tokens):
  1. Volume/Liquidity ratio (wash trading indicator)
  2. Tx density per $1K MC (artificial activity)
  3. Deployer funding amount (throwaway wallet)
  4. Deployer funder identity (unknown = suspicious)
  5. Early buyer size distribution (scattered tiny buys)
  6. Meteora ghost pool (stealth exit route)
  7. Pool count (organic tokens attract independent LPs)

Zero extra credits — computed entirely from data already fetched during analysis.
"""

from typing import Any, Dict, List, Optional

from meridinate.observability import log_info


def compute_rug_score(
    volume_24h: float = 0,
    liquidity_usd: float = 0,
    txs_24h: int = 0,
    market_cap_usd: float = 0,
    deployer_fund_amount: Optional[float] = None,
    deployer_funder_type: Optional[str] = None,
    early_buyers: Optional[List[Dict]] = None,
    pool_count: int = 1,
    has_meteora_ghost: bool = False,
) -> Dict[str, Any]:
    """
    Compute rug risk score from token metrics.

    Returns:
        {
            rug_score: int (0-100, higher = more likely fake),
            signals: [{name, triggered, points, value, threshold, detail}],
            verdict: "HIGH_RISK" | "MODERATE" | "LOW",
        }
    """
    signals = []
    total_score = 0

    # === Signal 1: Volume/Liquidity ratio ===
    # Wash trading produces volume far exceeding actual liquidity
    # BUT only meaningful when pool count is low (organic tokens with many pools can have high vol/liq)
    vol_liq = volume_24h / liquidity_usd if liquidity_usd > 0 else 0
    vol_liq_triggered = vol_liq > 10 and pool_count <= 3
    vol_liq_points = 20 if vol_liq_triggered else 0
    total_score += vol_liq_points
    signals.append({
        "name": "vol_liq_ratio",
        "triggered": vol_liq_triggered,
        "points": vol_liq_points,
        "value": round(vol_liq, 1),
        "threshold": ">10x with <=3 pools",
        "detail": f"{vol_liq:.1f}x vol/liq across {pool_count} pools",
    })

    # === Signal 2: Tx density per $1K MC ===
    # Rugs need hundreds of tiny wash trades per dollar of market cap
    # Organic volume comes from fewer, larger transactions
    tx_density = txs_24h / (market_cap_usd / 1000) if market_cap_usd > 0 else 0
    tx_density_triggered = tx_density > 40
    tx_density_points = 25 if tx_density_triggered else 0
    total_score += tx_density_points
    signals.append({
        "name": "tx_density",
        "triggered": tx_density_triggered,
        "points": tx_density_points,
        "value": round(tx_density, 1),
        "threshold": ">40 txs per $1K MC",
        "detail": f"{tx_density:.1f} txs per $1K MC ({txs_24h:,} txs / ${market_cap_usd:,.0f} MC)",
    })

    # === Signal 3: Deployer funding amount ===
    # Fresh throwaway wallets funded with dust (< 1 SOL)
    deployer_fund_triggered = deployer_fund_amount is not None and deployer_fund_amount < 1.0
    deployer_fund_points = 10 if deployer_fund_triggered else 0
    total_score += deployer_fund_points
    signals.append({
        "name": "deployer_dust_funding",
        "triggered": deployer_fund_triggered,
        "points": deployer_fund_points,
        "value": round(deployer_fund_amount, 3) if deployer_fund_amount is not None else None,
        "threshold": "<1 SOL",
        "detail": f"Deployer funded with {deployer_fund_amount:.3f} SOL" if deployer_fund_amount is not None else "Deployer funding unknown",
    })

    # === Signal 4: Deployer funder identity ===
    # Legitimate projects often fund from known exchanges; rugs use anonymous intermediaries
    deployer_unknown_triggered = deployer_funder_type is None or deployer_funder_type not in ("exchange", "protocol")
    deployer_unknown_points = 10 if deployer_unknown_triggered else 0
    total_score += deployer_unknown_points
    signals.append({
        "name": "deployer_funder_unknown",
        "triggered": deployer_unknown_triggered,
        "points": deployer_unknown_points,
        "value": deployer_funder_type,
        "threshold": "No exchange/protocol identity",
        "detail": f"Funder type: {deployer_funder_type or 'unknown'}",
    })

    # === Signal 5: Early buyer size distribution ===
    # Rugs scatter tiny buys to fake organic demand
    # Only counts when tx density is also high (otherwise organic memecoins can have small buys)
    pct_under_200 = 0
    if early_buyers:
        amounts = [b.get("total_usd", 0) for b in early_buyers]
        under_200 = sum(1 for a in amounts if a < 200)
        pct_under_200 = round(under_200 / len(amounts) * 100) if amounts else 0
    small_buys_triggered = pct_under_200 > 50 and tx_density > 40
    small_buys_points = 15 if small_buys_triggered else 0
    total_score += small_buys_points
    signals.append({
        "name": "small_early_buys",
        "triggered": small_buys_triggered,
        "points": small_buys_points,
        "value": pct_under_200,
        "threshold": ">50% under $200 AND high tx density",
        "detail": f"{pct_under_200}% of early buys under $200",
    })

    # === Signal 6: Meteora ghost pool ===
    # Placeholder DLMM position with near-zero liquidity = stealth exit route
    ghost_points = 10 if has_meteora_ghost else 0
    total_score += ghost_points
    signals.append({
        "name": "meteora_ghost_pool",
        "triggered": has_meteora_ghost,
        "points": ghost_points,
        "value": has_meteora_ghost,
        "threshold": "Meteora pool with <$100 liquidity",
        "detail": "Meteora ghost pool detected" if has_meteora_ghost else "No ghost pool",
    })

    # === Signal 7: Low pool count ===
    # Organic tokens attract independent LPs quickly; rugs stay on 1-3 pools
    low_pools_triggered = pool_count <= 3
    low_pools_points = 10 if low_pools_triggered else 0
    total_score += low_pools_points
    signals.append({
        "name": "low_pool_count",
        "triggered": low_pools_triggered,
        "points": low_pools_points,
        "value": pool_count,
        "threshold": "<=3 pools",
        "detail": f"{pool_count} pool{'s' if pool_count != 1 else ''}",
    })

    # Clamp to 100
    total_score = min(total_score, 100)

    # Verdict
    if total_score >= 60:
        verdict = "HIGH_RISK"
    elif total_score >= 40:
        verdict = "MODERATE"
    else:
        verdict = "LOW"

    return {
        "rug_score": total_score,
        "signals": signals,
        "verdict": verdict,
        "signals_triggered": sum(1 for s in signals if s["triggered"]),
        "signals_total": len(signals),
    }


def compute_rug_score_for_token(
    token_data: Dict,
    dexscreener_data: Optional[Dict] = None,
    deployer_funded_by: Optional[Dict] = None,
    early_buyers: Optional[List[Dict]] = None,
) -> Dict[str, Any]:
    """
    Convenience wrapper — computes rug score from token dict + supplementary data.
    Used by auto-scan and Quick DD pipelines.
    """
    dex = dexscreener_data or {}

    # Check for Meteora ghost pool
    has_meteora_ghost = False
    if token_data.get("has_meteora_pool"):
        # If meteora pool exists with very low liquidity, it's a ghost
        has_meteora_ghost = True  # Detection refinement can come later from pool data

    # Check pool data from DexScreener
    pools = dex.get("pools", [])
    pool_count = dex.get("pool_count", len(pools)) if dex else (token_data.get("pool_count", 1))

    # Check for ghost meteora in pools list
    if pools:
        for p in pools:
            dex_id = (p.get("dexId") or "").lower()
            liq = p.get("liquidity", {})
            liq_usd = liq.get("usd", 0) if isinstance(liq, dict) else (liq or 0)
            if "meteora" in dex_id and liq_usd < 100:
                has_meteora_ghost = True
                break

    deployer_fund_amount = None
    deployer_funder_type = None
    if deployer_funded_by:
        deployer_fund_amount = deployer_funded_by.get("amount")
        deployer_funder_type = deployer_funded_by.get("funderType")

    return compute_rug_score(
        volume_24h=dex.get("volume_24h", 0) or dex.get("volume_24h_usd", 0) or 0,
        liquidity_usd=dex.get("liquidity_usd", 0) or token_data.get("liquidity_usd", 0) or 0,
        txs_24h=dex.get("txs_24h", 0) or 0,
        market_cap_usd=dex.get("market_cap_usd", 0) or token_data.get("market_cap_usd", 0) or 0,
        deployer_fund_amount=deployer_fund_amount,
        deployer_funder_type=deployer_funder_type,
        early_buyers=early_buyers,
        pool_count=pool_count,
        has_meteora_ghost=has_meteora_ghost,
    )
