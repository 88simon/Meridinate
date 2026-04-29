"""
Quick DD — On-demand token due diligence pipeline.

Runs the full Meridinate intelligence pipeline on any token address in parallel:
  Batch 1 (free, instant): DexScreener snapshot, CLOBr score + depth, PumpFun metadata
  Batch 2 (~30-80 credits): Helius token analysis (early buyers, deployer, top holders)
  Batch 3 (~2-200 credits): LP trust analysis, deployer trace

Results are persisted in the quick_dd_runs table for history.
"""

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Dict, Optional

from meridinate import analyzed_tokens_db as db
from meridinate.observability import log_error, log_info
from meridinate.settings import HELIUS_API_KEY, CURRENT_INGEST_SETTINGS


# Progress state for polling (same pattern as auto-scan)
_dd_progress: Dict[str, Any] = {
    "running": False,
    "token_address": None,
    "step": None,
    "steps_completed": 0,
    "total_steps": 5,
    "started_at": None,
}


def get_dd_progress() -> Dict[str, Any]:
    return _dd_progress.copy()


def run_quick_dd(token_address: str) -> Dict[str, Any]:
    """
    Run the full Quick DD pipeline on a token address. Synchronous — run in a thread.

    Returns a comprehensive DD report dict.
    """
    global _dd_progress
    _dd_progress = {
        "running": True,
        "token_address": token_address,
        "step": "Starting",
        "steps_completed": 0,
        "total_steps": 5,
        "started_at": datetime.now().isoformat(),
    }

    started_at = time.time()
    credits_used = 0

    report: Dict[str, Any] = {
        "token_address": token_address,
        "started_at": datetime.now().isoformat(),
        "completed_at": None,
        "credits_used": 0,
        "dexscreener": None,
        "clobr": None,
        "pumpfun": None,
        "analysis": None,
        "lp_trust": None,
        "deployer_trace": None,
        "token_id": None,
        "error": None,
    }

    try:
        # ================================================================
        # Batch 1: Free data sources (parallel)
        # ================================================================
        _dd_progress["step"] = "Fetching market data"
        _dd_progress["steps_completed"] = 1

        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {
                pool.submit(_fetch_dexscreener, token_address): "dexscreener",
                pool.submit(_fetch_pumpfun, token_address): "pumpfun",
                pool.submit(_fetch_clobr, token_address): "clobr",
            }
            for future in as_completed(futures):
                key = futures[future]
                try:
                    report[key] = future.result()
                except Exception as e:
                    log_error(f"[QuickDD] {key} failed: {e}")

        # ================================================================
        # Batch 2: Helius token analysis
        # ================================================================
        _dd_progress["step"] = "Analyzing on-chain data"
        _dd_progress["steps_completed"] = 2

        analysis = _run_helius_analysis(token_address)
        if analysis:
            report["analysis"] = analysis
            credits_used += analysis.get("credits_used", 0)

            # Extract token name for report
            token_info = analysis.get("token_info")
            if token_info:
                metadata = token_info.get("onChainMetadata", {}).get("metadata", {})
                report["_token_name"] = metadata.get("name")
                report["_token_symbol"] = metadata.get("symbol")

            # Save to DB if not already there
            token_id = _save_to_db(token_address, report)
            report["token_id"] = token_id

        # ================================================================
        # Batch 3: LP Trust + Deployer trace (parallel)
        # ================================================================
        _dd_progress["step"] = "Checking liquidity trust"
        _dd_progress["steps_completed"] = 3

        deployer_address = None
        if analysis:
            deployer_address = analysis.get("deployer_address")

        pools = []
        if report["dexscreener"] and report["dexscreener"].get("pools"):
            pools = report["dexscreener"]["pools"]

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = {}

            if pools:
                futures[pool.submit(
                    _analyze_lp_trust, token_address, deployer_address, pools, report.get("token_id")
                )] = "lp_trust"

            if deployer_address:
                futures[pool.submit(_trace_deployer, deployer_address)] = "deployer_trace"

            for future in as_completed(futures):
                key = futures[future]
                try:
                    result = future.result()
                    report[key] = result
                    credits_used += result.get("credits_used", 0)
                except Exception as e:
                    log_error(f"[QuickDD] {key} failed: {e}")

        # ================================================================
        # Batch 4: Store LP trust data on token
        # ================================================================
        _dd_progress["step"] = "Finalizing"
        _dd_progress["steps_completed"] = 4

        if report["token_id"] and report.get("lp_trust"):
            _store_lp_trust(report["token_id"], report["lp_trust"])

        if report["token_id"] and report.get("clobr"):
            _store_clobr(report["token_id"], report["clobr"])

        # Compute rug score from all collected data
        try:
            from meridinate.services.rug_detector import compute_rug_score_for_token
            rug_result = compute_rug_score_for_token(
                token_data={"has_meteora_pool": bool(report.get("lp_trust", {}).get("pools"))},
                dexscreener_data=report.get("dexscreener"),
                deployer_funded_by=(report.get("deployer_trace") or {}).get("chain", [{}])[0] if report.get("deployer_trace") else None,
                early_buyers=(report.get("analysis") or {}).get("early_bidders"),
            )
            report["rug_score"] = rug_result
            if report["token_id"]:
                _store_rug_score(report["token_id"], rug_result)
        except Exception as e:
            log_error(f"[QuickDD] Rug score computation failed: {e}")

        # ================================================================
        # Complete
        # ================================================================
        _dd_progress["steps_completed"] = 5
        _dd_progress["step"] = "Complete"

        report["credits_used"] = credits_used
        report["completed_at"] = datetime.now().isoformat()
        report["duration_seconds"] = round(time.time() - started_at, 1)

        # Log credits to tracker (shows in bottom status bar)
        from meridinate.credit_tracker import get_credit_tracker
        get_credit_tracker().record_operation(
            operation="quick_dd",
            label="Quick DD",
            credits=credits_used,
            call_count=1,
            context={
                "token_address": token_address,
                "token_name": report.get("_token_name"),
                "lp_trust_score": (report.get("lp_trust") or {}).get("trust_score"),
                "duration": report.get("duration_seconds"),
            },
        )

        # Persist DD run
        _save_dd_run(report)

        log_info(
            f"[QuickDD] Complete: {token_address[:12]}... "
            f"in {report['duration_seconds']}s, {credits_used} credits"
        )

    except Exception as e:
        log_error(f"[QuickDD] Pipeline failed for {token_address}: {e}")
        report["error"] = str(e)
        report["completed_at"] = datetime.now().isoformat()
    finally:
        _dd_progress["running"] = False
        _dd_progress["step"] = None

    return report


