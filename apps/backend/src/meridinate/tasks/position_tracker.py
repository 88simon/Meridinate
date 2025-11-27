"""
MTEW Position Tracker Task
==========================
Periodically checks if MTEWs still hold their positions in analyzed tokens
and calculates PnL metrics for win rate tracking.

This task is designed to be run by APScheduler or manually triggered.
Cost: ~10 credits per position check (getTokenAccountsByOwner)
"""

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

from meridinate import analyzed_tokens_db as db
from meridinate import settings
from meridinate.credit_tracker import credit_tracker, CreditOperation
from meridinate.helius_api import HeliusAPI
from meridinate.observability import log_error, log_info


async def check_mtew_positions(
    older_than_minutes: int = 15,
    max_positions: int = 50,
    max_credits: int = 500,
) -> Dict[str, Any]:
    """
    Check stale MTEW positions and update their holding status.

    Detects balance changes and performs post-detection lookup to get
    transaction details for accurate multi-buy/sell tracking.

    Args:
        older_than_minutes: Only check positions not updated in this many minutes
        max_positions: Maximum positions to check in one run
        max_credits: Maximum credits to spend in one run

    Returns:
        Dict with statistics about the run
    """
    from meridinate.settings import HELIUS_API_KEY

    helius = HeliusAPI(HELIUS_API_KEY)
    start_time = datetime.now()

    # Get stale positions that need checking
    positions = db.get_stale_mtew_positions(
        older_than_minutes=older_than_minutes,
        limit=max_positions,
    )

    if not positions:
        log_info("No stale MTEW positions to check")
        return {
            "positions_checked": 0,
            "still_holding": 0,
            "sold": 0,
            "buys_detected": 0,
            "sells_detected": 0,
            "errors": 0,
            "credits_used": 0,
            "duration_ms": 0,
        }

    log_info(f"Checking {len(positions)} stale MTEW positions")

    # Track statistics
    still_holding_count = 0
    sold_count = 0
    buys_detected = 0
    sells_detected = 0
    error_count = 0
    total_credits = 0
    wallets_to_recalculate = set()

    # Process each position
    for position in positions:
        # Check credit budget (need room for balance check + potential tx lookup)
        if total_credits + 20 > max_credits:
            log_info(f"Credit limit reached ({total_credits}/{max_credits}), stopping early")
            break

        wallet_address = position["wallet_address"]
        token_id = position["token_id"]
        token_address = position["token_address"]
        entry_market_cap = position["entry_market_cap"]
        previous_balance = position.get("current_balance") or 0
        entry_balance = position.get("entry_balance")
        avg_entry_price = position.get("avg_entry_price")
        total_bought_usd = position.get("total_bought_usd")
        is_first_check = position.get("position_checked_at") is None

        try:
            # Run in executor since HeliusAPI is synchronous
            loop = asyncio.get_event_loop()
            accounts, credits = await loop.run_in_executor(
                None,
                lambda: helius.get_token_accounts_by_owner(wallet_address, token_address),
            )
            total_credits += credits

            if accounts is None:
                # API error
                error_count += 1
                continue

            # Get current balance
            current_balance = 0
            if accounts and len(accounts) > 0:
                account = accounts[0]
                current_balance = account.get("uiAmount", 0)

            # Get current token price for USD value
            token_price = helius.get_token_price_from_dexscreener(token_address)
            current_balance_usd = current_balance * token_price if token_price else None

            # Get current market cap for PnL calculation
            current_mc = helius.get_market_cap_from_dexscreener(token_address)

            # Calculate PnL ratio
            pnl_ratio = None
            if entry_market_cap and entry_market_cap > 0 and current_mc:
                pnl_ratio = current_mc / entry_market_cap

            # Detect balance changes and perform post-detection lookup
            balance_diff = current_balance - previous_balance
            balance_changed = abs(balance_diff) > 0.001  # Small threshold for float comparison

            if balance_changed and balance_diff > 0:
                # Balance INCREASED - a buy occurred
                log_info(f"Buy detected: {wallet_address[:8]}... +{balance_diff:,.2f} tokens")

                # Lookup the buy transaction for details
                tx_result, tx_credits = await loop.run_in_executor(
                    None,
                    lambda: helius.get_recent_token_transaction(
                        wallet_address, token_address, transaction_type="buy"
                    ),
                )
                total_credits += tx_credits

                if tx_result:
                    # Record the buy with actual transaction data
                    db.record_position_buy(
                        wallet_address=wallet_address,
                        token_id=token_id,
                        tokens_bought=tx_result.get("tokens", balance_diff),
                        usd_amount=tx_result.get("usd_amount", 0),
                        current_balance=current_balance,
                        current_balance_usd=current_balance_usd,
                    )
                    buys_detected += 1
                else:
                    # Fallback: just update the balance without tx details
                    db.update_mtew_position(
                        wallet_address=wallet_address,
                        token_id=token_id,
                        still_holding=True,
                        current_balance=current_balance,
                        current_balance_usd=current_balance_usd,
                        pnl_ratio=pnl_ratio,
                    )

                still_holding_count += 1

            elif balance_changed and balance_diff < 0:
                # Balance DECREASED - a sell occurred
                tokens_sold = abs(balance_diff)
                is_full_exit = current_balance < 0.001  # Essentially zero

                log_info(
                    f"Sell detected: {wallet_address[:8]}... -{tokens_sold:,.2f} tokens "
                    f"({'FULL EXIT' if is_full_exit else 'partial'})"
                )

                # Lookup the sell transaction for details
                tx_result, tx_credits = await loop.run_in_executor(
                    None,
                    lambda: helius.get_recent_token_transaction(
                        wallet_address, token_address, transaction_type="sell"
                    ),
                )
                total_credits += tx_credits

                if tx_result:
                    # Record the sell with actual transaction data
                    # Pass entry_market_cap and current_mc for FPnL calculation
                    db.record_position_sell(
                        wallet_address=wallet_address,
                        token_id=token_id,
                        tokens_sold=tx_result.get("tokens", tokens_sold),
                        usd_received=tx_result.get("usd_amount", 0),
                        current_balance=current_balance,
                        current_balance_usd=current_balance_usd,
                        is_full_exit=is_full_exit,
                        exit_market_cap=current_mc if is_full_exit else None,
                        entry_market_cap=entry_market_cap,
                        current_market_cap=current_mc,
                    )
                    sells_detected += 1
                else:
                    # Fallback: use price-based estimate since tx lookup failed
                    # fpnl_ratio is MC-based "what if held" metric
                    fpnl_ratio = None
                    if entry_market_cap and entry_market_cap > 0 and current_mc:
                        fpnl_ratio = current_mc / entry_market_cap

                    # Estimate PnL using current token price (frozen at detection time)
                    estimated_pnl_ratio = None
                    if token_price and total_bought_usd and total_bought_usd > 0:
                        estimated_exit_usd = tokens_sold * token_price
                        estimated_pnl_ratio = estimated_exit_usd / total_bought_usd
                        log_info(
                            f"Price-based PnL estimate: {tokens_sold:,.2f} tokens * "
                            f"${token_price:.6f} = ${estimated_exit_usd:.2f} / "
                            f"${total_bought_usd:.2f} = {estimated_pnl_ratio:.2f}x"
                        )

                    if is_full_exit:
                        db.update_mtew_position(
                            wallet_address=wallet_address,
                            token_id=token_id,
                            still_holding=False,
                            pnl_ratio=estimated_pnl_ratio,  # Price-based estimate
                            fpnl_ratio=fpnl_ratio,  # What they would have if held
                            exit_market_cap=current_mc,
                        )
                    else:
                        db.update_mtew_position(
                            wallet_address=wallet_address,
                            token_id=token_id,
                            still_holding=True,
                            current_balance=current_balance,
                            current_balance_usd=current_balance_usd,
                            pnl_ratio=pnl_ratio,  # OK for holding - based on current MC
                        )

                # Track counts and stop tracking for full exits
                if is_full_exit:
                    sold_count += 1
                    db.stop_tracking_position(position["id"], reason="sold")
                else:
                    still_holding_count += 1

            elif current_balance > 0:
                # No change - still holding, just update timestamp and PnL
                db.update_mtew_position(
                    wallet_address=wallet_address,
                    token_id=token_id,
                    still_holding=True,
                    current_balance=current_balance,
                    current_balance_usd=current_balance_usd,
                    pnl_ratio=pnl_ratio,
                )
                still_holding_count += 1

            else:
                # Balance is zero and was zero before (or first check found zero)
                # This could mean the wallet sold before our first check
                # Try to find the sell transaction for accurate PnL
                should_lookup_tx = (
                    is_first_check or  # First time checking this position
                    (entry_balance is not None and entry_balance > 0)  # Had tokens at entry
                )

                tx_result = None
                if should_lookup_tx:
                    log_info(
                        f"Sold before check detected: {wallet_address[:8]}... "
                        f"(entry_balance={entry_balance}, first_check={is_first_check})"
                    )
                    tx_result, tx_credits = await loop.run_in_executor(
                        None,
                        lambda: helius.get_recent_token_transaction(
                            wallet_address, token_address, transaction_type="sell"
                        ),
                    )
                    total_credits += tx_credits
                    if tx_result:
                        sells_detected += 1

                if tx_result:
                    # Found the sell transaction - record with actual data
                    db.record_position_sell(
                        wallet_address=wallet_address,
                        token_id=token_id,
                        tokens_sold=tx_result.get("tokens", entry_balance or 0),
                        usd_received=tx_result.get("usd_amount", 0),
                        current_balance=0,
                        current_balance_usd=0,
                        is_full_exit=True,
                        exit_market_cap=current_mc,
                        entry_market_cap=entry_market_cap,
                        current_market_cap=current_mc,
                    )
                else:
                    # Could not find transaction - use price-based estimate
                    fpnl_ratio = None
                    if entry_market_cap and entry_market_cap > 0 and current_mc:
                        fpnl_ratio = current_mc / entry_market_cap

                    # Estimate PnL using current token price (frozen at detection time)
                    estimated_pnl_ratio = None
                    tokens_sold_estimate = entry_balance or 0
                    if token_price and total_bought_usd and total_bought_usd > 0 and tokens_sold_estimate > 0:
                        estimated_exit_usd = tokens_sold_estimate * token_price
                        estimated_pnl_ratio = estimated_exit_usd / total_bought_usd
                        log_info(
                            f"Price-based PnL estimate (sold before check): "
                            f"{tokens_sold_estimate:,.2f} tokens * ${token_price:.6f} = "
                            f"${estimated_exit_usd:.2f} / ${total_bought_usd:.2f} = {estimated_pnl_ratio:.2f}x"
                        )

                    db.update_mtew_position(
                        wallet_address=wallet_address,
                        token_id=token_id,
                        still_holding=False,
                        pnl_ratio=estimated_pnl_ratio,  # Price-based estimate
                        fpnl_ratio=fpnl_ratio,  # What they would have if held
                        exit_market_cap=current_mc,
                    )

                db.stop_tracking_position(position["id"], reason="sold")
                sold_count += 1

            # Mark wallet for metrics recalculation
            wallets_to_recalculate.add(wallet_address)

        except Exception as e:
            log_error(f"Error checking position for {wallet_address[:8]}.../{token_address[:8]}...: {e}")
            error_count += 1

    # Recalculate wallet metrics and update Smart/Dumb labels for affected wallets
    for wallet_address in wallets_to_recalculate:
        try:
            db.calculate_wallet_metrics(wallet_address)
            # Update Smart/Dumb label based on new expectancy
            db.update_wallet_smart_dumb_label(wallet_address)
        except Exception as e:
            log_error(f"Error calculating metrics for {wallet_address[:8]}...: {e}")

    duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)

    # Record composite position check credits
    credit_tracker.record(
        CreditOperation.POSITION_CHECK,
        credits=0,  # Individual checks already recorded
        context={
            "positions_checked": len(positions),
            "still_holding": still_holding_count,
            "sold": sold_count,
            "buys_detected": buys_detected,
            "sells_detected": sells_detected,
            "errors": error_count,
            "total_credits": total_credits,
        },
    )

    result = {
        "positions_checked": len(positions),
        "still_holding": still_holding_count,
        "sold": sold_count,
        "buys_detected": buys_detected,
        "sells_detected": sells_detected,
        "errors": error_count,
        "credits_used": total_credits,
        "duration_ms": duration_ms,
        "wallets_recalculated": len(wallets_to_recalculate),
    }

    log_info(
        f"Position check complete: {still_holding_count} holding, {sold_count} sold, "
        f"{buys_detected} buys, {sells_detected} sells detected, "
        f"{error_count} errors, {total_credits} credits in {duration_ms}ms"
    )

    return result


