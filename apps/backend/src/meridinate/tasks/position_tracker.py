"""
Position Tracker Task
=====================
Periodically checks if recurring wallets still hold their positions in analyzed tokens
and calculates PnL metrics for win rate tracking.

This task is designed to be run by APScheduler or manually triggered.
Cost: ~10 credits per position check (getTokenAccountsByOwner)
"""

import asyncio
import json
import statistics
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
    Check stale positions and update their holding status.

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
        log_info("No stale positions to check")
        return {
            "positions_checked": 0,
            "still_holding": 0,
            "sold": 0,
            "buys_detected": 0,
            "sells_detected": 0,
            "errors": 0,
            "credits_used": 0,
            "duration_ms": 0,
            "wallets_recalculated": 0,
        }

    log_info(f"Checking {len(positions)} stale positions")

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

    # Update Tier 2 computed tags for affected wallets
    for wallet_address in wallets_to_recalculate:
        try:
            db.compute_wallet_tier2_tags(wallet_address)
        except Exception as e:
            log_error(f"Error computing tags for {wallet_address[:8]}...: {e}")

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

    # Recompute real PnL (v2) for wallets that had balance changes
    v2_updated = 0
    if wallets_to_recalculate and total_credits + len(wallets_to_recalculate) * 25 <= max_credits:
        try:
            from meridinate.services.pnl_calculator_v2 import compute_and_store_wallet_pnl_v2
            for wallet_addr in wallets_to_recalculate:
                try:
                    pnl_result = await loop.run_in_executor(
                        None,
                        lambda addr=wallet_addr: compute_and_store_wallet_pnl_v2(addr, HELIUS_API_KEY)
                    )
                    total_credits += pnl_result.get("credits_used", 0)
                    v2_updated += pnl_result.get("positions_updated", 0)
                except Exception:
                    pass
        except Exception as e:
            log_error(f"PnL v2 recompute failed: {e}")

    duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)

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
        "v2_pnl_updated": v2_updated,
    }

    log_info(
        f"Position check complete: {still_holding_count} holding, {sold_count} sold, "
        f"{buys_detected} buys, {sells_detected} sells detected, "
        f"{v2_updated} v2 PnL updates, "
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
    Record positions for all recurring wallets in a specific token.

    Called after token analysis completes to track positions for
    wallets that are or just became recurring wallets.

    Args:
        token_id: Token ID from analyzed_tokens
        token_address: Token mint address
        entry_market_cap: Market cap at time of scan
        top_holders: List of top holder dicts from Helius (contains balance info)

    Returns:
        Dict with positions_tracked count
    """
    # Get all recurring wallets for this token (existing and newly qualifying)
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
            f"Recorded {positions_tracked} position(s) for token {token_id} "
            f"at entry MC ${entry_market_cap:,.2f}" if entry_market_cap else
            f"Recorded {positions_tracked} position(s) for token {token_id}"
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
    Get statistics about position tracking.

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


# ============================================================================
# Phase 3: Position-Derived Signals
# ============================================================================


def compute_smart_money_flow(token_id: int) -> Dict[str, Any]:
    """
    Compute smart money flow direction for a token.

    Cross-references positions with wallet tags to find "Consistent Winner"
    and "Sniper" tagged wallets, then classifies their activity.

    A wallet that recently exited (still_holding=0) = selling.
    A wallet still holding = holding.
    A wallet with a recent entry_timestamp (within last 24h) and still holding = buying.

    Stores the result as JSON in analyzed_tokens.smart_money_flow.

    Args:
        token_id: Token ID from analyzed_tokens

    Returns:
        {"smart_buying": N, "smart_selling": N, "smart_holding": N,
         "flow_direction": "bullish"|"bearish"|"neutral"}
    """
    with db.get_db_connection() as conn:
        cursor = conn.cursor()

        # Get all positions for this token that belong to smart wallets
        # Smart wallets = those tagged "Consistent Winner" or "Sniper"
        cursor.execute("""
            SELECT
                p.wallet_address,
                p.still_holding,
                p.entry_timestamp,
                p.exit_detected_at,
                p.position_checked_at
            FROM mtew_token_positions p
            INNER JOIN wallet_tags wt ON wt.wallet_address = p.wallet_address
            WHERE p.token_id = ?
            AND wt.tag IN ('Consistent Winner', 'Sniper')
        """, (token_id,))

        rows = cursor.fetchall()

        # Deduplicate by wallet_address (a wallet may have both tags)
        seen_wallets: Dict[str, Dict] = {}
        for row in rows:
            wallet = row[0]
            if wallet not in seen_wallets:
                seen_wallets[wallet] = {
                    "still_holding": row[1],
                    "entry_timestamp": row[2],
                    "exit_detected_at": row[3],
                    "position_checked_at": row[4],
                }

        smart_buying = 0
        smart_selling = 0
        smart_holding = 0

        for wallet, data in seen_wallets.items():
            if not data["still_holding"]:
                # Exited position = selling
                smart_selling += 1
            else:
                # Still holding - check if this is a recent entry (buying) vs long hold
                entry_ts = data["entry_timestamp"]
                is_recent_entry = False
                if entry_ts:
                    try:
                        # Parse entry timestamp and check if within last 24 hours
                        entry_dt = datetime.fromisoformat(str(entry_ts).replace("Z", "+00:00"))
                        delta = datetime.now(entry_dt.tzinfo) if entry_dt.tzinfo else datetime.now()
                        hours_since_entry = (delta - entry_dt).total_seconds() / 3600
                        is_recent_entry = hours_since_entry < 24
                    except (ValueError, TypeError):
                        pass

                if is_recent_entry:
                    smart_buying += 1
                else:
                    smart_holding += 1

        # Determine flow direction
        total_smart = smart_buying + smart_selling + smart_holding
        if total_smart == 0:
            flow_direction = "neutral"
        elif smart_buying > smart_selling:
            flow_direction = "bullish"
        elif smart_selling > smart_buying:
            flow_direction = "bearish"
        else:
            flow_direction = "neutral"

        result = {
            "smart_buying": smart_buying,
            "smart_selling": smart_selling,
            "smart_holding": smart_holding,
            "flow_direction": flow_direction,
        }

        # Store on analyzed_tokens
        cursor.execute(
            "UPDATE analyzed_tokens SET smart_money_flow = ? WHERE id = ?",
            (json.dumps(result), token_id),
        )

    log_info(
        f"Smart money flow for token {token_id}: "
        f"{smart_buying} buying, {smart_selling} selling, {smart_holding} holding "
        f"-> {flow_direction}"
    )

    return result


def compute_hold_duration_stats(token_id: int) -> Dict[str, Any]:
    """
    Compute hold duration distribution for a token.

    For each exited position, computes duration = exit_detected_at - entry_timestamp (in hours).
    This reveals whether a token has "quick flip" patterns vs "diamond hand" holders.

    Stores avg_hold_hours on analyzed_tokens.

    Args:
        token_id: Token ID from analyzed_tokens

    Returns:
        {"avg_hold_hours": float, "median_hold_hours": float,
         "pct_exited_under_2h": float, "pct_holding_over_24h": float}
    """
    with db.get_db_connection() as conn:
        cursor = conn.cursor()

        # Get all positions for this token with both entry and exit timestamps
        cursor.execute("""
            SELECT
                entry_timestamp,
                exit_detected_at,
                still_holding
            FROM mtew_token_positions
            WHERE token_id = ?
            AND entry_timestamp IS NOT NULL
        """, (token_id,))

        rows = cursor.fetchall()

        durations_hours: List[float] = []
        total_positions = 0
        holding_over_24h = 0

        for row in rows:
            entry_ts_str = row[0]
            exit_ts_str = row[1]
            still_holding = row[2]
            total_positions += 1

            if not still_holding and exit_ts_str:
                # Exited position - compute actual duration
                try:
                    entry_dt = datetime.fromisoformat(str(entry_ts_str).replace("Z", "+00:00"))
                    exit_dt = datetime.fromisoformat(str(exit_ts_str).replace("Z", "+00:00"))
                    # Ensure both are naive or both aware for subtraction
                    if entry_dt.tzinfo and not exit_dt.tzinfo:
                        entry_dt = entry_dt.replace(tzinfo=None)
                    elif exit_dt.tzinfo and not entry_dt.tzinfo:
                        exit_dt = exit_dt.replace(tzinfo=None)
                    duration_h = (exit_dt - entry_dt).total_seconds() / 3600
                    if duration_h >= 0:
                        durations_hours.append(duration_h)
                except (ValueError, TypeError):
                    pass
            elif still_holding and entry_ts_str:
                # Still holding - compute duration so far for the 24h+ metric
                try:
                    entry_dt = datetime.fromisoformat(str(entry_ts_str).replace("Z", "+00:00"))
                    now = datetime.now(entry_dt.tzinfo) if entry_dt.tzinfo else datetime.now()
                    hold_h = (now - entry_dt).total_seconds() / 3600
                    if hold_h > 24:
                        holding_over_24h += 1
                except (ValueError, TypeError):
                    pass

        # Compute stats from exited positions
        if durations_hours:
            avg_hold = statistics.mean(durations_hours)
            median_hold = statistics.median(durations_hours)
            exited_under_2h = sum(1 for d in durations_hours if d < 2)
            pct_exited_under_2h = exited_under_2h / len(durations_hours)
        else:
            avg_hold = 0.0
            median_hold = 0.0
            pct_exited_under_2h = 0.0

        # pct_holding_over_24h is across ALL positions (exited + holding)
        if total_positions > 0:
            # Count exited positions that lasted over 24h too
            exited_over_24h = sum(1 for d in durations_hours if d > 24)
            pct_holding_over_24h = (exited_over_24h + holding_over_24h) / total_positions
        else:
            pct_holding_over_24h = 0.0

        result = {
            "avg_hold_hours": round(avg_hold, 2),
            "median_hold_hours": round(median_hold, 2),
            "pct_exited_under_2h": round(pct_exited_under_2h, 4),
            "pct_holding_over_24h": round(pct_holding_over_24h, 4),
        }

        # Store avg_hold_hours on analyzed_tokens
        cursor.execute(
            "UPDATE analyzed_tokens SET avg_hold_hours = ? WHERE id = ?",
            (round(avg_hold, 2), token_id),
        )

    log_info(
        f"Hold duration stats for token {token_id}: "
        f"avg={avg_hold:.1f}h, median={median_hold:.1f}h, "
        f"{pct_exited_under_2h:.0%} exited <2h, {pct_holding_over_24h:.0%} holding >24h"
    )

    return result


def compute_entry_timing_scores() -> Dict[str, float]:
    """
    Compute entry timing scores for all wallets across ALL tokens.

    For each wallet, calculates how early they bought relative to the token's
    first transaction (analyzed_tokens.first_buy_timestamp).

    Uses early_buyer_wallets.first_buy_timestamp vs analyzed_tokens.first_buy_timestamp
    to compute delta in seconds. Averages across all tokens for each wallet.

    Wallets with avg_entry_seconds < 60 across 3+ tokens are potential
    "Lightning Buyer" bots or insiders.

    Stores avg_entry_seconds on early_buyer_wallets rows.

    Returns:
        Dict of {wallet_address: avg_entry_seconds}
    """
    with db.get_db_connection() as conn:
        cursor = conn.cursor()

        # Get all wallet/token pairs with both timestamps available
        cursor.execute("""
            SELECT
                ebw.wallet_address,
                ebw.first_buy_timestamp,
                t.first_buy_timestamp AS token_first_buy,
                ebw.token_id,
                ebw.id AS ebw_id
            FROM early_buyer_wallets ebw
            JOIN analyzed_tokens t ON t.id = ebw.token_id
            WHERE ebw.first_buy_timestamp IS NOT NULL
            AND t.first_buy_timestamp IS NOT NULL
            AND (t.deleted_at IS NULL OR t.deleted_at = '')
        """)

        rows = cursor.fetchall()

        # Accumulate deltas per wallet
        wallet_deltas: Dict[str, List[float]] = {}
        # Track individual row updates for per-row avg_entry_seconds
        row_deltas: Dict[int, float] = {}

        for row in rows:
            wallet = row[0]
            wallet_buy_ts = row[1]
            token_first_ts = row[2]
            ebw_id = row[4]

            try:
                wallet_dt = datetime.fromisoformat(str(wallet_buy_ts).replace("Z", "+00:00"))
                token_dt = datetime.fromisoformat(str(token_first_ts).replace("Z", "+00:00"))
                # Ensure both are naive or both aware for subtraction
                if wallet_dt.tzinfo and not token_dt.tzinfo:
                    wallet_dt = wallet_dt.replace(tzinfo=None)
                elif token_dt.tzinfo and not wallet_dt.tzinfo:
                    token_dt = token_dt.replace(tzinfo=None)
                delta_seconds = (wallet_dt - token_dt).total_seconds()
                if delta_seconds < 0:
                    delta_seconds = 0  # Bought before first recorded tx (edge case)

                if wallet not in wallet_deltas:
                    wallet_deltas[wallet] = []
                wallet_deltas[wallet].append(delta_seconds)
                row_deltas[ebw_id] = delta_seconds
            except (ValueError, TypeError):
                pass

        # Compute per-wallet averages
        wallet_avg: Dict[str, float] = {}
        for wallet, deltas in wallet_deltas.items():
            wallet_avg[wallet] = round(statistics.mean(deltas), 2)

        # Store per-row delta on early_buyer_wallets
        update_pairs = [(round(delta, 2), ebw_id) for ebw_id, delta in row_deltas.items()]
        if update_pairs:
            cursor.executemany(
                "UPDATE early_buyer_wallets SET avg_entry_seconds = ? WHERE id = ?",
                update_pairs,
            )

        # Tag lightning buyers (avg < 60s across 3+ tokens)
        lightning_count = 0
        for wallet, avg_seconds in wallet_avg.items():
            token_count = len(wallet_deltas[wallet])
            if avg_seconds < 60 and token_count >= 3:
                lightning_count += 1
                # Add Lightning Buyer tag if not already present
                try:
                    cursor.execute("""
                        INSERT OR IGNORE INTO wallet_tags (wallet_address, tag, tier, source, updated_at)
                        VALUES (?, 'Lightning Buyer', 2, 'computed:entry-timing', CURRENT_TIMESTAMP)
                    """, (wallet,))
                except Exception:
                    pass  # Tag may already exist

    log_info(
        f"Entry timing scores computed for {len(wallet_avg)} wallets across "
        f"{sum(len(d) for d in wallet_deltas.values())} positions. "
        f"{lightning_count} lightning buyers detected."
    )

    return wallet_avg