# ============================================================================
# Pipeline steps
# ============================================================================


def _fetch_dexscreener(token_address: str) -> Optional[Dict]:
    try:
        from meridinate.services.dexscreener_service import get_dexscreener_service
        dex = get_dexscreener_service()
        snapshot = dex.get_token_snapshot(token_address)
        if not snapshot:
            return None

        # Also get individual pool data
        pairs = dex.get_token_pairs(token_address)
        pools = []
        if pairs:
            for pair in pairs[:10]:
                pools.append({
                    "pairAddress": pair.get("pairAddress"),
                    "dexId": pair.get("dexId"),
                    "liquidity": pair.get("liquidity", {}),
                    "url": pair.get("url"),
                })

        return {
            "market_cap_usd": snapshot.get("market_cap_usd"),
            "price_usd": snapshot.get("price_usd"),
            "liquidity_usd": snapshot.get("liquidity_usd"),
            "volume_24h": snapshot.get("volume_24h_usd"),
            "price_change_h1": snapshot.get("price_change_h1"),
            "price_change_h24": snapshot.get("price_change_h24"),
            "dex_id": snapshot.get("dex_id"),
            "age_hours": snapshot.get("age_hours"),
            "pools": pools,
            "pool_count": len(pools),
        }
    except Exception as e:
        log_error(f"[QuickDD] DexScreener failed: {e}")
        return None


def _fetch_pumpfun(token_address: str) -> Optional[Dict]:
    try:
        from meridinate.services.pumpfun_service import get_pumpfun_token_data
        data = get_pumpfun_token_data(token_address)
        if not data:
            return None
        return {
            "creator": data.get("creator"),
            "is_cashback": data.get("is_cashback"),
            "name": data.get("name"),
            "symbol": data.get("symbol"),
        }
    except Exception:
        return None


