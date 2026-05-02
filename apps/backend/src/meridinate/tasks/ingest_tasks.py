"""
Ingest Pipeline Tasks

Auto-Scan: Fetch tokens from DexScreener, apply filters, run Helius analysis immediately.
Hot Refresh: Update MC/volume for analyzed tokens (free).
Legacy: Discovery/Promote flow kept for backward compatibility but no longer primary.
"""

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from meridinate import analyzed_tokens_db as db
from meridinate.observability import log_error, log_info
from meridinate.services.dexscreener_service import get_dexscreener_service
from meridinate.settings import CURRENT_INGEST_SETTINGS, CURRENT_API_SETTINGS, save_ingest_settings, HELIUS_API_KEY, API_BASE_URL


# ============================================================================
# Scan Progress — lightweight state for progress polling during auto-scan
# ============================================================================
#
# `last_progress_at` is the heartbeat — bumped every time a token finishes
# (success/fail/timeout). If it's stale by STALE_THRESHOLD_SECONDS while
# `running` is True, the public reader treats the scan as dead and clears it.
# This guarantees the UI never sticks on "running" forever again.

STALE_THRESHOLD_SECONDS = 600  # 10 minutes without a token finishing = scan is dead

_scan_progress: Dict[str, Any] = {
    "running": False,
    "current": 0,
    "total": 0,
    "credits_used": 0,
    "current_token": None,
    "started_at": None,
    "last_progress_at": None,  # ISO timestamp; bumped after each token attempt
}


def _bump_heartbeat() -> None:
    _scan_progress["last_progress_at"] = datetime.now().isoformat()


def _clear_progress() -> None:
    """Reset all scan-progress fields. Called when scan completes or is detected stale."""
    _scan_progress["running"] = False
    _scan_progress["current_token"] = None
    _scan_progress["last_progress_at"] = None


def reset_scan_progress(reason: str = "manual") -> Dict[str, Any]:
    """
    Forcibly clear stuck scan-progress state without restarting the backend.
    Used by the /api/ingest/scan-progress/reset endpoint when the scan visibly
    hangs. The underlying thread (if any) continues running in the background,
    but the UI immediately reflects the reset.
    """
    snapshot = _scan_progress.copy()
    _clear_progress()
    log_info(f"[Auto-Scan] Scan-progress state forcibly reset ({reason}); was: {snapshot}")
    return {"reset": True, "previous_state": snapshot}


def get_scan_progress() -> Dict[str, Any]:
    """
    Thread-safe read of scan progress.
    Auto-clears stuck state: if running=True but the heartbeat is stale, treat
    the scan as dead and return running=False so the UI doesn't lie.
    """
    snap = _scan_progress.copy()
    if snap.get("running") and snap.get("last_progress_at"):
        try:
            last = datetime.fromisoformat(snap["last_progress_at"])
            if datetime.now() - last > timedelta(seconds=STALE_THRESHOLD_SECONDS):
                log_error(
                    f"[Auto-Scan] Stale scan detected — no progress in "
                    f"{int((datetime.now() - last).total_seconds())}s; auto-clearing state."
                )
                _clear_progress()
                snap = _scan_progress.copy()
                snap["stale_cleared"] = True
        except Exception:
            pass
    return snap


def tag_deployer_wallet(deployer_address: Optional[str]) -> None:
    """Tag a deployer wallet, detect serial deployers, and compute performance sub-labels."""
    if not deployer_address:
        return
    try:
        with db.get_db_connection() as conn:
            cursor = conn.cursor()
            # Add Deployer tag (tier 1)
            cursor.execute(
                "INSERT OR IGNORE INTO wallet_tags (wallet_address, tag, tier, source, updated_at) "
                "VALUES (?, 'Deployer', 1, 'auto:deployer-detection', CURRENT_TIMESTAMP)",
                (deployer_address,)
            )
            # Get all tokens this wallet deployed with their verdicts
            cursor.execute("""
                SELECT t.id, t.market_cap_usd, t.market_cap_ath,
                       (SELECT tt.tag FROM token_tags tt WHERE tt.token_id = t.id AND tt.tag IN ('verified-win', 'verified-loss') LIMIT 1) as verdict
                FROM analyzed_tokens t
                WHERE t.deployer_address = ? AND (t.deleted_at IS NULL OR t.deleted_at = '')
            """, (deployer_address,))
            tokens = cursor.fetchall()
            deploy_count = len(tokens)

            if deploy_count >= 2:
                cursor.execute(
                    "INSERT OR IGNORE INTO wallet_tags (wallet_address, tag, tier, source, updated_at) "
                    "VALUES (?, 'Serial Deployer', 1, 'auto:deployer-detection', CURRENT_TIMESTAMP)",
                    (deployer_address,)
                )
                log_info(f"[Deployer] Serial deployer detected: {deployer_address[:12]}... ({deploy_count} tokens)")

            # Compute performance sub-labels (only for deployers with 2+ verdicts)
            wins = sum(1 for t in tokens if t[3] == "verified-win")
            losses = sum(1 for t in tokens if t[3] == "verified-loss")
            total_verdicts = wins + losses

            # Remove old performance tags before recomputing
            perf_tags = ("Winning Deployer", "Rug Deployer", "High-Value Deployer")
            cursor.execute(
                f"DELETE FROM wallet_tags WHERE wallet_address = ? AND tag IN ({','.join('?' for _ in perf_tags)})",
                (deployer_address, *perf_tags)
            )

            if total_verdicts >= 2:
                win_rate = wins / total_verdicts
                if win_rate >= 0.5:
                    cursor.execute(
                        "INSERT INTO wallet_tags (wallet_address, tag, tier, source, updated_at) "
                        "VALUES (?, 'Winning Deployer', 1, 'auto:deployer-detection', CURRENT_TIMESTAMP)",
                        (deployer_address,)
                    )
                elif losses / total_verdicts >= 0.5:
                    cursor.execute(
                        "INSERT INTO wallet_tags (wallet_address, tag, tier, source, updated_at) "
                        "VALUES (?, 'Rug Deployer', 1, 'auto:deployer-detection', CURRENT_TIMESTAMP)",
                        (deployer_address,)
                    )

            # High-Value Deployer: avg ATH multiple >= 10x across winning tokens
            ath_multiples = []
            for t in tokens:
                if t[3] == "verified-win" and t[1] and t[2] and t[1] > 0:
                    ath_multiples.append(t[2] / t[1])
            if ath_multiples and sum(ath_multiples) / len(ath_multiples) >= 10:
                cursor.execute(
                    "INSERT INTO wallet_tags (wallet_address, tag, tier, source, updated_at) "
                    "VALUES (?, 'High-Value Deployer', 1, 'auto:deployer-detection', CURRENT_TIMESTAMP)",
                    (deployer_address,)
                )

    except Exception as e:
        log_error(f"[Deployer] Failed to tag deployer {deployer_address[:12]}...: {e}")


