"""
Real PnL Calculator v2

Computes actual profit/loss per wallet per token using the correct approach:
1. getTokenAccountsByOwner → find the wallet's token account for a specific mint
2. getSignaturesForAddress on that token account → get ONLY transactions for this wallet+token pair
3. Parse each transaction for buy/sell amounts

This is cheap (~21 credits per wallet-token pair) and guaranteed to find the right data.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from meridinate.observability import log_error, log_info


def compute_wallet_token_pnl(
    wallet_address: str,
    token_address: str,
    api_key: str,
    max_signatures: int = 50,
) -> Dict[str, Any]:
    """
    Compute real PnL for a specific wallet on a specific token.

    Steps:
    1. Find the wallet's token account via getTokenAccountsByOwner
    2. Get all signatures for that token account
    3. Parse each transaction for buy/sell amounts

    Cost: ~10 + 1 + N credits (N = number of transactions, typically 1-20)

    Returns: {
        wallet_address, token_address,
        total_bought_sol, total_sold_sol, total_bought_tokens, total_sold_tokens,
        buy_count, sell_count, realized_pnl_sol,
        still_holding, current_balance,
        credits_used, transactions: [...]
    }
    """
    from meridinate.helius_api import HeliusAPI

    helius = HeliusAPI(api_key)
    credits_used = 0

    result = {
        "wallet_address": wallet_address,
        "token_address": token_address,
        "total_bought_sol": 0.0,
        "total_sold_sol": 0.0,
        "total_bought_tokens": 0.0,
        "total_sold_tokens": 0.0,
        "buy_count": 0,
        "sell_count": 0,
        "realized_pnl_sol": 0.0,
        "still_holding": False,
        "current_balance": 0.0,
        "credits_used": 0,
        "transactions": [],
        "tip_detected": None,  # "nozomi" or "jito" if tip infrastructure detected
    }

    # Step 1: Find the wallet's token account for this mint
    token_accounts, ta_credits = helius.get_token_accounts_by_owner(wallet_address, token_address)
    credits_used += ta_credits

    if not token_accounts:
        result["credits_used"] = credits_used
        return result

    # Get the token account pubkey and current balance
    token_account_pubkey = token_accounts[0].get("pubkey")
    current_balance = float(token_accounts[0].get("uiAmount", 0) or 0)
    result["current_balance"] = current_balance
    result["still_holding"] = current_balance > 0

    if not token_account_pubkey:
        result["credits_used"] = credits_used
        return result

    # Step 2: Get all signatures for this token account
    try:
        signatures = helius._rpc_call(
            "getSignaturesForAddress",
            [token_account_pubkey, {"limit": max_signatures}]
        )
        credits_used += 1
    except Exception as e:
        log_error(f"[PnLv2] Failed to get signatures for {token_account_pubkey[:12]}...: {e}")
        result["credits_used"] = credits_used
        return result

    if not signatures:
        result["credits_used"] = credits_used
        return result

    # Step 3: Parse each transaction
    for sig_obj in signatures:
        sig = sig_obj.get("signature")
        if not sig:
            continue

        try:
            tx_data = helius._rpc_call(
                "getTransaction",
                [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]
            )
            credits_used += 1

            if not tx_data:
                continue

            parsed = helius._parse_rpc_transaction(tx_data, sig)
            if not parsed:
                continue

            # Detect tip infrastructure usage (zero cost — uses existing parsed data)
            if not result["tip_detected"]:
                from meridinate.services.tip_detector import detect_tips_in_parsed_tx
                tip = detect_tips_in_parsed_tx(parsed)
                if tip:
                    result["tip_detected"] = tip

            # Look for token transfers matching our mint
            for tt in parsed.get("tokenTransfers", []):
                if tt.get("mint") != token_address:
                    continue

                token_amount = tt.get("tokenAmount", 0)
                if token_amount <= 0:
                    continue

                is_buy = tt.get("toUserAccount") == wallet_address
                is_sell = tt.get("fromUserAccount") == wallet_address

                if not is_buy and not is_sell:
                    continue

                # Find SOL amount from native transfers
                sol_amount = 0
                for nt in parsed.get("nativeTransfers", []):
                    amt = nt.get("amount", 0)
                    if amt <= 100000:  # Skip dust/fees
                        continue
                    if is_buy and nt.get("fromUserAccount") == wallet_address:
                        sol_amount = max(sol_amount, amt / 1e9)
                    elif is_sell and nt.get("toUserAccount") == wallet_address:
                        sol_amount = max(sol_amount, amt / 1e9)

                tx_record = {
                    "signature": sig,
                    "direction": "buy" if is_buy else "sell",
                    "token_amount": token_amount,
                    "sol_amount": sol_amount,
                    "timestamp": parsed.get("timestamp"),
                }
                result["transactions"].append(tx_record)

                if is_buy:
                    result["total_bought_sol"] += sol_amount
                    result["total_bought_tokens"] += token_amount
                    result["buy_count"] += 1
                else:
                    result["total_sold_sol"] += sol_amount
                    result["total_sold_tokens"] += token_amount
                    result["sell_count"] += 1

        except Exception as e:
            continue

    result["realized_pnl_sol"] = result["total_sold_sol"] - result["total_bought_sol"]
    result["credits_used"] = credits_used

    # Extract first buy and last sell timestamps from parsed transactions
    buy_timestamps = [t["timestamp"] for t in result["transactions"] if t["direction"] == "buy" and t.get("timestamp")]
    sell_timestamps = [t["timestamp"] for t in result["transactions"] if t["direction"] == "sell" and t.get("timestamp")]
    result["first_buy_timestamp"] = min(buy_timestamps) if buy_timestamps else None
    result["last_sell_timestamp"] = max(sell_timestamps) if sell_timestamps else None

    return result


def compute_and_store_wallet_pnl_v2(
    wallet_address: str,
    api_key: str,
    token_ids: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """
    Compute real PnL for a wallet across all their tokens in our database.
    Uses the per-token-account approach for accuracy.

    Args:
        wallet_address: Wallet to compute PnL for
        api_key: Helius API key
        token_ids: Specific token IDs to compute (None = all tokens this wallet bought early)

    Returns: summary with credits used and positions updated
    """
    from meridinate import analyzed_tokens_db as db

    summary = {
        "wallet_address": wallet_address,
        "tokens_processed": 0,
        "positions_updated": 0,
        "credits_used": 0,
        "total_realized_pnl_sol": 0.0,
    }

    # Get this wallet's tokens from early_buyer_wallets
    with db.get_db_connection() as conn:
        cursor = conn.cursor()
        if token_ids:
            placeholders = ",".join("?" for _ in token_ids)
            cursor.execute(f"""
                SELECT t.id, t.token_address, t.token_name
                FROM early_buyer_wallets ebw
                JOIN analyzed_tokens t ON t.id = ebw.token_id
                WHERE ebw.wallet_address = ? AND t.id IN ({placeholders})
                AND (t.deleted_at IS NULL OR t.deleted_at = '')
            """, [wallet_address] + token_ids)
        else:
            cursor.execute("""
                SELECT t.id, t.token_address, t.token_name
                FROM early_buyer_wallets ebw
                JOIN analyzed_tokens t ON t.id = ebw.token_id
                WHERE ebw.wallet_address = ? AND (t.deleted_at IS NULL OR t.deleted_at = '')
            """, (wallet_address,))
        tokens = cursor.fetchall()

    sol_price = _get_current_sol_price()

    for token_id, token_address, token_name in tokens:
        try:
            pnl = compute_wallet_token_pnl(wallet_address, token_address, api_key)
            summary["credits_used"] += pnl["credits_used"]
            summary["tokens_processed"] += 1

            # Skip if no meaningful trades found
            if pnl["total_bought_sol"] < 0.01 and pnl["total_sold_sol"] < 0.01:
                continue

            total_bought_usd = pnl["total_bought_sol"] * sol_price
            total_sold_usd = pnl["total_sold_sol"] * sol_price
            realized_pnl_usd = pnl["realized_pnl_sol"] * sol_price

            summary["total_realized_pnl_sol"] += pnl["realized_pnl_sol"]

            with db.get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id FROM mtew_token_positions WHERE wallet_address = ? AND token_id = ?",
                    (wallet_address, token_id)
                )
                existing = cursor.fetchone()

                # Convert unix timestamps to ISO strings
                first_buy_ts = None
                last_sell_ts = None
                if pnl.get("first_buy_timestamp"):
                    try:
                        first_buy_ts = datetime.utcfromtimestamp(pnl["first_buy_timestamp"]).isoformat()
                    except Exception:
                        pass
                if pnl.get("last_sell_timestamp"):
                    try:
                        last_sell_ts = datetime.utcfromtimestamp(pnl["last_sell_timestamp"]).isoformat()
                    except Exception:
                        pass

                if existing:
                    cursor.execute("""
                        UPDATE mtew_token_positions SET
                            total_bought_usd = ?, total_sold_usd = ?,
                            realized_pnl = ?, still_holding = ?,
                            position_checked_at = CURRENT_TIMESTAMP,
                            pnl_source = 'helius_enhanced',
                            entry_timestamp = COALESCE(?, entry_timestamp),
                            last_sell_timestamp = ?,
                            exit_detected_at = COALESCE(?, exit_detected_at)
                        WHERE wallet_address = ? AND token_id = ?
                    """, (total_bought_usd, total_sold_usd, realized_pnl_usd,
                          1 if pnl["still_holding"] else 0,
                          first_buy_ts, last_sell_ts, last_sell_ts,
                          wallet_address, token_id))
                else:
                    cursor.execute("""
                        INSERT INTO mtew_token_positions (
                            wallet_address, token_id, total_bought_usd, total_sold_usd,
                            realized_pnl, still_holding, position_checked_at, pnl_source,
                            entry_timestamp, last_sell_timestamp, exit_detected_at
                        ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, 'helius_enhanced', ?, ?, ?)
                    """, (wallet_address, token_id, total_bought_usd, total_sold_usd,
                          realized_pnl_usd, 1 if pnl["still_holding"] else 0,
                          first_buy_ts, last_sell_ts, last_sell_ts))

            summary["positions_updated"] += 1

            # Track tip detection across all tokens for this wallet
            if pnl.get("tip_detected") and not summary.get("tip_detected"):
                summary["tip_detected"] = pnl["tip_detected"]

        except Exception as e:
            log_error(f"[PnLv2] Failed for {wallet_address[:12]} on {token_name}: {e}")

    # Tag wallet if tip infrastructure was detected in any transaction
    tip = summary.get("tip_detected")
    if tip:
        tag = "Automated (Nozomi)" if tip == "nozomi" else "Bundled (Jito)"
        try:
            with db.get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT OR IGNORE INTO wallet_tags (wallet_address, tag, tier, source, updated_at) "
                    "VALUES (?, ?, 1, 'auto:tip-detection', CURRENT_TIMESTAMP)",
                    (wallet_address, tag)
                )
                if cursor.rowcount > 0:
                    log_info(f"[PnLv2] Tagged {wallet_address[:12]}... as '{tag}'")
        except Exception:
            pass

    log_info(
        f"[PnLv2] {wallet_address[:12]}...: {summary['tokens_processed']} tokens, "
        f"{summary['positions_updated']} updated, {summary['credits_used']} credits, "
        f"PnL={summary['total_realized_pnl_sol']:.4f} SOL"
    )
    return summary


def _get_current_sol_price() -> float:
    """Get current SOL price in USD from CoinGecko (free, reliable)."""
    try:
        import requests
        response = requests.get(
            "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd",
            timeout=10
        )
        if response.ok:
            data = response.json()
            price = data.get("solana", {}).get("usd", 0)
            if price > 0:
                return float(price)
    except Exception:
        pass
    # Fallback: try DexScreener SOL/USDC on Raydium
    try:
        import requests
        response = requests.get(
            "https://api.dexscreener.com/latest/dex/pairs/solana/58oQChx4yWmvKdwLLZg8QoRb88vFP51UNEEZuDA2pump",
            timeout=10
        )
        if response.ok:
            data = response.json()
            pair = data.get("pair") or (data.get("pairs", [None])[0])
            if pair:
                price = float(pair.get("priceNative", 0))
                if price > 1:  # Sanity check — SOL should be > $1
                    return price
    except Exception:
        pass
    return 140.0  # Last resort fallback


def backfill_leaderboard_pnl(max_wallets: int = 100) -> Dict[str, Any]:
    """
    Backfill real PnL for top recurring wallets using the v2 per-token-account approach.
    Prioritizes wallets with most tokens.
    """
    from meridinate import analyzed_tokens_db as db
    from meridinate.settings import HELIUS_API_KEY
    from meridinate.credit_tracker import get_credit_tracker

    result = {
        "wallets_processed": 0,
        "total_positions_updated": 0,
        "total_credits": 0,
    }

    # Get recurring wallets ordered by token count, excluding those already fully covered
    with db.get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT ebw.wallet_address, COUNT(DISTINCT ebw.token_id) as token_count,
                   COUNT(DISTINCT CASE WHEN mtp.pnl_source = 'helius_enhanced' THEN mtp.token_id END) as covered
            FROM early_buyer_wallets ebw
            JOIN analyzed_tokens t ON t.id = ebw.token_id AND (t.deleted_at IS NULL OR t.deleted_at = '')
            LEFT JOIN mtew_token_positions mtp ON mtp.wallet_address = ebw.wallet_address AND mtp.token_id = ebw.token_id
            GROUP BY ebw.wallet_address
            HAVING token_count >= 2 AND (covered IS NULL OR covered < token_count)
            ORDER BY token_count DESC
            LIMIT ?
        """, (max_wallets,))
        wallets = [(r[0], r[1], r[2] or 0) for r in cursor.fetchall()]

    log_info(f"[PnLv2 Backfill] {len(wallets)} wallets to process")

    for wallet_addr, token_count, covered in wallets:
        try:
            summary = compute_and_store_wallet_pnl_v2(wallet_addr, HELIUS_API_KEY)
            result["wallets_processed"] += 1
            result["total_positions_updated"] += summary["positions_updated"]
            result["total_credits"] += summary["credits_used"]

            if result["wallets_processed"] % 50 == 0:
                log_info(
                    f"[PnLv2 Backfill] Progress: {result['wallets_processed']}/{len(wallets)} wallets, "
                    f"{result['total_positions_updated']} positions, {result['total_credits']} credits"
                )
        except Exception as e:
            log_error(f"[PnLv2 Backfill] Failed for {wallet_addr[:12]}...: {e}")

    get_credit_tracker().record_operation(
        operation="pnl_v2_backfill", label="PnL v2 Backfill",
        credits=result["total_credits"], call_count=result["wallets_processed"],
        context={"positions": result["total_positions_updated"]},
    )

    log_info(
        f"[PnLv2 Backfill] Complete: {result['wallets_processed']} wallets, "
        f"{result['total_positions_updated']} positions, {result['total_credits']} credits"
    )
    return result