def _fetch_clobr(token_address: str) -> Optional[Dict]:
    try:
        from meridinate.services.clobr_service import get_clobr_service
        svc = get_clobr_service()
        if not svc:
            return None
        score_data = svc.get_score(token_address)
        if not score_data or score_data.get("status") != "available":
            return {"status": "unavailable"}

        depth_data = svc.get_market_depth(token_address)
        result = {
            "status": "available",
            "clobr_score": score_data.get("clobr_score"),
            "score_msg": score_data.get("score_msg"),
        }
        if depth_data:
            result["support_usd"] = depth_data.get("support_usd")
            result["resistance_usd"] = depth_data.get("resistance_usd")
            result["sr_ratio"] = depth_data.get("sr_ratio")
        return result
    except Exception:
        return None


def _run_helius_analysis(token_address: str) -> Optional[Dict]:
    try:
        from meridinate.helius_api import TokenAnalyzer
        from meridinate.settings import CURRENT_API_SETTINGS

        analyzer = TokenAnalyzer(HELIUS_API_KEY)
        result = analyzer.analyze_token(
            mint_address=token_address,
            min_usd=CURRENT_API_SETTINGS.get("minUsdFilter", 50.0),
            time_window_hours=72,
            max_transactions=CURRENT_API_SETTINGS.get("transactionLimit", 500),
            max_credits=CURRENT_API_SETTINGS.get("maxCreditsPerAnalysis", 1000),
            max_wallets_to_store=CURRENT_API_SETTINGS.get("walletCount", 100),
            top_holders_limit=CURRENT_API_SETTINGS.get("topHoldersLimit", 10),
        )
        return result
    except Exception as e:
        log_error(f"[QuickDD] Helius analysis failed: {e}")
        return None


def _analyze_lp_trust(
    token_address: str, deployer_address: Optional[str],
    pools: list, token_id: Optional[int]
) -> Dict:
    from meridinate.services.lp_trust_analyzer import analyze_lp_trust
    return analyze_lp_trust(token_address, deployer_address, pools, HELIUS_API_KEY, token_id)


def _trace_deployer(deployer_address: str) -> Dict:
    from meridinate.services.funding_tracer import trace_funding_chain
    return trace_funding_chain(deployer_address, HELIUS_API_KEY, max_hops=3, stop_at_exchanges=True)


# ============================================================================
# DB persistence
# ============================================================================


def _save_to_db(token_address: str, report: Dict) -> Optional[int]:
    """Save or update the token in analyzed_tokens. Returns token_id."""
    try:
        # Check if already exists
        with db.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id FROM analyzed_tokens WHERE token_address = ? AND (deleted_at IS NULL OR deleted_at = '')",
                (token_address,),
            )
            row = cursor.fetchone()
            if row:
                token_id = row[0]
                # Update existing token with fresh data from Quick DD
                dex = report.get("dexscreener") or {}
                analysis = report.get("analysis") or {}
                cursor.execute("""
                    UPDATE analyzed_tokens SET
                        market_cap_usd_current = COALESCE(?, market_cap_usd_current),
                        liquidity_usd = COALESCE(?, liquidity_usd),
                        deployer_address = COALESCE(?, deployer_address),
                        market_cap_updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (
                    dex.get("market_cap_usd"),
                    dex.get("liquidity_usd"),
                    analysis.get("deployer_address"),
                    token_id,
                ))
                # Re-save early buyers if analysis returned more wallets
                early_bidders = analysis.get("early_bidders", [])
                if early_bidders:
                    for bidder in early_bidders:
                        if "first_buy_time" in bidder and hasattr(bidder["first_buy_time"], "isoformat"):
                            bidder["first_buy_time"] = bidder["first_buy_time"].isoformat()
                    # Update wallet count
                    cursor.execute(
                        "UPDATE analyzed_tokens SET wallets_found = ? WHERE id = ?",
                        (len(early_bidders), token_id),
                    )
                log_info(f"[QuickDD] Updated existing token {token_id} with fresh data")
                return token_id

        # Save new token
        analysis = report.get("analysis") or {}
        dex = report.get("dexscreener") or {}
        pf = report.get("pumpfun") or {}

        from meridinate.helius_api import generate_axiom_export, generate_token_acronym

        token_name = pf.get("name") or "Unknown"
        token_symbol = pf.get("symbol") or "UNK"

        # Try to get name from analysis token_info
        token_info = analysis.get("token_info")
        if token_info:
            metadata = token_info.get("onChainMetadata", {}).get("metadata", {})
            token_name = metadata.get("name") or token_name
            token_symbol = metadata.get("symbol") or token_symbol

        early_bidders = analysis.get("early_bidders", [])
        for bidder in early_bidders:
            if "first_buy_time" in bidder and hasattr(bidder["first_buy_time"], "isoformat"):
                bidder["first_buy_time"] = bidder["first_buy_time"].isoformat()

        acronym = generate_token_acronym(token_name, token_symbol)
        axiom_export = generate_axiom_export(
            early_bidders=early_bidders, token_name=token_name,
            token_symbol=token_symbol, limit=100,
        )

        token_id = db.save_analyzed_token(
            token_address=token_address,
            token_name=token_name,
            token_symbol=token_symbol,
            acronym=acronym,
            early_bidders=early_bidders,
            axiom_json=axiom_export,
            first_buy_timestamp=analysis.get("first_transaction_time"),
            credits_used=analysis.get("api_credits_used", 0),
            max_wallets=100,
            market_cap_usd=dex.get("market_cap_usd") or analysis.get("market_cap_usd"),
            liquidity_usd=dex.get("liquidity_usd"),
            top_holders=analysis.get("top_holders"),
            ingest_source="quick_dd",
            dex_id=dex.get("dex_id"),
            deployer_address=analysis.get("deployer_address"),
            creation_events=analysis.get("creation_events"),
        )
        return token_id

    except Exception as e:
        log_error(f"[QuickDD] Failed to save token to DB: {e}")
        return None


def _store_lp_trust(token_id: int, lp_trust: Dict):
    """Store LP trust results on the token."""
    try:
        with db.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE analyzed_tokens
                SET lp_trust_score = ?, lp_trust_json = ?
                WHERE id = ?
            """, (
                lp_trust.get("trust_score"),
                json.dumps(lp_trust),
                token_id,
            ))
    except Exception as e:
        log_error(f"[QuickDD] Failed to store LP trust: {e}")