def detect_and_tag_sniper_bots() -> Dict[str, Any]:
    """
    Detect sniper bots by analyzing entry timing consistency across tokens.
    Criteria: avg entry < 30 seconds AND 80%+ entries under 60 seconds AND 5+ tokens.
    Tags them as 'Sniper Bot' (tier 1) and removes misleading 'Consistent Winner' tags.
    """
    from collections import defaultdict

    result = {"bots_detected": 0, "tags_added": 0, "winner_tags_removed": 0}

    try:
        with db.get_db_connection() as conn:
            cursor = conn.cursor()

            # Get all wallet-token entry timing pairs
            cursor.execute("""
                SELECT ebw.wallet_address, ebw.first_buy_timestamp, t.first_buy_timestamp
                FROM early_buyer_wallets ebw
                JOIN analyzed_tokens t ON t.id = ebw.token_id
                WHERE ebw.first_buy_timestamp IS NOT NULL AND t.first_buy_timestamp IS NOT NULL
                  AND (t.deleted_at IS NULL OR t.deleted_at = '')
            """)

            wallets = defaultdict(list)
            for row in cursor.fetchall():
                try:
                    buy_ts = str(row[1]).replace('Z', '').split('+')[0]
                    token_ts = str(row[2]).replace('Z', '').split('+')[0]
                    from datetime import datetime
                    buy_time = datetime.fromisoformat(buy_ts)
                    token_time = datetime.fromisoformat(token_ts)
                    delta = (buy_time - token_time).total_seconds()
                    if 0 <= delta < 86400:
                        wallets[row[0]].append(delta)
                except Exception:
                    pass

            # Detect sniper bots
            for addr, deltas in wallets.items():
                if len(deltas) < 5:
                    continue
                avg = sum(deltas) / len(deltas)
                under_60 = sum(1 for d in deltas if d < 60)
                pct = under_60 / len(deltas) * 100

                if avg < 30 and pct >= 80:
                    result["bots_detected"] += 1

                    # Add Sniper Bot tag
                    cursor.execute(
                        "INSERT OR IGNORE INTO wallet_tags (wallet_address, tag, tier, source, updated_at) "
                        "VALUES (?, 'Sniper Bot', 1, 'auto:sniper-bot-detection', CURRENT_TIMESTAMP)",
                        (addr,)
                    )
                    if cursor.rowcount > 0:
                        result["tags_added"] += 1

                    # Remove misleading Consistent Winner tag if present
                    cursor.execute(
                        "DELETE FROM wallet_tags WHERE wallet_address = ? AND tag = 'Consistent Winner'",
                        (addr,)
                    )
                    if cursor.rowcount > 0:
                        result["winner_tags_removed"] += 1
                        log_info(f"[SniperBot] Removed 'Consistent Winner' from bot {addr[:12]}...")

        log_info(
            f"[SniperBot] Detection complete: {result['bots_detected']} bots, "
            f"{result['tags_added']} new tags, {result['winner_tags_removed']} false winner tags removed"
        )
    except Exception as e:
        log_error(f"[SniperBot] Detection failed: {e}")

    return result


def _compute_pnl_for_new_recurring_wallets() -> Dict[str, Any]:
    """
    Find recurring wallets that don't have real PnL data yet and compute it.
    Called after each auto-scan cycle.

    Caps:
      - Process at most `auto_scan_pnl_backfill_max_wallets` per run (default 10)
      - Per-wallet wall-clock deadline `auto_scan_pnl_backfill_per_wallet_seconds` (default 60)

    Without these caps, this post-step could itself hang for hours when a wallet's
    Helius transaction history is huge or when one call times out.
    """
    result = {"wallets_computed": 0, "credits_used": 0}
    max_wallets = CURRENT_INGEST_SETTINGS.get("auto_scan_pnl_backfill_max_wallets", 10)
    per_wallet_timeout = CURRENT_INGEST_SETTINGS.get("auto_scan_pnl_backfill_per_wallet_seconds", 60)

    try:
        with db.get_db_connection() as conn:
            cursor = conn.cursor()

            # Find recurring wallets (2+ tokens) that have NO real PnL data
            cursor.execute("""
                SELECT DISTINCT ebw.wallet_address, COUNT(DISTINCT ebw.token_id) as token_count
                FROM early_buyer_wallets ebw
                JOIN analyzed_tokens t ON t.id = ebw.token_id
                WHERE (t.deleted_at IS NULL OR t.deleted_at = '')
                GROUP BY ebw.wallet_address
                HAVING token_count >= 2
                AND ebw.wallet_address NOT IN (
                    SELECT DISTINCT wallet_address FROM mtew_token_positions
                    WHERE pnl_source = 'helius_enhanced'
                )
                ORDER BY token_count DESC
                LIMIT ?
            """, (max_wallets,))
            wallets_needing_pnl = [row[0] for row in cursor.fetchall()]

        if not wallets_needing_pnl:
            log_info("[PnL Auto] No new recurring wallets need PnL computation")
            return result

        log_info(f"[PnL Auto] {len(wallets_needing_pnl)} recurring wallets need real PnL (capped at {max_wallets})")

        from meridinate.services.pnl_calculator_v2 import compute_and_store_wallet_pnl_v2

        for addr in wallets_needing_pnl:
            try:
                with ThreadPoolExecutor(max_workers=1, thread_name_prefix="pnl-backfill") as exec_:
                    fut = exec_.submit(compute_and_store_wallet_pnl_v2, addr, HELIUS_API_KEY)
                    pnl = fut.result(timeout=per_wallet_timeout)
                result["wallets_computed"] += 1
                result["credits_used"] += pnl.get("credits_used", 0)
            except FuturesTimeoutError:
                log_error(f"[PnL Auto] TIMEOUT after {per_wallet_timeout}s for {addr[:12]}... — skipping")
            except Exception as e:
                log_error(f"[PnL Auto] Failed for {addr[:12]}...: {e}")

        from meridinate.credit_tracker import get_credit_tracker
        get_credit_tracker().record_operation(
            operation="pnl_auto", label="PnL Auto-Compute",
            credits=result["credits_used"], call_count=result["wallets_computed"],
            context={"total_wallets": len(wallets_needing_pnl)},
        )

        # Retag wallets based on real PnL data
        _retag_wallets_from_real_pnl(wallets_needing_pnl[:result["wallets_computed"]])

        log_info(
            f"[PnL Auto] Computed PnL for {result['wallets_computed']}/{len(wallets_needing_pnl)} wallets, "
            f"{result['credits_used']} credits"
        )
    except Exception as e:
        log_error(f"[PnL Auto] Error: {e}")

    return result


