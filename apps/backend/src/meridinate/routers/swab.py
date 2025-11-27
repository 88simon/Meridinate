"""
SWAB (Smart Wallet Archive Builder) Router
===========================================
API endpoints for SWAB position tracking, settings, and controls.
"""

from typing import Optional, List

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from meridinate import analyzed_tokens_db as db
from meridinate.observability import log_error, log_info
from meridinate.settings import HELIUS_API_KEY

router = APIRouter(prefix="/api/swab")


# =============================================================================
# Request/Response Models
# =============================================================================


class SwabSettingsResponse(BaseModel):
    """SWAB settings response model."""

    auto_check_enabled: bool
    check_interval_minutes: int
    daily_credit_budget: int
    stale_threshold_minutes: int
    min_token_count: int
    last_check_at: Optional[str] = None
    credits_used_today: int
    credits_reset_date: Optional[str] = None
    updated_at: Optional[str] = None


class SwabSettingsUpdate(BaseModel):
    """SWAB settings update request model."""

    auto_check_enabled: Optional[bool] = None
    check_interval_minutes: Optional[int] = Field(None, ge=5, le=1440)
    daily_credit_budget: Optional[int] = Field(None, ge=0, le=10000)
    stale_threshold_minutes: Optional[int] = Field(None, ge=5, le=1440)
    min_token_count: Optional[int] = Field(None, ge=1, le=50)


class SwabStatsResponse(BaseModel):
    """SWAB overview statistics response model."""

    total_positions: int
    holding: int
    sold: int
    winners: int
    losers: int
    win_rate: Optional[float] = None
    avg_pnl_ratio: Optional[float] = None
    unique_wallets: int
    unique_tokens: int
    stale_positions: int
    estimated_check_credits: int
    credits_used_today: int
    daily_credit_budget: int
    credits_remaining: int


class PositionResponse(BaseModel):
    """Individual position response model."""

    id: int
    wallet_address: str
    token_id: int
    token_name: str
    token_symbol: str
    token_address: str
    entry_timestamp: Optional[str] = None
    entry_market_cap: Optional[float] = None
    current_market_cap: Optional[float] = None
    still_holding: bool
    current_balance: Optional[float] = None
    current_balance_usd: Optional[float] = None
    pnl_ratio: Optional[float] = None
    fpnl_ratio: Optional[float] = None  # Fumbled PnL: what they would have made if held
    exit_detected_at: Optional[str] = None
    exit_market_cap: Optional[float] = None
    position_checked_at: Optional[str] = None
    tracking_enabled: bool
    tracking_stopped_at: Optional[str] = None
    tracking_stopped_reason: Optional[str] = None
    # New fields for USD PnL and hold time
    entry_balance: Optional[float] = None
    entry_balance_usd: Optional[float] = None
    pnl_usd: Optional[float] = None
    hold_time_seconds: Optional[int] = None


class PositionsResponse(BaseModel):
    """Paginated positions response model."""

    positions: list[PositionResponse]
    total: int
    limit: int
    offset: int
    has_more: bool


class WalletSummaryResponse(BaseModel):
    """Wallet summary response model."""

    wallet_address: str
    total_positions: int
    holding_count: int
    sold_count: int
    win_count: int
    loss_count: int
    win_rate: Optional[float] = None
    avg_pnl_ratio: Optional[float] = None
    last_checked: Optional[str] = None


class StopTrackingRequest(BaseModel):
    """Request to stop tracking."""

    reason: str = "manual"


class BatchStopTrackingRequest(BaseModel):
    """Request to stop tracking multiple positions."""

    position_ids: list[int]
    reason: str = "manual"


class CheckResultResponse(BaseModel):
    """Position check result response model."""

    positions_checked: int
    still_holding: int
    sold: int
    errors: int
    credits_used: int
    duration_ms: int
    wallets_recalculated: int


class WalletExpectancyResponse(BaseModel):
    """Wallet expectancy calculation response model."""

    wallet_address: str
    expectancy: float
    win_rate: float
    avg_win: float
    avg_loss: float
    closed_positions: int
    wins: int
    losses: int
    current_label: Optional[str] = None


# =============================================================================
# Settings Endpoints
# =============================================================================