def _store_clobr(token_id: int, clobr: Dict):
    """Store CLOBr data on the token."""
    if clobr.get("status") != "available":
        return
    try:
        with db.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE analyzed_tokens
                SET clobr_score = ?,
                    clobr_support_usd = ?,
                    clobr_resistance_usd = ?,
                    clobr_sr_ratio = ?,
                    clobr_updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (
                clobr.get("clobr_score"),
                clobr.get("support_usd"),
                clobr.get("resistance_usd"),
                clobr.get("sr_ratio"),
                token_id,
            ))
    except Exception as e:
        log_error(f"[QuickDD] Failed to store CLOBr: {e}")


def _store_rug_score(token_id: int, rug_result: Dict):
    """Store rug score on the token."""
    try:
        with db.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE analyzed_tokens
                SET rug_score = ?, rug_score_json = ?
                WHERE id = ?
            """, (
                rug_result.get("rug_score"),
                json.dumps(rug_result),
                token_id,
            ))
    except Exception as e:
        log_error(f"[QuickDD] Failed to store rug score: {e}")


def _save_dd_run(report: Dict):
    """Persist the DD run for history."""
    try:
        with db.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO quick_dd_runs (
                    token_address, token_id, token_name, token_symbol,
                    market_cap_usd, clobr_score, lp_trust_score,
                    credits_used, duration_seconds,
                    report_json, started_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                report["token_address"],
                report.get("token_id"),
                (report.get("pumpfun") or {}).get("name")
                or ((report.get("analysis") or {}).get("token_info") or {}).get("onChainMetadata", {}).get("metadata", {}).get("name")
                or report.get("_token_name"),
                (report.get("pumpfun") or {}).get("symbol")
                or ((report.get("analysis") or {}).get("token_info") or {}).get("onChainMetadata", {}).get("metadata", {}).get("symbol")
                or report.get("_token_symbol"),
                (report.get("dexscreener") or {}).get("market_cap_usd"),
                (report.get("clobr") or {}).get("clobr_score"),
                (report.get("lp_trust") or {}).get("trust_score"),
                report.get("credits_used", 0),
                report.get("duration_seconds"),
                json.dumps(report, default=str),
                report.get("started_at"),
                report.get("completed_at"),
            ))
    except Exception as e:
        log_error(f"[QuickDD] Failed to save DD run: {e}")