def record_mtew_positions_for_token(
    token_id: int,
    token_address: str,
    entry_market_cap: Optional[float],
    top_holders: Optional[List[Dict]] = None,
) -> Dict[str, Any]:
    """
    Record positions for all MTEWs in a specific token.

    Called after token analysis completes to track positions for
    wallets that are or just became MTEWs.

    Args:
        token_id: Token ID from analyzed_tokens
        token_address: Token mint address
        entry_market_cap: Market cap at time of scan
        top_holders: List of top holder dicts from Helius (contains balance info)

    Returns:
        Dict with positions_tracked count
    """
    # Get all MTEWs for this token (existing and newly minted)
    mtew_wallets = db.get_multi_token_wallets_for_token(token_id)

    if not mtew_wallets:
        return {"positions_tracked": 0, "mtew_wallets": []}

    # Get first_buy_timestamp, entry_market_cap, and entry price for each wallet from early_buyer_wallets
    # This gives us the ACTUAL entry time, entry market cap, and entry price, not scan-time values
    wallet_entry_data: Dict[str, Dict] = {}
    with db.get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT wallet_address, first_buy_timestamp, entry_market_cap, first_buy_usd, first_buy_tokens
            FROM early_buyer_wallets
            WHERE token_id = ?
            """,
            (token_id,),
        )
        for row in cursor.fetchall():
            first_buy_usd = row[3]
            first_buy_tokens = row[4]
            # Calculate entry price per token if we have the data
            avg_entry_price = None
            if first_buy_usd and first_buy_tokens and first_buy_tokens > 0:
                avg_entry_price = first_buy_usd / first_buy_tokens

            wallet_entry_data[row[0]] = {
                "first_buy_timestamp": row[1],
                "entry_market_cap": row[2],
                "avg_entry_price": avg_entry_price,
                "total_bought_tokens": first_buy_tokens,
                "total_bought_usd": first_buy_usd,
            }

    # Build a lookup dict for holder balances
    holder_balances: Dict[str, Dict] = {}
    if top_holders:
        for holder in top_holders:
            wallet_addr = holder.get("address")
            if wallet_addr:
                holder_balances[wallet_addr] = {
                    "balance": holder.get("uiAmount"),
                    "balance_usd": holder.get("token_balance_usd"),
                }

    positions_tracked = 0
    for wallet_address in mtew_wallets:
        try:
            # Get entry balance data if available from current top holders
            holder_data = holder_balances.get(wallet_address, {})
            entry_balance = holder_data.get("balance")
            entry_balance_usd = holder_data.get("balance_usd")

            # Get actual entry data from early_buyer_wallets
            entry_data = wallet_entry_data.get(wallet_address, {})
            first_buy_ts = entry_data.get("first_buy_timestamp")
            # Use actual entry_market_cap from early_buyer_wallets if available, else fall back to scan-time MC
            actual_entry_mc = entry_data.get("entry_market_cap") or entry_market_cap
            # Get entry price data for accurate PnL calculation
            avg_entry_price = entry_data.get("avg_entry_price")
            total_bought_tokens = entry_data.get("total_bought_tokens")
            total_bought_usd = entry_data.get("total_bought_usd")

            # Fallback: if wallet isn't in top holders (sold before scan), use first_buy_tokens
            if entry_balance is None and total_bought_tokens:
                entry_balance = total_bought_tokens
            if entry_balance_usd is None and total_bought_usd:
                entry_balance_usd = total_bought_usd

            db.upsert_mtew_position(
                wallet_address=wallet_address,
                token_id=token_id,
                entry_market_cap=actual_entry_mc,
                still_holding=True,
                entry_balance=entry_balance,
                entry_balance_usd=entry_balance_usd,
                # Also set current balance to entry values initially
                current_balance=entry_balance,
                current_balance_usd=entry_balance_usd,
                # Use actual first buy timestamp for accurate hold time
                entry_timestamp=first_buy_ts,
                # Entry price data from early_buyer_wallets for accurate PnL
                avg_entry_price=avg_entry_price,
                total_bought_tokens=total_bought_tokens,
                total_bought_usd=total_bought_usd,
            )
            positions_tracked += 1
        except Exception as e:
            log_error(f"Error recording position for {wallet_address[:8]}...: {e}")

    if positions_tracked > 0:
        log_info(
            f"Recorded {positions_tracked} MTEW position(s) for token {token_id} "
            f"at entry MC ${entry_market_cap:,.2f}" if entry_market_cap else
            f"Recorded {positions_tracked} MTEW position(s) for token {token_id}"
        )

    return {
        "positions_tracked": positions_tracked,
        "mtew_wallets": mtew_wallets,
    }


async def update_all_pnl_ratios() -> Dict[str, Any]:
    """
    Update PnL ratios for all positions based on current market caps.

    This is a lightweight operation that only fetches market caps (free from DexScreener)
    without checking wallet holdings.

    Returns:
        Dict with update statistics
    """
    from meridinate.settings import HELIUS_API_KEY

    helius = HeliusAPI(HELIUS_API_KEY)
    start_time = datetime.now()

    # Get all tokens that have ANY positions (holding or sold)
    # This ensures FPnL stays updated for sold positions too
    with db.get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT DISTINCT token_id, t.token_address, p.entry_market_cap
            FROM mtew_token_positions p
            JOIN analyzed_tokens t ON p.token_id = t.id
        """)

        tokens = cursor.fetchall()

    if not tokens:
        return {"tokens_updated": 0, "positions_updated": 0, "duration_ms": 0}

    tokens_updated = 0
    positions_updated = 0

    for token_id, token_address, _ in tokens:
        # Get current market cap (free from DexScreener)
        current_mc = helius.get_market_cap_from_dexscreener(token_address)

        if not current_mc:
            continue

        # Update token's current market cap (needed for dynamic FPnL calculation)
        with db.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE analyzed_tokens
                SET market_cap_usd_current = ?
                WHERE id = ?
            """, (current_mc, token_id))
            conn.commit()

        # Update all HOLDING positions for this token
        with db.get_db_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                UPDATE mtew_token_positions
                SET pnl_ratio = ? / entry_market_cap
                WHERE token_id = ?
                AND still_holding = 1
                AND (tracking_enabled = 1 OR tracking_enabled IS NULL)
                AND entry_market_cap > 0
            """, (current_mc, token_id))

            positions_updated += cursor.rowcount

        tokens_updated += 1

    duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)

    log_info(f"Updated PnL ratios for {positions_updated} positions across {tokens_updated} tokens in {duration_ms}ms")

    return {
        "tokens_updated": tokens_updated,
        "positions_updated": positions_updated,
        "duration_ms": duration_ms,
    }