@router.get("/settings", response_model=SwabSettingsResponse, tags=["SWAB"])
async def get_settings():
    """Get SWAB configuration settings."""
    try:
        settings = db.get_swab_settings()
        return SwabSettingsResponse(**settings)
    except Exception as e:
        log_error(f"Error fetching SWAB settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/settings", response_model=SwabSettingsResponse, tags=["SWAB"])
async def update_settings(settings: SwabSettingsUpdate):
    """Update SWAB configuration settings."""
    try:
        updated = db.update_swab_settings(
            auto_check_enabled=settings.auto_check_enabled,
            check_interval_minutes=settings.check_interval_minutes,
            daily_credit_budget=settings.daily_credit_budget,
            stale_threshold_minutes=settings.stale_threshold_minutes,
            min_token_count=settings.min_token_count,
        )

        # Update scheduler if settings changed
        from meridinate.scheduler import update_scheduler_interval
        update_scheduler_interval()

        log_info(f"SWAB settings updated: {settings.dict(exclude_none=True)}")
        return SwabSettingsResponse(**updated)
    except Exception as e:
        log_error(f"Error updating SWAB settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scheduler/status", tags=["SWAB"])
async def get_scheduler_status():
    """Get SWAB scheduler status."""
    try:
        from meridinate.scheduler import get_scheduler_status
        return get_scheduler_status()
    except Exception as e:
        log_error(f"Error fetching scheduler status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Statistics Endpoints
# =============================================================================


@router.get("/stats", response_model=SwabStatsResponse, tags=["SWAB"])
async def get_stats():
    """Get SWAB overview statistics."""
    try:
        stats = db.get_swab_stats()
        return SwabStatsResponse(**stats)
    except Exception as e:
        log_error(f"Error fetching SWAB stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Position Endpoints
# =============================================================================


@router.get("/positions", response_model=PositionsResponse, tags=["SWAB"])
async def get_positions(
    min_token_count: Optional[int] = Query(None, ge=1, le=50),
    status: Optional[str] = Query(None, regex="^(holding|sold|stale|all)$"),
    pnl_min: Optional[float] = Query(None),
    pnl_max: Optional[float] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """
    Get tracked positions with filters.

    Query parameters:
    - min_token_count: Minimum tokens for MTEW to be included
    - status: Filter by status ('holding', 'sold', 'stale', 'all')
    - pnl_min: Minimum PnL ratio
    - pnl_max: Maximum PnL ratio
    - limit: Max positions to return (default 50, max 500)
    - offset: Pagination offset
    """
    try:
        result = db.get_swab_positions(
            min_token_count=min_token_count,
            status_filter=status,
            pnl_min=pnl_min,
            pnl_max=pnl_max,
            limit=limit,
            offset=offset,
        )
        return PositionsResponse(**result)
    except Exception as e:
        log_error(f"Error fetching SWAB positions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/wallets", response_model=list[WalletSummaryResponse], tags=["SWAB"])
async def get_wallet_summaries(
    min_token_count: Optional[int] = Query(None, ge=1, le=50),
):
    """
    Get aggregated wallet summaries for SWAB.

    Query parameters:
    - min_token_count: Minimum tokens for MTEW to be included
    """
    try:
        wallets = db.get_swab_wallet_summary(min_token_count=min_token_count)
        return [WalletSummaryResponse(**w) for w in wallets]
    except Exception as e:
        log_error(f"Error fetching SWAB wallet summaries: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Tracking Control Endpoints
# =============================================================================


@router.post("/positions/{position_id}/stop", tags=["SWAB"])
async def stop_position_tracking(position_id: int, request: StopTrackingRequest):
    """Stop tracking a specific position."""
    try:
        success = db.stop_tracking_position(position_id, reason=request.reason)
        if success:
            log_info(f"Stopped tracking position {position_id}: {request.reason}")
            return {"success": True, "message": f"Stopped tracking position {position_id}"}
        else:
            raise HTTPException(status_code=404, detail=f"Position {position_id} not found")
    except HTTPException:
        raise
    except Exception as e:
        log_error(f"Error stopping position tracking: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/positions/{position_id}/resume", tags=["SWAB"])
async def resume_position_tracking(position_id: int):
    """Resume tracking a previously stopped position."""
    try:
        success = db.resume_tracking_position(position_id)
        if success:
            log_info(f"Resumed tracking position {position_id}")
            return {"success": True, "message": f"Resumed tracking position {position_id}"}
        else:
            raise HTTPException(status_code=404, detail=f"Position {position_id} not found")
    except HTTPException:
        raise
    except Exception as e:
        log_error(f"Error resuming position tracking: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/wallets/{wallet_address}/stop", tags=["SWAB"])
async def stop_wallet_tracking(wallet_address: str, request: StopTrackingRequest):
    """Stop tracking all positions for a wallet."""
    try:
        count = db.stop_tracking_wallet_positions(wallet_address, reason=request.reason)
        log_info(f"Stopped tracking {count} positions for wallet {wallet_address[:8]}...")
        return {
            "success": True,
            "message": f"Stopped tracking {count} positions for wallet",
            "positions_stopped": count,
        }
    except Exception as e:
        log_error(f"Error stopping wallet tracking: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/positions/batch-stop", tags=["SWAB"])
async def batch_stop_position_tracking(request: BatchStopTrackingRequest):
    """Stop tracking multiple positions at once."""
    try:
        stopped_count = 0
        failed_ids = []

        for position_id in request.position_ids:
            try:
                success = db.stop_tracking_position(position_id, reason=request.reason)
                if success:
                    stopped_count += 1
                else:
                    failed_ids.append(position_id)
            except Exception:
                failed_ids.append(position_id)

        log_info(f"Batch stopped {stopped_count} positions, {len(failed_ids)} failed")
        return {
            "success": True,
            "positions_stopped": stopped_count,
            "failed_ids": failed_ids,
            "message": f"Stopped tracking {stopped_count} positions",
        }
    except Exception as e:
        log_error(f"Error batch stopping positions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Position Check Endpoints
# =============================================================================


@router.post("/check", response_model=CheckResultResponse, tags=["SWAB"])
async def trigger_position_check(
    max_positions: int = Query(50, ge=1, le=200),
    max_credits: Optional[int] = Query(None, ge=10, le=2000),
):
    """
    Manually trigger a position check cycle.

    Query parameters:
    - max_positions: Maximum positions to check (default 50)
    - max_credits: Maximum credits to spend (defaults to remaining daily budget)
    """
    from meridinate.tasks.position_tracker import check_mtew_positions

    try:
        # Get settings for credit budget
        settings = db.get_swab_settings()

        # Use remaining daily budget if not specified
        if max_credits is None:
            max_credits = settings["daily_credit_budget"] - settings["credits_used_today"]
            if max_credits <= 0:
                return CheckResultResponse(
                    positions_checked=0,
                    still_holding=0,
                    sold=0,
                    errors=0,
                    credits_used=0,
                    duration_ms=0,
                    wallets_recalculated=0,
                )

        log_info(f"Manual position check triggered: max_positions={max_positions}, max_credits={max_credits}")

        result = await check_mtew_positions(
            older_than_minutes=settings["stale_threshold_minutes"],
            max_positions=max_positions,
            max_credits=max_credits,
        )

        # Update SWAB credits used
        db.update_swab_last_check(credits_used=result.get("credits_used", 0))

        return CheckResultResponse(**result)
    except Exception as e:
        log_error(f"Error during position check: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/update-pnl", tags=["SWAB"])
async def trigger_pnl_update():
    """
    Update PnL ratios for all holding positions.

    This is a free operation (uses DexScreener, not Helius credits).
    """
    from meridinate.tasks.position_tracker import update_all_pnl_ratios

    try:
        log_info("Manual PnL update triggered")
        result = await update_all_pnl_ratios()
        return {
            "success": True,
            "tokens_updated": result["tokens_updated"],
            "positions_updated": result["positions_updated"],
            "duration_ms": result["duration_ms"],
        }
    except Exception as e:
        log_error(f"Error during PnL update: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Wallet Expectancy Endpoints
# =============================================================================


@router.get(
    "/expectancies",
    response_model=list[WalletExpectancyResponse],
    tags=["SWAB"],
)
async def get_wallet_expectancies(
    min_closed: int = Query(5, ge=1, le=100),
):
    """
    Get expectancy calculations for all wallets with sufficient closed positions.

    The expectancy formula is: (Win% × Avg_Win_Size) - (Loss% × Avg_Loss_Size)
    - Smart: Expectancy > 0.5 AND min_closed positions
    - Dumb: Expectancy < -0.2 AND min_closed positions

    Query parameters:
    - min_closed: Minimum closed positions required (default 5)
    """
    try:
        expectancies = db.get_all_wallet_expectancies(min_closed=min_closed)
        return [WalletExpectancyResponse(**e) for e in expectancies]
    except Exception as e:
        log_error(f"Error fetching wallet expectancies: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/expectancies/{wallet_address}",
    response_model=WalletExpectancyResponse,
    tags=["SWAB"],
)
async def get_wallet_expectancy(wallet_address: str):
    """
    Get expectancy calculation for a specific wallet.

    Returns the wallet's trading expectancy and Smart/Dumb label status.
    """
    try:
        result = db.calculate_wallet_expectancy(wallet_address)
        return WalletExpectancyResponse(**result)
    except Exception as e:
        log_error(f"Error fetching expectancy for {wallet_address[:8]}...: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/labels/update", tags=["SWAB"])
async def trigger_label_update():
    """
    Trigger a batch update of all Smart/Dumb labels.

    This recalculates expectancy for all eligible wallets and updates their labels.
    """
    try:
        # Get all wallets with sufficient closed positions
        expectancies = db.get_all_wallet_expectancies()
        wallet_addresses = [e["wallet_address"] for e in expectancies]

        # Batch update labels
        results = db.batch_update_wallet_labels(wallet_addresses)

        # Count results
        smart_count = sum(1 for label in results.values() if label == "smart")
        dumb_count = sum(1 for label in results.values() if label == "dumb")
        neutral_count = sum(1 for label in results.values() if label is None)

        log_info(
            f"Label update complete: {smart_count} smart, {dumb_count} dumb, {neutral_count} neutral"
        )

        return {
            "success": True,
            "wallets_processed": len(wallet_addresses),
            "smart_count": smart_count,
            "dumb_count": dumb_count,
            "neutral_count": neutral_count,
        }
    except Exception as e:
        log_error(f"Error during label update: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Data Management Endpoints
# =============================================================================


@router.post("/purge", tags=["SWAB"])
async def purge_swab_data():
    """
    Purge all SWAB position tracking data for a fresh start.

    This deletes:
    - All records from mtew_token_positions
    - All wallet metrics
    - Smart/Dumb labels from wallets

    Use this when you want to reset SWAB tracking entirely.
    """
    try:
        result = db.purge_swab_data()

        log_info(
            f"SWAB data purged: {result['positions_deleted']} positions, {result['metrics_deleted']} metrics deleted"
        )

        return {
            "success": True,
            "positions_deleted": result["positions_deleted"],
            "metrics_deleted": result["metrics_deleted"],
        }
    except Exception as e:
        log_error(f"Error purging SWAB data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Reconciliation Endpoints
# =============================================================================


class ReconciliationResultItem(BaseModel):
    """Individual position reconciliation result."""

    wallet_address: str
    token_symbol: str
    status: str  # "success", "no_tx_found", "error"
    old_pnl_ratio: Optional[float] = None
    new_pnl_ratio: Optional[float] = None
    tokens_sold: Optional[float] = None
    usd_received: Optional[float] = None
    error_message: Optional[str] = None


class ReconciliationResponse(BaseModel):
    """Reconciliation endpoint response."""

    positions_found: int
    positions_reconciled: int
    positions_no_tx_found: int
    positions_error: int
    credits_used: int
    results: List[ReconciliationResultItem]


@router.post(
    "/reconcile/{token_id}",
    response_model=ReconciliationResponse,
    tags=["SWAB"],
)
async def reconcile_token_positions(
    token_id: int,
    max_signatures: int = Query(50, ge=10, le=200),
):
    """
    Reconcile sold positions for a specific token using Helius transaction history.

    This endpoint fixes positions where:
    - The position was marked as sold (still_holding = 0)
    - But the sell was never recorded with actual price data (total_sold_usd = 0)

    For each such position, it:
    1. Fetches recent transaction history from Helius
    2. Finds the sell transaction (where wallet sent tokens)
    3. Updates the position with accurate USD received and PnL

    Query parameters:
    - max_signatures: Max signatures to check per wallet (default 50, max 200)
                      Higher = more likely to find old sells, but uses more credits

    Returns:
    - positions_found: Number of positions needing reconciliation
    - positions_reconciled: Successfully updated
    - positions_no_tx_found: Sell transaction not found in recent history
    - credits_used: Helius API credits consumed
    """
    if not HELIUS_API_KEY:
        raise HTTPException(status_code=503, detail="Helius API not available")

    from meridinate.helius_api import HeliusAPI

    try:
        # Get positions needing reconciliation for this token
        positions = db.get_positions_needing_reconciliation(token_id=token_id)

        if not positions:
            return ReconciliationResponse(
                positions_found=0,
                positions_reconciled=0,
                positions_no_tx_found=0,
                positions_error=0,
                credits_used=0,
                results=[],
            )

        log_info(
            f"[Reconcile] Found {len(positions)} positions needing reconciliation for token {token_id}"
        )

        helius = HeliusAPI(HELIUS_API_KEY)
        total_credits_used = 0
        reconciled = 0
        no_tx_found = 0
        errors = 0
        results = []

        for position in positions:
            wallet_address = position["wallet_address"]
            token_address = position["token_address"]
            token_symbol = position["token_symbol"]
            old_pnl_ratio = position["current_pnl_ratio"]
            entry_balance = position["entry_balance"] or position["total_bought_tokens"]

            try:
                # Fetch recent sell transaction for this wallet+token
                tx_result, credits = helius.get_recent_token_transaction(
                    wallet_address=wallet_address,
                    mint_address=token_address,
                    transaction_type="sell",
                    limit=max_signatures,
                )
                total_credits_used += credits

                if tx_result and tx_result.get("type") == "sell":
                    tokens_sold = tx_result.get("tokens", 0)
                    usd_received = tx_result.get("usd_amount", 0)

                    # If we found less tokens than entry balance, use entry balance
                    # (they likely sold everything but we might have missed some txs)
                    if tokens_sold < (entry_balance * 0.5) and entry_balance:
                        tokens_sold = entry_balance

                    # If USD wasn't captured from SOL transfer, estimate using current price
                    # This happens for pump.fun swaps where SOL routing is different
                    estimated_usd = False
                    if usd_received <= 0 and tokens_sold > 0:
                        try:
                            current_price = helius.get_token_price_from_dexscreener(token_address)
                            if current_price and current_price > 0:
                                usd_received = tokens_sold * current_price
                                estimated_usd = True
                                log_info(
                                    f"[Reconcile] {wallet_address[:8]}... {token_symbol}: "
                                    f"No USD in tx, estimated ${usd_received:.2f} from current price"
                                )
                        except Exception as price_err:
                            log_error(f"[Reconcile] Failed to get price for estimation: {price_err}")

                    # Skip if we still have no USD value
                    if usd_received <= 0:
                        no_tx_found += 1
                        results.append(ReconciliationResultItem(
                            wallet_address=wallet_address,
                            token_symbol=token_symbol,
                            status="no_tx_found",
                            old_pnl_ratio=old_pnl_ratio,
                            error_message="Found sell tx but couldn't determine USD value",
                        ))
                        continue

                    # Update the position with reconciled data
                    success = db.update_position_sell_reconciliation(
                        wallet_address=wallet_address,
                        token_id=token_id,
                        tokens_sold=tokens_sold,
                        usd_received=usd_received,
                    )

                    if success:
                        # Calculate what the new PnL ratio would be
                        avg_entry_price = position["avg_entry_price"]
                        new_pnl_ratio = None
                        if tokens_sold > 0 and avg_entry_price and avg_entry_price > 0:
                            exit_price = usd_received / tokens_sold
                            new_pnl_ratio = exit_price / avg_entry_price

                        reconciled += 1
                        old_pnl_str = f"{old_pnl_ratio:.2f}x" if old_pnl_ratio else "N/A"
                        new_pnl_str = f"{new_pnl_ratio:.2f}x" if new_pnl_ratio else "N/A"
                        log_info(
                            f"[Reconcile] {wallet_address[:8]}... {token_symbol}: "
                            f"PnL {old_pnl_str} -> {new_pnl_str} "
                            f"(sold {tokens_sold:.2f} for ${usd_received:.2f})"
                        )
                        results.append(ReconciliationResultItem(
                            wallet_address=wallet_address,
                            token_symbol=token_symbol,
                            status="success",
                            old_pnl_ratio=old_pnl_ratio,
                            new_pnl_ratio=new_pnl_ratio,
                            tokens_sold=tokens_sold,
                            usd_received=usd_received,
                        ))
                    else:
                        errors += 1
                        results.append(ReconciliationResultItem(
                            wallet_address=wallet_address,
                            token_symbol=token_symbol,
                            status="error",
                            old_pnl_ratio=old_pnl_ratio,
                            error_message="Database update failed",
                        ))
                else:
                    # No sell transaction found in recent history
                    no_tx_found += 1
                    log_info(
                        f"[Reconcile] {wallet_address[:8]}... {token_symbol}: "
                        f"No sell tx found in last {max_signatures} signatures"
                    )
                    results.append(ReconciliationResultItem(
                        wallet_address=wallet_address,
                        token_symbol=token_symbol,
                        status="no_tx_found",
                        old_pnl_ratio=old_pnl_ratio,
                        error_message=f"No sell tx found in last {max_signatures} signatures",
                    ))

            except Exception as e:
                errors += 1
                log_error(f"[Reconcile] Error processing {wallet_address[:8]}...: {e}")
                results.append(ReconciliationResultItem(
                    wallet_address=wallet_address,
                    token_symbol=token_symbol,
                    status="error",
                    old_pnl_ratio=old_pnl_ratio,
                    error_message=str(e),
                ))

        log_info(
            f"[Reconcile] Complete: {reconciled} reconciled, {no_tx_found} no tx found, "
            f"{errors} errors, {total_credits_used} credits used"
        )

        return ReconciliationResponse(
            positions_found=len(positions),
            positions_reconciled=reconciled,
            positions_no_tx_found=no_tx_found,
            positions_error=errors,
            credits_used=total_credits_used,
            results=results,
        )

    except Exception as e:
        log_error(f"Error during reconciliation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/reconcile-all",
    response_model=ReconciliationResponse,
    tags=["SWAB"],
)
async def reconcile_all_positions(
    max_signatures: int = Query(50, ge=10, le=200),
    max_positions: int = Query(50, ge=1, le=200),
):
    """
    Reconcile all sold positions across all tokens that need reconciliation.

    This is a batch operation that processes up to max_positions positions
    that have missing sell data.

    Query parameters:
    - max_signatures: Max signatures to check per wallet (default 50)
    - max_positions: Max positions to process in this batch (default 50)

    Returns:
    - positions_found: Number of positions needing reconciliation
    - positions_reconciled: Successfully updated
    - positions_no_tx_found: Sell transaction not found
    - credits_used: Helius API credits consumed
    """
    if not HELIUS_API_KEY:
        raise HTTPException(status_code=503, detail="Helius API not available")

    from meridinate.helius_api import HeliusAPI

    try:
        # Get ALL positions needing reconciliation
        all_positions = db.get_positions_needing_reconciliation()

        if not all_positions:
            return ReconciliationResponse(
                positions_found=0,
                positions_reconciled=0,
                positions_no_tx_found=0,
                positions_error=0,
                credits_used=0,
                results=[],
            )

        # Limit to max_positions
        positions = all_positions[:max_positions]

        log_info(
            f"[Reconcile] Found {len(all_positions)} total positions needing reconciliation, "
            f"processing {len(positions)}"
        )

        helius = HeliusAPI(HELIUS_API_KEY)
        total_credits_used = 0
        reconciled = 0
        no_tx_found = 0
        errors = 0
        results = []

        for position in positions:
            wallet_address = position["wallet_address"]
            token_id = position["token_id"]
            token_address = position["token_address"]
            token_symbol = position["token_symbol"]
            old_pnl_ratio = position["current_pnl_ratio"]
            entry_balance = position["entry_balance"] or position["total_bought_tokens"]

            try:
                # Fetch recent sell transaction
                tx_result, credits = helius.get_recent_token_transaction(
                    wallet_address=wallet_address,
                    mint_address=token_address,
                    transaction_type="sell",
                    limit=max_signatures,
                )
                total_credits_used += credits

                if tx_result and tx_result.get("type") == "sell":
                    tokens_sold = tx_result.get("tokens", 0)
                    usd_received = tx_result.get("usd_amount", 0)

                    if tokens_sold < (entry_balance * 0.5) and entry_balance:
                        tokens_sold = entry_balance

                    # If USD wasn't captured from SOL transfer, estimate using current price
                    if usd_received <= 0 and tokens_sold > 0:
                        try:
                            current_price = helius.get_token_price_from_dexscreener(token_address)
                            if current_price and current_price > 0:
                                usd_received = tokens_sold * current_price
                                log_info(
                                    f"[Reconcile] {wallet_address[:8]}... {token_symbol}: "
                                    f"No USD in tx, estimated ${usd_received:.2f} from current price"
                                )
                        except Exception as price_err:
                            log_error(f"[Reconcile] Failed to get price for estimation: {price_err}")

                    # Skip if we still have no USD value
                    if usd_received <= 0:
                        no_tx_found += 1
                        results.append(ReconciliationResultItem(
                            wallet_address=wallet_address,
                            token_symbol=token_symbol,
                            status="no_tx_found",
                            old_pnl_ratio=old_pnl_ratio,
                            error_message="Found sell tx but couldn't determine USD value",
                        ))
                        continue

                    success = db.update_position_sell_reconciliation(
                        wallet_address=wallet_address,
                        token_id=token_id,
                        tokens_sold=tokens_sold,
                        usd_received=usd_received,
                    )

                    if success:
                        avg_entry_price = position["avg_entry_price"]
                        new_pnl_ratio = None
                        if tokens_sold > 0 and avg_entry_price and avg_entry_price > 0:
                            exit_price = usd_received / tokens_sold
                            new_pnl_ratio = exit_price / avg_entry_price

                        reconciled += 1
                        old_pnl_str = f"{old_pnl_ratio:.2f}x" if old_pnl_ratio else "N/A"
                        new_pnl_str = f"{new_pnl_ratio:.2f}x" if new_pnl_ratio else "N/A"
                        log_info(
                            f"[Reconcile] {wallet_address[:8]}... {token_symbol}: "
                            f"PnL {old_pnl_str} -> {new_pnl_str}"
                        )
                        results.append(ReconciliationResultItem(
                            wallet_address=wallet_address,
                            token_symbol=token_symbol,
                            status="success",
                            old_pnl_ratio=old_pnl_ratio,
                            new_pnl_ratio=new_pnl_ratio,
                            tokens_sold=tokens_sold,
                            usd_received=usd_received,
                        ))
                    else:
                        errors += 1
                        results.append(ReconciliationResultItem(
                            wallet_address=wallet_address,
                            token_symbol=token_symbol,
                            status="error",
                            old_pnl_ratio=old_pnl_ratio,
                            error_message="Database update failed",
                        ))
                else:
                    no_tx_found += 1
                    results.append(ReconciliationResultItem(
                        wallet_address=wallet_address,
                        token_symbol=token_symbol,
                        status="no_tx_found",
                        old_pnl_ratio=old_pnl_ratio,
                        error_message=f"No sell tx found in last {max_signatures} signatures",
                    ))

            except Exception as e:
                errors += 1
                log_error(f"[Reconcile] Error: {e}")
                results.append(ReconciliationResultItem(
                    wallet_address=wallet_address,
                    token_symbol=token_symbol,
                    status="error",
                    old_pnl_ratio=old_pnl_ratio,
                    error_message=str(e),
                ))

        log_info(
            f"[Reconcile] Batch complete: {reconciled}/{len(positions)} reconciled, "
            f"{total_credits_used} credits"
        )

        return ReconciliationResponse(
            positions_found=len(all_positions),
            positions_reconciled=reconciled,
            positions_no_tx_found=no_tx_found,
            positions_error=errors,
            credits_used=total_credits_used,
            results=results,
        )

    except Exception as e:
        log_error(f"Error during batch reconciliation: {e}")
        raise HTTPException(status_code=500, detail=str(e))