def _retag_wallets_from_real_pnl(wallet_addresses: List[str]):
    """
    Recompute behavioral tags (Consistent Winner, Consistent Loser) based on real PnL.
    Only uses positions with pnl_source = 'helius_enhanced'.
    """
    try:
        with db.get_db_connection() as conn:
            cursor = conn.cursor()

            for addr in wallet_addresses:
                # Get real PnL positions
                cursor.execute("""
                    SELECT realized_pnl, total_bought_usd, total_sold_usd, still_holding
                    FROM mtew_token_positions
                    WHERE wallet_address = ? AND pnl_source = 'helius_enhanced'
                """, (addr,))
                positions = cursor.fetchall()

                if len(positions) < 2:
                    continue  # Need at least 2 positions to tag

                wins = sum(1 for p in positions if (p[0] or 0) > 0)
                losses = sum(1 for p in positions if (p[0] or 0) < 0 and not p[3])
                total = wins + losses

                if total < 2:
                    continue

                win_rate = wins / total

                # Remove old behavioral tags
                cursor.execute(
                    "DELETE FROM wallet_tags WHERE wallet_address = ? AND tag IN ('Consistent Winner', 'Consistent Loser')",
                    (addr,)
                )

                # Apply new tags based on real data
                if win_rate >= 0.6 and wins >= 3:
                    cursor.execute(
                        "INSERT OR IGNORE INTO wallet_tags (wallet_address, tag, tier, source, updated_at) "
                        "VALUES (?, 'Consistent Winner', 2, 'auto:real-pnl', CURRENT_TIMESTAMP)",
                        (addr,)
                    )
                elif win_rate <= 0.3 and losses >= 3:
                    cursor.execute(
                        "INSERT OR IGNORE INTO wallet_tags (wallet_address, tag, tier, source, updated_at) "
                        "VALUES (?, 'Consistent Loser', 2, 'auto:real-pnl', CURRENT_TIMESTAMP)",
                        (addr,)
                    )
    except Exception as e:
        log_error(f"[PnL Retag] Error: {e}")


