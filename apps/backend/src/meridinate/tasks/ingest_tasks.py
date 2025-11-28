"""
Ingest Pipeline Tasks

Implements Tier-0 ingestion and Tier-1 enrichment jobs for the token discovery pipeline.

Tier-0: Fetch tokens from DexScreener (free), dedupe, store snapshots
Tier-1: Enrich tokens with Helius data (budgeted), apply thresholds
Hot Refresh: Update MC/volume for recently ingested tokens (free)
Auto-promote: Promote enriched tokens to full analysis
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from meridinate import analyzed_tokens_db as db
from meridinate.observability import log_error, log_info
from meridinate.services.dexscreener_service import get_dexscreener_service
from meridinate.settings import CURRENT_INGEST_SETTINGS, save_ingest_settings, HELIUS_API_KEY


async def run_tier0_ingestion(
    max_tokens: Optional[int] = None,
    mc_min: Optional[float] = None,
    volume_min: Optional[float] = None,
    liquidity_min: Optional[float] = None,
    age_max_hours: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Tier-0 Ingestion: Fetch tokens from DexScreener (free, no Helius credits).

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
        f"[Tier-0] Starting ingestion: max={max_tokens}, mc>=${mc_min}, "
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
        log_info(f"[Tier-0] Found {len(existing_addresses)} existing addresses to dedupe against")

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

        # Process tokens
        processed = 0
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

        result["completed_at"] = datetime.now().isoformat()
        log_info(
            f"[Tier-0] Complete: {result['tokens_new']} new, "
            f"{result['tokens_updated']} updated, {result['tokens_skipped']} skipped"
        )

    except Exception as e:
        log_error(f"[Tier-0] Error: {e}")
        result["errors"].append(str(e))
        result["completed_at"] = datetime.now().isoformat()

    return result


async def run_tier1_enrichment(
    batch_size: Optional[int] = None,
    credit_budget: Optional[int] = None,
    mc_min: Optional[float] = None,
    volume_min: Optional[float] = None,
    liquidity_min: Optional[float] = None,
    age_max_hours: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Tier-1 Enrichment: Enrich tokens with Helius data (budgeted).

    - Selects tokens from queue with tier='ingested' passing thresholds
    - Calls minimal Helius endpoints (metadata + top holders)
    - Tracks credits used and respects budget
    - Updates tier='enriched' on success

    Args:
        batch_size: Override tier1_batch_size setting
        credit_budget: Override tier1_credit_budget_per_run setting
        mc_min: Override mc_min threshold
        volume_min: Override volume_min threshold
        liquidity_min: Override liquidity_min threshold
        age_max_hours: Override age_max_hours threshold

    Returns:
        Dictionary with enrichment results
    """
    from meridinate.helius_api import HeliusAPI
    from meridinate.settings import HELIUS_API_KEY

    settings = CURRENT_INGEST_SETTINGS

    # Use settings or overrides
    batch_size = batch_size or settings.get("tier1_batch_size", 10)
    credit_budget = credit_budget or settings.get("tier1_credit_budget_per_run", 100)
    mc_min = mc_min if mc_min is not None else settings.get("mc_min", 10000)
    volume_min = volume_min if volume_min is not None else settings.get("volume_min", 5000)
    liquidity_min = liquidity_min if liquidity_min is not None else settings.get("liquidity_min", 5000)
    age_max_hours = age_max_hours if age_max_hours is not None else settings.get("age_max_hours", 48)

    log_info(
        f"[Tier-1] Starting enrichment: batch={batch_size}, budget={credit_budget} credits, "
        f"mc>=${mc_min}, vol>=${volume_min}"
    )

    result = {
        "tokens_processed": 0,
        "tokens_enriched": 0,
        "tokens_failed": 0,
        "credits_used": 0,
        "errors": [],
        "started_at": datetime.now().isoformat(),
        "completed_at": None,
    }

    try:
        # Get candidates for enrichment
        candidates = db.get_ingest_queue_candidates_for_enrichment(
            mc_min=mc_min,
            volume_min=volume_min,
            liquidity_min=liquidity_min,
            age_max_hours=age_max_hours,
            limit=batch_size,
        )

        if not candidates:
            log_info("[Tier-1] No candidates found for enrichment")
            result["completed_at"] = datetime.now().isoformat()
            return result

        log_info(f"[Tier-1] Found {len(candidates)} candidates for enrichment")

        # Initialize Helius API
        helius = HeliusAPI(HELIUS_API_KEY)

        for token in candidates:
            # Check credit budget
            if result["credits_used"] >= credit_budget:
                log_info(f"[Tier-1] Credit budget exhausted ({credit_budget}), stopping")
                break

            address = token["token_address"]
            result["tokens_processed"] += 1

            try:
                # Fetch token metadata (1 credit)
                metadata, meta_credits = helius.get_token_metadata(address)
                result["credits_used"] += meta_credits

                if not metadata:
                    log_info(f"[Tier-1] No metadata for {address}, skipping")
                    db.update_ingest_queue_tier(address, "ingested", error="No metadata found")
                    result["tokens_failed"] += 1
                    continue

                # Fetch top holders (11-21 credits: 1 + up to 10 owner lookups + up to 10 balances)
                # But we'll use a smaller limit for enrichment to save credits
                top_holders, holders_credits = helius.get_top_holders(address, limit=5)
                result["credits_used"] += holders_credits

                # Update token with enrichment data
                # For now, just mark as enriched - actual holder data can be stored later
                # when we add enrichment_data column or similar
                db.update_ingest_queue_tier(address, "enriched")
                result["tokens_enriched"] += 1

                log_info(f"[Tier-1] Enriched {address}: {meta_credits + holders_credits} credits")

            except Exception as e:
                log_error(f"[Tier-1] Error enriching {address}: {e}")
                db.update_ingest_queue_tier(address, "ingested", error=str(e))
                result["tokens_failed"] += 1
                result["errors"].append(f"{address}: {str(e)}")

        # Update run tracking
        CURRENT_INGEST_SETTINGS["last_tier1_run_at"] = datetime.now().isoformat()
        CURRENT_INGEST_SETTINGS["last_tier1_credits_used"] = result["credits_used"]
        save_ingest_settings(CURRENT_INGEST_SETTINGS)

        result["completed_at"] = datetime.now().isoformat()
        log_info(
            f"[Tier-1] Complete: {result['tokens_enriched']} enriched, "
            f"{result['tokens_failed']} failed, {result['credits_used']} credits used"
        )

        # Auto-promote if enabled (runs after enrichment)
        if settings.get("auto_promote_enabled") and result["tokens_enriched"] > 0:
            log_info("[Tier-1] Triggering auto-promote after enrichment")
            auto_promote_result = await run_auto_promote()
            result["auto_promote"] = auto_promote_result

    except Exception as e:
        log_error(f"[Tier-1] Error: {e}")
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
        for token in hot_tokens:
            address = token["token_address"]
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
                else:
                    result["tokens_failed"] += 1
            except Exception as e:
                log_error(f"[Hot Refresh] Error refreshing {address}: {e}")
                result["errors"].append(f"{address}: {str(e)}")
                result["tokens_failed"] += 1

        # Bulk update snapshots
        if updates:
            result["tokens_updated"] = db.bulk_update_ingest_snapshots(updates)

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
    from meridinate.settings import CURRENT_API_SETTINGS, ANALYSIS_RESULTS_DIR, AXIOM_EXPORTS_DIR

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
            # Check token is in enriched tier
            entry = db.get_ingest_queue_entry(address)
            if not entry or entry["tier"] != "enriched":
                result["errors"].append(f"{address}: Not in enriched tier")
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
                top_holders=analysis_result.get("top_holders"),
                ingest_source=entry.get("source", "ingest_queue"),
                ingest_tier="enriched",
            )
            log_info(f"[Promote] Saved token to DB: id={token_id}, acronym={acronym}")

            # Update multi-token wallet metadata
            try:
                newly_marked = db.update_multi_token_wallet_metadata(token_id)
                if newly_marked > 0:
                    log_info(f"[Promote] Marked {newly_marked} wallet(s) as NEW in multi-token panel")
            except Exception as meta_err:
                log_error(f"[Promote] Failed to update multi-token wallet metadata: {meta_err}")

            # Track MTEW positions for win rate calculation
            try:
                position_result = record_mtew_positions_for_token(
                    token_id=token_id,
                    token_address=address,
                    entry_market_cap=analysis_result.get("market_cap_usd"),
                    top_holders=analysis_result.get("top_holders"),
                )
                if position_result["positions_tracked"] > 0:
                    log_info(f"[Promote] Recorded {position_result['positions_tracked']} MTEW position(s)")
            except Exception as pos_err:
                log_error(f"[Promote] Failed to record MTEW positions: {pos_err}")

            # Save analysis files
            analysis_filepath = db.get_analysis_file_path(token_id, token_name, in_trash=False)
            axiom_filepath = db.get_axiom_file_path(token_id, acronym, in_trash=False)

            os.makedirs(os.path.dirname(analysis_filepath), exist_ok=True)
            os.makedirs(os.path.dirname(axiom_filepath), exist_ok=True)

            with open(analysis_filepath, "w") as f:
                json.dump(analysis_result, f, indent=2)
            with open(axiom_filepath, "w") as f:
                json.dump(axiom_export, f, indent=2)

            db.update_token_file_paths(token_id, analysis_filepath, axiom_filepath)

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
                    webhook_url="http://localhost:5003/webhooks/callback",
                    wallet_addresses=wallet_addresses,
                    transaction_types=["TRANSFER", "SWAP"],
                )
                if webhook_result and webhook_result.get("webhookID"):
                    result["webhooks_registered"] = 1
                    log_info(
                        f"[Promote] Registered SWAB webhook for {len(wallet_addresses)} wallets "
                        f"(ID: {webhook_result['webhookID']})"
                    )
        except Exception as e:
            log_error(f"[Promote] Failed to register SWAB webhook: {e}")
            result["errors"].append(f"Webhook registration failed: {str(e)}")

    result["completed_at"] = datetime.now().isoformat()
    return result


async def run_auto_promote(
    max_promotions: Optional[int] = None,
    register_webhooks: bool = True,
) -> Dict[str, Any]:
    """
    Auto-promote enriched tokens to full analysis.

    Called after Tier-1 enrichment when auto_promote_enabled is True.

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
