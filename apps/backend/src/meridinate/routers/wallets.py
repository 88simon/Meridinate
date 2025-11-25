"""
Wallets router - multi-token wallets and balance refresh endpoints

Provides REST endpoints for wallet operations
"""

import asyncio
from datetime import datetime, timezone

import aiosqlite
import requests
from fastapi import APIRouter, HTTPException, Request

from meridinate.middleware.rate_limit import READ_RATE_LIMIT, WALLET_BALANCE_RATE_LIMIT, conditional_rate_limit

from meridinate import settings
from meridinate.cache import ResponseCache
from meridinate.utils.models import MultiTokenWalletsResponse, RefreshBalancesRequest, RefreshBalancesResponse
import json

router = APIRouter()
cache = ResponseCache()


@router.get("/multi-token-wallets", response_model=MultiTokenWalletsResponse)
@conditional_rate_limit(READ_RATE_LIMIT)
async def get_multi_early_buyer_wallets(request: Request, min_tokens: int = 2):
    """Get wallets that appear in multiple tokens"""
    cache_key = f"multi_early_buyer_wallets_{min_tokens}"
    cached_data, _ = cache.get(cache_key)
    if cached_data:
        return cached_data

    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        conn.row_factory = aiosqlite.Row
        query = """
            WITH distinct_wallet_tokens AS (
                SELECT DISTINCT
                    tw.wallet_address,
                    tw.token_id,
                    t.id as token_table_id,
                    t.token_name,
                    t.token_address,
                    tw.wallet_balance_usd,
                    tw.wallet_balance_usd_previous,
                    tw.wallet_balance_updated_at
                FROM early_buyer_wallets tw
                JOIN analyzed_tokens t ON tw.token_id = t.id
                WHERE t.deleted_at IS NULL
            )
            SELECT
                dwt.wallet_address,
                COUNT(DISTINCT dwt.token_id) as token_count,
                GROUP_CONCAT(dwt.token_name ORDER BY dwt.token_table_id DESC) as token_names,
                GROUP_CONCAT(dwt.token_address ORDER BY dwt.token_table_id DESC) as token_addresses,
                GROUP_CONCAT(dwt.token_table_id ORDER BY dwt.token_table_id DESC) as token_ids,
                MAX(dwt.wallet_balance_usd) as wallet_balance_usd,
                MAX(dwt.wallet_balance_usd_previous) as wallet_balance_usd_previous,
                MAX(dwt.wallet_balance_updated_at) as wallet_balance_updated_at,
                COALESCE(mtw.marked_new, 0) as is_new,
                mtw.marked_at_analysis_id
            FROM distinct_wallet_tokens dwt
            LEFT JOIN multi_token_wallet_metadata mtw ON dwt.wallet_address = mtw.wallet_address
            GROUP BY dwt.wallet_address
            HAVING COUNT(DISTINCT dwt.token_id) >= ?
            ORDER BY token_count DESC, wallet_balance_usd DESC
        """
        cursor = await conn.execute(query, (min_tokens,))
        rows = await cursor.fetchall()

        # Fetch all token tags for tokens that appear in the results
        all_token_ids = set()
        for row in rows:
            wallet_dict = dict(row)
            token_ids_str = wallet_dict.get("token_ids", "")
            if token_ids_str:
                all_token_ids.update([int(id) for id in token_ids_str.split(",")])

        # Fetch tags for all tokens at once
        tags_by_token = {}
        if all_token_ids:
            tags_query = "SELECT token_id, tag FROM token_tags WHERE token_id IN ({})".format(
                ",".join(str(tid) for tid in all_token_ids)
            )
            tag_cursor = await conn.execute(tags_query)
            tag_rows = await tag_cursor.fetchall()
            for tag_row in tag_rows:
                token_id, tag = tag_row[0], tag_row[1]
                if token_id not in tags_by_token:
                    tags_by_token[token_id] = []
                tags_by_token[token_id].append(tag)

        wallets = []
        for row in rows:
            wallet_dict = dict(row)
            wallet_dict["token_names"] = wallet_dict["token_names"].split(",") if wallet_dict["token_names"] else []
            wallet_dict["token_addresses"] = (
                wallet_dict["token_addresses"].split(",") if wallet_dict["token_addresses"] else []
            )
            token_ids = [int(id) for id in wallet_dict["token_ids"].split(",") if wallet_dict["token_ids"]]
            wallet_dict["token_ids"] = token_ids

            # Build gem_statuses from token tags
            # For each token, check if it has 'gem' or 'dud' tag
            gem_statuses = []
            for token_id in token_ids:
                tags = tags_by_token.get(token_id, [])
                if "gem" in tags:
                    gem_statuses.append("gem")
                elif "dud" in tags:
                    gem_statuses.append("dud")
                else:
                    gem_statuses.append(None)
            wallet_dict["gem_statuses"] = gem_statuses

            # Convert is_new from integer (0/1) to boolean
            wallet_dict["is_new"] = bool(wallet_dict["is_new"])
            # SQLite returns timestamps as strings; pass through for client consumption
            wallets.append(wallet_dict)

        result = {"total": len(wallets), "wallets": wallets}
        cache.set(cache_key, result)
        return result