def run_auto_scan_sync(max_tokens: Optional[int] = None) -> Dict[str, Any]:
    """
    Synchronous Auto-Scan — runs entirely in a background thread.
    Discovers tokens from DexScreener, applies filters, runs Helius analysis.
    Does NOT touch the async event loop.
    """
    from meridinate.helius_api import TokenAnalyzer, generate_axiom_export, generate_token_acronym
    from meridinate.tasks.position_tracker import record_mtew_positions_for_token

    settings = CURRENT_INGEST_SETTINGS
    max_tokens = max_tokens or settings.get("discovery_max_per_run", settings.get("tier0_max_tokens_per_run", 20))
    mc_min = settings.get("mc_min", 10000)
    volume_min = settings.get("volume_min", 5000)
    liquidity_min = settings.get("liquidity_min", 5000)
    age_max_hours = settings.get("age_max_hours", 48)

    log_info(f"[Auto-Scan] Starting (sync): max={max_tokens}, mc>=${mc_min}")

    result = {
        "tokens_found": 0, "tokens_scanned": 0, "tokens_skipped": 0,
        "tokens_filtered": 0, "tokens_failed": 0, "credits_used": 0,
        "errors": [], "started_at": datetime.now().isoformat(), "completed_at": None,
    }

    # Initialize scan progress (heartbeat starts now so stale detection has a baseline)
    _scan_progress["running"] = True
    _scan_progress["current"] = 0
    _scan_progress["total"] = 0
    _scan_progress["credits_used"] = 0
    _scan_progress["current_token"] = None
    _scan_progress["started_at"] = result["started_at"]
    _bump_heartbeat()

    # Per-token wall-clock deadline. Without this, one stuck Helius call can
    # freeze the entire scan for hours. ThreadPoolExecutor.result(timeout=) raises
    # FuturesTimeoutError after N seconds; the orphaned worker thread keeps running
    # in the background but the main scan moves on to the next token.
    per_token_timeout = CURRENT_INGEST_SETTINGS.get("auto_scan_per_token_timeout_seconds", 90)

    try:
        existing_addresses = db.get_existing_token_addresses()
        dexscreener = get_dexscreener_service()
        tokens, fetched_count = dexscreener.fetch_recent_migrated_tokens(
            max_tokens=max_tokens * 3, min_mc=mc_min, min_volume=volume_min,
            min_liquidity=liquidity_min, max_age_hours=age_max_hours,
        )
        result["tokens_found"] = fetched_count
        _scan_progress["total"] = min(len(tokens), max_tokens)

        # Load pipeline filters
        launchpad_include = [x.lower() for x in settings.get("launchpad_include", [])]
        launchpad_exclude = [x.lower() for x in settings.get("launchpad_exclude", [])]
        quote_token_include = [x.upper() for x in settings.get("quote_token_include", [])]
        address_suffix_include = [x.lower() for x in settings.get("address_suffix_include", [])]
        buys_24h_min = settings.get("buys_24h_min")
        net_buys_24h_min = settings.get("net_buys_24h_min")
        txs_24h_min = settings.get("txs_24h_min")
        price_change_h1_min = settings.get("price_change_h1_min")
        keyword_include = [k.lower() for k in settings.get("keyword_include", [])]
        keyword_exclude = [k.lower() for k in settings.get("keyword_exclude", [])]
        require_socials = settings.get("require_socials", False)
        mc_max = settings.get("mc_max")

        # Load webhook detections for cross-referencing
        webhook_detections = {}
        try:
            with db.get_db_connection() as wh_conn:
                wh_cursor = wh_conn.cursor()
                wh_cursor.execute(
                    "SELECT token_address, conviction_score, detected_at, status, rejection_reason, deployer_address "
                    "FROM webhook_detections"
                )
                for wh_row in wh_cursor.fetchall():
                    webhook_detections[wh_row[0]] = {
                        "conviction_score": wh_row[1],
                        "detected_at": wh_row[2],
                        "status": wh_row[3],
                        "rejection_reason": wh_row[4],
                        "deployer_address": wh_row[5],
                    }
        except Exception:
            pass

        scanned = 0
        for token in tokens:
            if scanned >= max_tokens:
                break
            address = token.get("token_address")
            if not address or address in existing_addresses:
                result["tokens_skipped"] += 1
                continue

            # Cross-reference with webhook detections (for cross-linking, NOT for skipping)
            # Tokens can revive after webhook rejection — DexScreener should always analyze independently
            webhook_data = webhook_detections.get(address)

            # Apply filters
            dex_id = (token.get("dex_id") or "").lower()
            quote = (token.get("quote_token") or "").upper()
            name_lower = (token.get("token_name") or "").lower()
            addr_lower = address.lower()

            # Launchpad + address suffix: pass if EITHER matches (OR logic)
            launchpad_ok = not launchpad_include or dex_id in launchpad_include
            suffix_ok = not address_suffix_include or any(addr_lower.endswith(s) for s in address_suffix_include)
            if launchpad_include or address_suffix_include:
                if not launchpad_ok and not suffix_ok: result["tokens_filtered"] += 1; continue
            if launchpad_exclude and dex_id in launchpad_exclude: result["tokens_filtered"] += 1; continue
            if quote_token_include and quote not in quote_token_include: result["tokens_filtered"] += 1; continue
            if mc_max and (token.get("market_cap_usd") or 0) > mc_max: result["tokens_filtered"] += 1; continue
            if buys_24h_min and (token.get("buys_24h") or 0) < buys_24h_min: result["tokens_filtered"] += 1; continue
            if net_buys_24h_min and (token.get("net_buys_24h") or 0) < net_buys_24h_min: result["tokens_filtered"] += 1; continue
            if txs_24h_min and (token.get("txs_24h") or 0) < txs_24h_min: result["tokens_filtered"] += 1; continue
            if price_change_h1_min and (token.get("price_change_h1") or 0) < price_change_h1_min: result["tokens_filtered"] += 1; continue
            if keyword_include and not any(kw in name_lower for kw in keyword_include): result["tokens_filtered"] += 1; continue
            if keyword_exclude and any(kw in name_lower for kw in keyword_exclude): result["tokens_filtered"] += 1; continue
            if require_socials and not token.get("has_socials"): result["tokens_filtered"] += 1; continue

            # Update progress: about to analyze this token
            _scan_progress["current_token"] = token.get("token_name") or address[:12]

            # Per-token analysis is wrapped in a worker function so we can enforce
            # a wall-clock deadline. Returns (status, credits_used) where status is
            # one of: "scanned", "failed", "no_data".
            def _analyze_one_token() -> tuple[str, int]:
                log_info(f"[Auto-Scan] Analyzing {address}")
                analyzer = TokenAnalyzer(HELIUS_API_KEY)
                analysis_result = analyzer.analyze_token(
                    mint_address=address,
                    min_usd=CURRENT_API_SETTINGS.get("minUsdFilter", 50.0),
                    time_window_hours=72,
                    max_transactions=CURRENT_API_SETTINGS.get("transactionLimit", 500),
                    max_credits=CURRENT_API_SETTINGS.get("maxCreditsPerAnalysis", 1000),
                    max_wallets_to_store=CURRENT_API_SETTINGS.get("walletCount", 10),
                    top_holders_limit=CURRENT_API_SETTINGS.get("topHoldersLimit", 10),
                )
                local_credits = analysis_result.get("api_credits_used", 0)

                token_info = analysis_result.get("token_info")
                token_name = token.get("token_name") or "Unknown"
                token_symbol = token.get("token_symbol") or "UNK"
                if token_info:
                    metadata = token_info.get("onChainMetadata", {}).get("metadata", {})
                    token_name = metadata.get("name") or token_name
                    token_symbol = metadata.get("symbol") or token_symbol

                early_bidders = analysis_result.get("early_bidders", [])
                if not early_bidders and not token_info:
                    return ("no_data", local_credits)

                acronym = generate_token_acronym(token_name, token_symbol)
                for bidder in early_bidders:
                    if "first_buy_time" in bidder and hasattr(bidder["first_buy_time"], "isoformat"):
                        bidder["first_buy_time"] = bidder["first_buy_time"].isoformat()

                max_wallets = CURRENT_API_SETTINGS.get("walletCount", 10)
                axiom_export = generate_axiom_export(early_bidders=early_bidders, token_name=token_name, token_symbol=token_symbol, limit=max_wallets)

                token_id = db.save_analyzed_token(
                    token_address=address, token_name=token_name, token_symbol=token_symbol,
                    acronym=acronym, early_bidders=early_bidders, axiom_json=axiom_export,
                    first_buy_timestamp=analysis_result.get("first_transaction_time"),
                    credits_used=local_credits, max_wallets=max_wallets,
                    market_cap_usd=analysis_result.get("market_cap_usd"),
                    liquidity_usd=token.get("liquidity_usd"),
                    top_holders=analysis_result.get("top_holders"), ingest_source="auto-scan",
                    dex_id=token.get("dex_id"),
                    deployer_address=analysis_result.get("deployer_address"),
                    creation_events=analysis_result.get("creation_events"),
                )
                log_info(f"[Auto-Scan] Saved {token_name} ({acronym}) id={token_id}, {len(early_bidders)} wallets")

                # Cross-system: link webhook detection to analyzed token
                if webhook_data:
                    try:
                        webhook_detected_at = webhook_data["detected_at"]
                        now = datetime.now()
                        try:
                            if "T" in str(webhook_detected_at):
                                wh_time = datetime.fromisoformat(str(webhook_detected_at).replace("Z", "+00:00")).replace(tzinfo=None)
                            else:
                                wh_time = datetime.strptime(str(webhook_detected_at), "%Y-%m-%d %H:%M:%S")
                            time_to_migration = (now - wh_time).total_seconds() / 60
                        except Exception:
                            time_to_migration = None

                        with db.get_db_connection() as cross_conn:
                            cross_cursor = cross_conn.cursor()
                            cross_cursor.execute("""
                                UPDATE analyzed_tokens SET
                                    webhook_detected_at = ?,
                                    webhook_conviction_score = ?,
                                    time_to_migration_minutes = ?
                                WHERE id = ?
                            """, (webhook_detected_at, webhook_data["conviction_score"], time_to_migration, token_id))
                            cross_cursor.execute("""
                                UPDATE webhook_detections SET
                                    auto_scan_picked_up_at = CURRENT_TIMESTAMP,
                                    time_to_migration_minutes = ?,
                                    auto_scan_token_id = ?
                                WHERE token_address = ?
                            """, (time_to_migration, token_id, address))
                        log_info(f"[Auto-Scan] Cross-linked with webhook detection (conviction={webhook_data['conviction_score']}, migration={time_to_migration:.1f}min)" if time_to_migration else "[Auto-Scan] Cross-linked with webhook detection")
                    except Exception as e:
                        log_error(f"[Auto-Scan] Cross-system linkage failed: {e}")

                tag_deployer_wallet(analysis_result.get("deployer_address"))

                try:
                    from meridinate.services.pumpfun_service import get_pumpfun_token_data
                    pf_data = get_pumpfun_token_data(address)
                    if pf_data:
                        with db.get_db_connection() as pf_conn:
                            pf_cursor = pf_conn.cursor()
                            pf_cursor.execute(
                                "UPDATE analyzed_tokens SET is_cashback = ? WHERE id = ?",
                                (1 if pf_data.get("is_cashback_enabled") else 0, token_id)
                            )
                            pf_ath = pf_data.get("ath_market_cap")
                            if pf_ath and pf_ath > 0:
                                pf_cursor.execute(
                                    "UPDATE analyzed_tokens SET market_cap_ath = MAX(COALESCE(market_cap_ath, 0), ?) WHERE id = ?",
                                    (pf_ath, token_id)
                                )
                            pf_creator = pf_data.get("creator")
                            if pf_creator and pf_creator != analysis_result.get("deployer_address"):
                                pf_cursor.execute(
                                    "UPDATE analyzed_tokens SET deployer_address = ? WHERE id = ?",
                                    (pf_creator, token_id)
                                )
                                tag_deployer_wallet(pf_creator)
                                log_info(f"[Auto-Scan] Deployer corrected via PumpFun API: {pf_creator[:12]}...")
                except Exception as e:
                    log_error(f"[Auto-Scan] PumpFun enrichment failed for token {token_id}: {e}")

                try:
                    db.update_multi_token_wallet_metadata(token_id)
                except Exception as e:
                    log_error(f"[Auto-Scan] Failed to update multi-token wallet metadata for token {token_id}: {e}")
                try:
                    record_mtew_positions_for_token(token_id=token_id, token_address=address, entry_market_cap=analysis_result.get("market_cap_usd"), top_holders=analysis_result.get("top_holders"))
                except Exception as e:
                    log_error(f"[Auto-Scan] Failed to record positions for token {token_id}: {e}")

                try:
                    from meridinate.services.rug_detector import compute_rug_score_for_token
                    rug_result = compute_rug_score_for_token(
                        token_data={},
                        dexscreener_data={
                            "volume_24h": token.get("volume_24h_usd", 0),
                            "liquidity_usd": token.get("liquidity_usd", 0),
                            "txs_24h": token.get("txs_24h", 0),
                            "market_cap_usd": token.get("market_cap_usd", 0),
                            "pool_count": 1,
                        },
                        early_buyers=early_bidders,
                    )
                    if rug_result and token_id:
                        import json as _json
                        with db.get_db_connection() as rug_conn:
                            rug_conn.cursor().execute(
                                "UPDATE analyzed_tokens SET rug_score = ?, rug_score_json = ? WHERE id = ?",
                                (rug_result["rug_score"], _json.dumps(rug_result), token_id),
                            )
                except Exception as e:
                    log_error(f"[Auto-Scan] Rug score failed for {token_id}: {e}")

                return ("scanned", local_credits)

            # Run the worker with a hard wall-clock deadline. The orphaned thread
            # (if it times out) will keep running in the background but the main
            # scan thread is unblocked. This is the single most important fix —
            # it's what stops a stuck Helius call from freezing the whole scan.
            status = "failed"
            credits_used = 0
            try:
                with ThreadPoolExecutor(max_workers=1, thread_name_prefix="auto-scan-token") as exec_:
                    future = exec_.submit(_analyze_one_token)
                    status, credits_used = future.result(timeout=per_token_timeout)
            except FuturesTimeoutError:
                log_error(
                    f"[Auto-Scan] TIMEOUT after {per_token_timeout}s on {address} "
                    f"({token.get('token_name') or '?'}) — abandoning, scan continues"
                )
                status = "timeout"
                # Cannot kill the orphaned thread, but it'll eventually exit on its own
                # when the underlying HTTP call returns/errors.
            except Exception as e:
                log_error(f"[Auto-Scan] Failed {address}: {e}")
                status = "failed"

            # Always advance counters + heartbeat exactly once per token attempt,
            # regardless of success/failure/timeout. Prevents the progress display
            # from sticking on a single token forever.
            result["credits_used"] += credits_used
            if status == "scanned":
                existing_addresses.add(address)
                scanned += 1
                result["tokens_scanned"] += 1
            elif status == "no_data":
                result["tokens_failed"] += 1
            else:  # "failed" or "timeout"
                result["tokens_failed"] += 1
            _scan_progress["current"] = scanned + result["tokens_failed"]
            _scan_progress["credits_used"] = result["credits_used"]
            _bump_heartbeat()

        from meridinate.credit_tracker import get_credit_tracker
        get_credit_tracker().record_operation(
            operation="auto_scan", label="Auto-Scan", credits=result["credits_used"],
            call_count=result["tokens_scanned"], context={"filtered": result["tokens_filtered"]},
        )
        CURRENT_INGEST_SETTINGS["last_discovery_run_at"] = datetime.now().isoformat()
        save_ingest_settings(CURRENT_INGEST_SETTINGS)
        result["completed_at"] = datetime.now().isoformat()
        log_info(f"[Auto-Scan] Complete: {result['tokens_scanned']} scanned, {result['credits_used']} credits")

        # Auto-compute real PnL for newly recurring wallets
        try:
            pnl_result = _compute_pnl_for_new_recurring_wallets()
            result["pnl_wallets_computed"] = pnl_result.get("wallets_computed", 0)
            result["pnl_credits_used"] = pnl_result.get("credits_used", 0)
            result["credits_used"] += pnl_result.get("credits_used", 0)
        except Exception as e:
            log_error(f"[Auto-Scan] PnL auto-compute failed: {e}")

    except Exception as e:
        log_error(f"[Auto-Scan] Error: {e}")
        result["errors"].append(str(e))
        result["completed_at"] = datetime.now().isoformat()
    finally:
        _clear_progress()
    return result