def get_position_tracking_stats() -> Dict[str, Any]:
    """
    Get statistics about MTEW position tracking.

    Returns:
        Dict with position counts, win rates, etc.
    """
    with db.get_db_connection() as conn:
        cursor = conn.cursor()

        # Total positions
        cursor.execute("SELECT COUNT(*) FROM mtew_token_positions")
        total_positions = cursor.fetchone()[0]

        # Still holding
        cursor.execute("SELECT COUNT(*) FROM mtew_token_positions WHERE still_holding = 1")
        still_holding = cursor.fetchone()[0]

        # Sold
        cursor.execute("SELECT COUNT(*) FROM mtew_token_positions WHERE still_holding = 0")
        sold = cursor.fetchone()[0]

        # Positions with PnL > 1 (winners)
        cursor.execute("SELECT COUNT(*) FROM mtew_token_positions WHERE pnl_ratio > 1.0")
        winners = cursor.fetchone()[0]

        # Positions with PnL <= 1 (losers)
        cursor.execute("SELECT COUNT(*) FROM mtew_token_positions WHERE pnl_ratio <= 1.0 AND pnl_ratio IS NOT NULL")
        losers = cursor.fetchone()[0]

        # Average PnL ratio
        cursor.execute("SELECT AVG(pnl_ratio) FROM mtew_token_positions WHERE pnl_ratio IS NOT NULL")
        avg_pnl = cursor.fetchone()[0]

        # Unique wallets tracked
        cursor.execute("SELECT COUNT(DISTINCT wallet_address) FROM mtew_token_positions")
        unique_wallets = cursor.fetchone()[0]

        # Unique tokens tracked
        cursor.execute("SELECT COUNT(DISTINCT token_id) FROM mtew_token_positions")
        unique_tokens = cursor.fetchone()[0]

        # Stale positions (not checked in 15+ minutes)
        cursor.execute("""
            SELECT COUNT(*) FROM mtew_token_positions
            WHERE still_holding = 1
            AND (position_checked_at IS NULL OR position_checked_at < datetime('now', '-15 minutes'))
        """)
        stale_positions = cursor.fetchone()[0]

    win_rate = winners / (winners + losers) if (winners + losers) > 0 else None

    return {
        "total_positions": total_positions,
        "still_holding": still_holding,
        "sold": sold,
        "winners": winners,
        "losers": losers,
        "win_rate": win_rate,
        "avg_pnl_ratio": avg_pnl,
        "unique_wallets": unique_wallets,
        "unique_tokens": unique_tokens,
        "stale_positions": stale_positions,
    }