@router.post("/wallets/refresh-balances", response_model=RefreshBalancesResponse)
@conditional_rate_limit(WALLET_BALANCE_RATE_LIMIT)
async def refresh_wallet_balances(request: Request, data: RefreshBalancesRequest):
    """Refresh wallet balances for multiple wallets (ASYNC)"""
    wallet_addresses = data.wallet_addresses

    # Use HeliusAPI for consistent balance calculation with real-time SOL price
    from meridinate.helius_api import HeliusAPI

    helius = HeliusAPI(settings.HELIUS_API_KEY)

    # Capture existing balances for comparison
    existing_balances = {}
    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        placeholders = ",".join("?" for _ in wallet_addresses)
        if placeholders:
            cursor = await conn.execute(
                f"SELECT wallet_address, wallet_balance_usd FROM early_buyer_wallets WHERE wallet_address IN ({placeholders})",
                wallet_addresses,
            )
            for row in await cursor.fetchall():
                existing_balances[row[0]] = row[1]

    async def fetch_balance(wallet_address: str):
        try:
            loop = asyncio.get_event_loop()
            # Use the same get_wallet_balance method that properly converts lamports to USD
            # force_refresh=True bypasses cache since this is a manual user-triggered refresh
            balance_usd, credits = await loop.run_in_executor(
                None, lambda: helius.get_wallet_balance(wallet_address, force_refresh=True)
            )

            if balance_usd is not None:
                return {
                    "wallet_address": wallet_address,
                    "balance_usd": balance_usd,
                    "success": True,
                    "credits": credits,
                }
            else:
                return {"wallet_address": wallet_address, "balance_usd": None, "success": False, "credits": credits}
        except Exception:
            return {"wallet_address": wallet_address, "balance_usd": None, "success": False, "credits": 0}

    # Fetch all balances concurrently
    results = await asyncio.gather(*[fetch_balance(addr) for addr in wallet_addresses])

    # Update database with previous/current values and timestamp
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        for result in results:
            if result["success"] and result["balance_usd"] is not None:
                await conn.execute(
                    """
                    UPDATE early_buyer_wallets
                    SET wallet_balance_usd_previous = wallet_balance_usd,
                        wallet_balance_usd = ?,
                        wallet_balance_updated_at = ?
                    WHERE wallet_address = ?
                    """,
                    (result["balance_usd"], timestamp, result["wallet_address"]),
                )
                result["previous_balance_usd"] = existing_balances.get(result["wallet_address"])
                result["updated_at"] = timestamp
            else:
                result["previous_balance_usd"] = existing_balances.get(result["wallet_address"])
                result["updated_at"] = None
        await conn.commit()

    cache.invalidate("multi_early_buyer_wallets")

    successful = sum(1 for r in results if r["success"])
    total_credits = sum(r.get("credits", 0) for r in results)

    return {
        "message": f"Refreshed {successful} of {len(wallet_addresses)} wallets",
        "results": results,
        "total_wallets": len(wallet_addresses),
        "successful": successful,
        "api_credits_used": total_credits,
    }