async def run_auto_scan(
    max_tokens: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Async wrapper for Auto-Scan. Used by the scheduler.
    Delegates to run_auto_scan_sync in a thread to avoid blocking the event loop.
    """
    import asyncio
    return await asyncio.to_thread(run_auto_scan_sync, max_tokens)


async def run_tier0_ingestion(
    max_tokens: Optional[int] = None,
    mc_min: Optional[float] = None,
    volume_min: Optional[float] = None,
    liquidity_min: Optional[float] = None,
    age_max_hours: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Discovery Ingestion: Fetch tokens from DexScreener (free, no Helius credits).

    - Fetches recently migrated/listed tokens from DexScreener
    - Dedupes against analyzed_tokens and existing queue entries
    - Stores tokens with tier='ingested', status='pending'
    - Updates snapshots (MC, volume, liquidity, age)

    Args:
        max_tokens: Override tier0_max_tokens_per_run setting
        mc_min: Override mc_min threshold
        volume_min: Override volume_min threshold
        liquidity_min: Override liquidity_min threshold
        age_max_hours: Override age_max_hours threshold

    Returns:
        Dictionary with ingestion results
    """
    settings = CURRENT_INGEST_SETTINGS

    # Use settings or overrides
    max_tokens = max_tokens or settings.get("tier0_max_tokens_per_run", 50)
    mc_min = mc_min if mc_min is not None else settings.get("mc_min", 10000)
    volume_min = volume_min if volume_min is not None else settings.get("volume_min", 5000)
    liquidity_min = liquidity_min if liquidity_min is not None else settings.get("liquidity_min", 5000)
    age_max_hours = age_max_hours if age_max_hours is not None else settings.get("age_max_hours", 48)

    log_info(
        f"[Discovery] Starting ingestion: max={max_tokens}, mc>=${mc_min}, "
        f"vol>=${volume_min}, liq>=${liquidity_min}, age<={age_max_hours}h"
    )

    result = {
        "tokens_fetched": 0,
        "tokens_new": 0,
        "tokens_updated": 0,
        "tokens_skipped": 0,
        "errors": [],
        "started_at": datetime.now().isoformat(),
        "completed_at": None,
    }

    try:
        # Get existing addresses for deduplication
        existing_addresses = db.get_existing_token_addresses()
        log_info(f"[Discovery] Found {len(existing_addresses)} existing addresses to dedupe against")

        # Fetch tokens from DexScreener
        dexscreener = get_dexscreener_service()
        tokens, fetched_count = dexscreener.fetch_recent_migrated_tokens(
            max_tokens=max_tokens * 2,  # Fetch extra to account for deduplication
            min_mc=mc_min,
            min_volume=volume_min,
            min_liquidity=liquidity_min,
            max_age_hours=age_max_hours,
        )
        result["tokens_fetched"] = fetched_count

        # Load pipeline filters from settings
        launchpad_include = [x.lower() for x in settings.get("launchpad_include", [])]
        launchpad_exclude = [x.lower() for x in settings.get("launchpad_exclude", [])]
        quote_token_include = [x.upper() for x in settings.get("quote_token_include", [])]
        address_suffix_include = [x.lower() for x in settings.get("address_suffix_include", [])]
        buys_24h_min = settings.get("buys_24h_min")
        sells_24h_max = settings.get("sells_24h_max")
        net_buys_24h_min = settings.get("net_buys_24h_min")
        txs_24h_min = settings.get("txs_24h_min")
        price_change_h1_min = settings.get("price_change_h1_min")
        keyword_include = [k.lower() for k in settings.get("keyword_include", [])]
        keyword_exclude = [k.lower() for k in settings.get("keyword_exclude", [])]
        require_socials = settings.get("require_socials", False)
        mc_max = settings.get("mc_max")

        # Process tokens
        processed = 0
        filtered_out = 0
        for token in tokens:
            if processed >= max_tokens:
                break

            address = token.get("token_address")
            if not address:
                continue

            # Skip if already exists in analyzed_tokens
            if address in existing_addresses:
                result["tokens_skipped"] += 1
                continue

            # Apply pipeline filters
            dex_id = (token.get("dex_id") or "").lower()
            quote = (token.get("quote_token") or "").upper()
            name_lower = (token.get("token_name") or "").lower()
            addr_lower = address.lower()

            # Launchpad + address suffix: pass if EITHER matches (OR logic)
            launchpad_ok = not launchpad_include or dex_id in launchpad_include
            suffix_ok = not address_suffix_include or any(addr_lower.endswith(s) for s in address_suffix_include)
            if launchpad_include or address_suffix_include:
                if not launchpad_ok and not suffix_ok:
                    filtered_out += 1
                    continue
            if launchpad_exclude and dex_id in launchpad_exclude:
                filtered_out += 1
                continue

            # Quote token filter
            if quote_token_include and quote not in quote_token_include:
                filtered_out += 1
                continue

            # MC max filter
            if mc_max is not None and (token.get("market_cap_usd") or 0) > mc_max:
                filtered_out += 1
                continue

            # Transaction count filters
            if buys_24h_min is not None and (token.get("buys_24h") or 0) < buys_24h_min:
                filtered_out += 1
                continue
            if sells_24h_max is not None and (token.get("sells_24h") or 0) > sells_24h_max:
                filtered_out += 1
                continue
            if net_buys_24h_min is not None and (token.get("net_buys_24h") or 0) < net_buys_24h_min:
                filtered_out += 1
                continue
            if txs_24h_min is not None and (token.get("txs_24h") or 0) < txs_24h_min:
                filtered_out += 1
                continue

            # Price change filter
            if price_change_h1_min is not None and (token.get("price_change_h1") or 0) < price_change_h1_min:
                filtered_out += 1
                continue

            # Keyword filters
            if keyword_include and not any(kw in name_lower for kw in keyword_include):
                filtered_out += 1
                continue
            if keyword_exclude and any(kw in name_lower for kw in keyword_exclude):
                filtered_out += 1
                continue

            # Social links filter
            if require_socials and not token.get("has_socials"):
                filtered_out += 1
                continue

            # Try to insert new entry
            inserted = db.insert_ingest_queue_entry(
                token_address=address,
                token_name=token.get("token_name"),
                token_symbol=token.get("token_symbol"),
                source="dexscreener",
                last_mc_usd=token.get("market_cap_usd"),
                last_volume_usd=token.get("volume_24h_usd"),
                last_liquidity=token.get("liquidity_usd"),
                age_hours=token.get("age_hours"),
                dex_id=token.get("dex_id"),
                quote_token=token.get("quote_token"),
                buys_24h=token.get("buys_24h"),
                sells_24h=token.get("sells_24h"),
                net_buys_24h=token.get("net_buys_24h"),
                txs_24h=token.get("txs_24h"),
                price_change_h1=token.get("price_change_h1"),
                price_change_h6=token.get("price_change_h6"),
                price_change_h24=token.get("price_change_h24"),
                has_socials=token.get("has_socials", False),
            )

            if inserted:
                result["tokens_new"] += 1
                processed += 1
            else:
                # Already in queue - update snapshot
                db.update_ingest_queue_snapshot(
                    token_address=address,
                    last_mc_usd=token.get("market_cap_usd"),
                    last_volume_usd=token.get("volume_24h_usd"),
                    last_liquidity=token.get("liquidity_usd"),
                    age_hours=token.get("age_hours"),
                )
                result["tokens_updated"] += 1
                processed += 1

        # Update last run timestamp
        CURRENT_INGEST_SETTINGS["last_tier0_run_at"] = datetime.now().isoformat()
        save_ingest_settings(CURRENT_INGEST_SETTINGS)

        result["tokens_filtered"] = filtered_out
        result["completed_at"] = datetime.now().isoformat()
        log_info(
            f"[Discovery] Complete: {result['tokens_new']} new, "
            f"{result['tokens_updated']} updated, {result['tokens_skipped']} skipped, "
            f"{filtered_out} filtered out by pipeline"
        )

    except Exception as e:
        log_error(f"[Discovery] Error: {e}")
        result["errors"].append(str(e))
        result["completed_at"] = datetime.now().isoformat()

    return result



async def run_hot_token_refresh(
    max_age_hours: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Refresh MC/volume/liquidity snapshots for hot tokens (free, DexScreener).

    "Hot" tokens are recently ingested/enriched tokens (within max_age_hours).
    This keeps their metrics fresh for promotion decisions.

    Args:
        max_age_hours: Override age threshold for hot tokens (default: 48h)
        max_tokens: Override max tokens to refresh (default: 100)

    Returns:
        Dictionary with refresh results
    """
    settings = CURRENT_INGEST_SETTINGS

    max_age_hours = max_age_hours or settings.get("hot_refresh_age_hours", 48)
    max_tokens = max_tokens or settings.get("hot_refresh_max_tokens", 100)

    log_info(f"[Hot Refresh] Starting: max_age={max_age_hours}h, max_tokens={max_tokens}")

    result = {
        "tokens_checked": 0,
        "tokens_updated": 0,
        "tokens_failed": 0,
        "errors": [],
        "started_at": datetime.now().isoformat(),
        "completed_at": None,
    }

    try:
        # Get hot tokens from queue
        hot_tokens = db.get_hot_ingest_tokens(max_age_hours=max_age_hours, limit=max_tokens)
        result["tokens_checked"] = len(hot_tokens)

        if not hot_tokens:
            log_info("[Hot Refresh] No hot tokens to refresh")
            result["completed_at"] = datetime.now().isoformat()
            return result

        log_info(f"[Hot Refresh] Found {len(hot_tokens)} hot tokens")

        # Get DexScreener service
        dexscreener = get_dexscreener_service()

        # Refresh each token
        updates = []
        perf_snapshots = []
        for token in hot_tokens:
            address = token["token_address"]
            tier = token.get("tier", "ingested")
            try:
                snapshot = dexscreener.get_token_snapshot(address)
                if snapshot:
                    updates.append({
                        "token_address": address,
                        "last_mc_usd": snapshot.get("market_cap_usd"),
                        "last_volume_usd": snapshot.get("volume_24h_usd"),
                        "last_liquidity": snapshot.get("liquidity_usd"),
                        "age_hours": snapshot.get("age_hours"),
                    })
                    # Build performance snapshot for scoring
                    perf_snapshots.append({
                        "token_address": address,
                        "price_usd": snapshot.get("price_usd"),
                        "mc_usd": snapshot.get("market_cap_usd"),
                        "volume_24h_usd": snapshot.get("volume_24h_usd"),
                        "liquidity_usd": snapshot.get("liquidity_usd"),
                        "ingest_tier_snapshot": tier,
                    })
                else:
                    result["tokens_failed"] += 1
            except Exception as e:
                log_error(f"[Hot Refresh] Error refreshing {address}: {e}")
                result["errors"].append(f"{address}: {str(e)}")
                result["tokens_failed"] += 1

        # Bulk update ingest queue snapshots
        if updates:
            result["tokens_updated"] = db.bulk_update_ingest_snapshots(updates)

        # Save performance snapshots for scoring
        if perf_snapshots:
            snapshots_saved = db.bulk_save_performance_snapshots(perf_snapshots)
            result["snapshots_saved"] = snapshots_saved
            log_info(f"[Hot Refresh] Saved {snapshots_saved} performance snapshots")

        # Run scoring if enabled
        if settings.get("score_enabled", False) and perf_snapshots:
            try:
                from meridinate.tasks.performance_scorer import score_tokens
                addresses = [s["token_address"] for s in perf_snapshots]
                score_result = await score_tokens(addresses)
                result["scoring"] = score_result
                log_info(
                    f"[Hot Refresh] Scoring complete: {score_result.get('tokens_scored', 0)} scored"
                )
            except Exception as e:
                log_error(f"[Hot Refresh] Scoring error: {e}")
                result["scoring_error"] = str(e)

        # Update last run timestamp
        CURRENT_INGEST_SETTINGS["last_hot_refresh_at"] = datetime.now().isoformat()
        save_ingest_settings(CURRENT_INGEST_SETTINGS)

        result["completed_at"] = datetime.now().isoformat()
        log_info(
            f"[Hot Refresh] Complete: {result['tokens_updated']} updated, "
            f"{result['tokens_failed']} failed"
        )

    except Exception as e:
        log_error(f"[Hot Refresh] Error: {e}")
        result["errors"].append(str(e))
        result["completed_at"] = datetime.now().isoformat()

    return result


async def promote_tokens_to_analysis(
    token_addresses: List[str],
    register_webhooks: bool = True,
) -> Dict[str, Any]:
    """
    Promote tokens from enriched tier to full analysis.

    - Runs FULL token analysis for each token (early bidder detection, MTEW, etc.)
    - Saves to analyzed_tokens table with ingest metadata
    - Updates tier='analyzed' in queue
    - Registers SWAB webhooks for tracking (if enabled)

    Args:
        token_addresses: List of token addresses to promote
        register_webhooks: Whether to register SWAB webhooks (default: True)

    Returns:
        Dictionary with promotion results
    """
    import json
    import os
    from meridinate.helius_api import TokenAnalyzer, WebhookManager, generate_axiom_export, generate_token_acronym
    from meridinate.tasks.position_tracker import record_mtew_positions_for_token
    from meridinate.settings import CURRENT_API_SETTINGS

    result = {
        "tokens_promoted": 0,
        "tokens_failed": 0,
        "credits_used": 0,
        "webhooks_registered": 0,
        "errors": [],
        "started_at": datetime.now().isoformat(),
        "completed_at": None,
    }

    for address in token_addresses:
        try:
            # Check token is in ingested or enriched tier (both can be promoted)
            entry = db.get_ingest_queue_entry(address)
            if not entry or entry["tier"] not in ("ingested", "enriched"):
                result["errors"].append(f"{address}: Not in ingested/enriched tier")
                result["tokens_failed"] += 1
                continue

            log_info(f"[Promote] Starting full analysis for {address}")

            # Initialize analyzer and run full analysis
            analyzer = TokenAnalyzer(HELIUS_API_KEY)
            analysis_result = analyzer.analyze_token(
                mint_address=address,
                min_usd=CURRENT_API_SETTINGS.get("minUsdFilter", 50.0),
                time_window_hours=72,
                max_transactions=CURRENT_API_SETTINGS.get("transactionLimit", 500),
                max_credits=CURRENT_API_SETTINGS.get("maxCreditsPerAnalysis", 1000),
                max_wallets_to_store=CURRENT_API_SETTINGS.get("walletCount", 10),
                top_holders_limit=CURRENT_API_SETTINGS.get("topHoldersLimit", 10),
            )

            credits_used = analysis_result.get("api_credits_used", 0)
            result["credits_used"] += credits_used

            # Extract token info
            token_info = analysis_result.get("token_info")
            if token_info is None:
                token_name = entry.get("token_name") or "Unknown"
                token_symbol = entry.get("token_symbol") or "UNK"
            else:
                metadata = token_info.get("onChainMetadata", {}).get("metadata", {})
                token_name = metadata.get("name") or entry.get("token_name") or "Unknown"
                token_symbol = metadata.get("symbol") or entry.get("token_symbol") or "UNK"

            # Check if analysis found meaningful data
            early_bidders = analysis_result.get("early_bidders", [])
            if len(early_bidders) == 0 and token_info is None:
                error_msg = analysis_result.get("error", "No transactions found")
                log_info(f"[Promote] Analysis for {address} found no data: {error_msg}")
                db.update_ingest_queue_tier(address, "analyzed", error=error_msg)
                result["tokens_failed"] += 1
                result["errors"].append(f"{address}: {error_msg}")
                continue

            # Generate acronym
            acronym = generate_token_acronym(token_name, token_symbol)

            # Convert datetime objects to strings
            for bidder in early_bidders:
                if "first_buy_time" in bidder and hasattr(bidder["first_buy_time"], "isoformat"):
                    bidder["first_buy_time"] = bidder["first_buy_time"].isoformat()

            # Generate Axiom export
            max_wallets = CURRENT_API_SETTINGS.get("walletCount", 10)
            axiom_export = generate_axiom_export(
                early_bidders=early_bidders,
                token_name=token_name,
                token_symbol=token_symbol,
                limit=max_wallets,
            )

            # Save to database with ingest metadata
            token_id = db.save_analyzed_token(
                token_address=address,
                token_name=token_name,
                token_symbol=token_symbol,
                acronym=acronym,
                early_bidders=early_bidders,
                axiom_json=axiom_export,
                first_buy_timestamp=analysis_result.get("first_transaction_time"),
                credits_used=credits_used,
                max_wallets=max_wallets,
                market_cap_usd=analysis_result.get("market_cap_usd"),
                liquidity_usd=entry.get("last_liquidity"),
                top_holders=analysis_result.get("top_holders"),
                ingest_source=entry.get("source", "ingest_queue"),
                ingest_tier="enriched",
                deployer_address=analysis_result.get("deployer_address"),
                creation_events=analysis_result.get("creation_events"),
            )
            log_info(f"[Promote] Saved token to DB: id={token_id}, acronym={acronym}")

            # Update multi-token wallet metadata
            try:
                newly_marked = db.update_multi_token_wallet_metadata(token_id)
                if newly_marked > 0:
                    log_info(f"[Promote] Marked {newly_marked} wallet(s) as NEW in recurring wallets")
            except Exception as meta_err:
                log_error(f"[Promote] Failed to update multi-token wallet metadata: {meta_err}")

            # Track positions for win rate calculation
            try:
                position_result = record_mtew_positions_for_token(
                    token_id=token_id,
                    token_address=address,
                    entry_market_cap=analysis_result.get("market_cap_usd"),
                    top_holders=analysis_result.get("top_holders"),
                )
                if position_result["positions_tracked"] > 0:
                    log_info(f"[Promote] Recorded {position_result['positions_tracked']} position(s)")
            except Exception as pos_err:
                log_error(f"[Promote] Failed to record positions: {pos_err}")

            # JSON file generation disabled — data is stored in SQLite database

            # Invalidate caches so the new analysis shows up immediately
            try:
                from meridinate.routers.tokens import cache as tokens_cache
                tokens_cache.invalidate("tokens_history")
            except Exception:
                pass
            try:
                from meridinate.routers.wallets import cache as wallets_cache
                wallets_cache.invalidate("multi_early_buyer_wallets")
            except Exception:
                pass

            # Mark as analyzed in the queue
            db.update_ingest_queue_tier(address, "analyzed")
            result["tokens_promoted"] += 1

            log_info(f"[Promote] Successfully promoted {address} (id={token_id}, {len(early_bidders)} wallets)")

        except Exception as e:
            log_error(f"[Promote] Error promoting {address}: {e}")
            result["errors"].append(f"{address}: {str(e)}")
            result["tokens_failed"] += 1

    # Register SWAB webhooks for all promoted tokens if enabled
    if register_webhooks and result["tokens_promoted"] > 0 and HELIUS_API_KEY:
        try:
            # Get all active SWAB wallets (includes newly promoted tokens)
            wallet_addresses = db.get_active_swab_wallets()

            if wallet_addresses:
                webhook_manager = WebhookManager(HELIUS_API_KEY)
                webhook_result = webhook_manager.create_webhook(
                    webhook_url=f"{API_BASE_URL}/webhooks/callback",
                    wallet_addresses=wallet_addresses,
                    transaction_types=["TRANSFER", "SWAP"],
                )
                if webhook_result and webhook_result.get("webhookID"):
                    result["webhooks_registered"] = 1
                    log_info(
                        f"[Promote] Registered position webhook for {len(wallet_addresses)} wallets "
                        f"(ID: {webhook_result['webhookID']})"
                    )
        except Exception as e:
            log_error(f"[Promote] Failed to register position webhook: {e}")
            result["errors"].append(f"Webhook registration failed: {str(e)}")

    result["completed_at"] = datetime.now().isoformat()
    return result


async def run_auto_promote(
    max_promotions: Optional[int] = None,
    register_webhooks: bool = True,
) -> Dict[str, Any]:
    """
    Auto-promote enriched tokens to full analysis.

    Called after Tier-1 enrichment (deprecated) when auto_promote_enabled is True.

    Args:
        max_promotions: Maximum tokens to promote per run (default: from settings)
        register_webhooks: Whether to register SWAB webhooks (default: True)

    Returns:
        Dictionary with auto-promotion results
    """
    settings = CURRENT_INGEST_SETTINGS

    # Check if auto-promote is enabled
    if not settings.get("auto_promote_enabled"):
        log_info("[Auto-Promote] Disabled, skipping")
        return {
            "status": "disabled",
            "tokens_promoted": 0,
            "started_at": datetime.now().isoformat(),
            "completed_at": datetime.now().isoformat(),
        }

    max_promotions = max_promotions or settings.get("auto_promote_max_per_run", 5)

    log_info(f"[Auto-Promote] Starting: max_promotions={max_promotions}")

    # Get enriched tokens ready for promotion
    enriched_tokens = db.get_enriched_tokens_for_promotion(limit=max_promotions)

    if not enriched_tokens:
        log_info("[Auto-Promote] No enriched tokens to promote")
        return {
            "status": "no_candidates",
            "tokens_promoted": 0,
            "started_at": datetime.now().isoformat(),
            "completed_at": datetime.now().isoformat(),
        }

    # Promote the tokens
    token_addresses = [t["token_address"] for t in enriched_tokens]
    result = await promote_tokens_to_analysis(
        token_addresses=token_addresses,
        register_webhooks=register_webhooks,
    )

    log_info(
        f"[Auto-Promote] Complete: {result['tokens_promoted']} promoted, "
        f"{result['webhooks_registered']} webhooks registered"
    )

    return result