@router.get("/wallets/{wallet_address}/top-holder-tokens")
@conditional_rate_limit(READ_RATE_LIMIT)
async def get_wallet_top_holder_tokens(request: Request, wallet_address: str):
    """
    Get all tokens where this wallet is a top holder.

    Returns a list of tokens with:
    - token_id
    - token_name
    - token_symbol
    - token_address
    - top_holders (full list from top_holders_json)
    - top_holders_limit (the limit used when analyzing)
    - wallet_rank (this wallet's position in the top holders list, 1-indexed)
    - last_updated (when top holders was last refreshed)
    """
    cache_key = f"wallet_top_holder_tokens_{wallet_address}"
    cached_data, _ = cache.get(cache_key)
    if cached_data:
        return cached_data

    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        conn.row_factory = aiosqlite.Row

        # Get all tokens where top_holders_json is not NULL and deleted_at is NULL
        query = """
            SELECT
                id,
                token_name,
                token_symbol,
                token_address,
                top_holders_json,
                top_holders_updated_at
            FROM analyzed_tokens
            WHERE top_holders_json IS NOT NULL
              AND deleted_at IS NULL
        """
        cursor = await conn.execute(query)
        rows = await cursor.fetchall()

        top_holder_tokens = []

        for row in rows:
            row_dict = dict(row)
            top_holders_json = row_dict.get("top_holders_json")

            if not top_holders_json:
                continue

            try:
                holders = json.loads(top_holders_json)

                # Check if wallet_address is in the top holders list
                wallet_rank = None
                for idx, holder in enumerate(holders):
                    if holder.get("address") == wallet_address:
                        wallet_rank = idx + 1  # 1-indexed
                        break

                if wallet_rank is not None:
                    # This wallet is a top holder of this token
                    top_holder_tokens.append({
                        "token_id": row_dict["id"],
                        "token_name": row_dict["token_name"],
                        "token_symbol": row_dict["token_symbol"],
                        "token_address": row_dict["token_address"],
                        "top_holders": holders,
                        "top_holders_limit": len(holders),  # The actual number of holders stored
                        "wallet_rank": wallet_rank,
                        "last_updated": row_dict["top_holders_updated_at"]
                    })
            except (json.JSONDecodeError, KeyError, TypeError):
                # Skip tokens with malformed data
                continue

        result = {
            "wallet_address": wallet_address,
            "total_tokens": len(top_holder_tokens),
            "tokens": top_holder_tokens
        }

        # Cache for 5 minutes
        cache.set(cache_key, result, ttl=300)
        return result


@router.post("/wallets/batch-top-holder-counts")
@conditional_rate_limit(READ_RATE_LIMIT)
async def get_batch_top_holder_counts(request: Request, wallet_addresses: list[str]):
    """
    Get count of tokens where each wallet is a top holder.
    Optimized batch endpoint that returns only counts, not full holder lists.

    This is much more efficient than calling /wallets/{address}/top-holder-tokens
    for each wallet when you only need the counts for badge display.

    Request body: {"wallet_addresses": ["addr1", "addr2", ...]}
    Returns: {"counts": {"addr1": 3, "addr2": 5, ...}}
    """
    cache_key = f"batch_top_holder_counts_{hash(tuple(sorted(wallet_addresses)))}"
    cached_data, _ = cache.get(cache_key)
    if cached_data:
        return cached_data

    counts = {}

    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        # Get all tokens where top_holders_json is not NULL
        query = """
            SELECT top_holders_json
            FROM analyzed_tokens
            WHERE top_holders_json IS NOT NULL
              AND deleted_at IS NULL
        """
        cursor = await conn.execute(query)
        rows = await cursor.fetchall()

        # Build a count map for each wallet address
        for wallet_address in wallet_addresses:
            count = 0
            for row in rows:
                top_holders_json = row[0]
                if not top_holders_json:
                    continue

                try:
                    holders = json.loads(top_holders_json)
                    # Check if wallet_address is in this token's holders
                    if any(holder.get("address") == wallet_address for holder in holders):
                        count += 1
                except (json.JSONDecodeError, KeyError, TypeError):
                    continue

            counts[wallet_address] = count

    result = {"counts": counts}

    # Cache for 5 minutes
    cache.set(cache_key, result, ttl=300)
    return result
