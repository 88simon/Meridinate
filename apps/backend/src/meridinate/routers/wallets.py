"""
Wallets router - multi-token wallets and balance refresh endpoints

Provides REST endpoints for wallet operations
"""

import asyncio

import aiosqlite
import requests
from fastapi import APIRouter, HTTPException

from meridinate import settings
from meridinate.cache import ResponseCache
from meridinate.utils.models import MultiTokenWalletsResponse, RefreshBalancesRequest, RefreshBalancesResponse

router = APIRouter()
cache = ResponseCache()


@router.get("/multi-token-wallets", response_model=MultiTokenWalletsResponse)
async def get_multi_early_buyer_wallets(min_tokens: int = 2):
    """Get wallets that appear in multiple tokens"""
    cache_key = f"multi_early_buyer_wallets_{min_tokens}"
    cached_data, _ = cache.get(cache_key)
    if cached_data:
        return cached_data

    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        conn.row_factory = aiosqlite.Row
        query = """
            SELECT
                tw.wallet_address,
                COUNT(DISTINCT tw.token_id) as token_count,
                GROUP_CONCAT(DISTINCT t.token_name) as token_names,
                GROUP_CONCAT(DISTINCT t.token_address) as token_addresses,
                GROUP_CONCAT(DISTINCT t.id) as token_ids,
                MAX(tw.wallet_balance_usd) as wallet_balance_usd
            FROM early_buyer_wallets tw
            JOIN analyzed_tokens t ON tw.token_id = t.id
            WHERE t.deleted_at IS NULL
            GROUP BY tw.wallet_address
            HAVING COUNT(DISTINCT tw.token_id) >= ?
            ORDER BY token_count DESC, wallet_balance_usd DESC
        """
        cursor = await conn.execute(query, (min_tokens,))
        rows = await cursor.fetchall()

        wallets = []
        for row in rows:
            wallet_dict = dict(row)
            wallet_dict["token_names"] = wallet_dict["token_names"].split(",") if wallet_dict["token_names"] else []
            wallet_dict["token_addresses"] = (
                wallet_dict["token_addresses"].split(",") if wallet_dict["token_addresses"] else []
            )
            wallet_dict["token_ids"] = [
                int(id) for id in wallet_dict["token_ids"].split(",") if wallet_dict["token_ids"]
            ]
            wallets.append(wallet_dict)

        result = {"total": len(wallets), "wallets": wallets}
        cache.set(cache_key, result)
        return result


@router.post("/wallets/refresh-balances", response_model=RefreshBalancesResponse)
async def refresh_wallet_balances(request: RefreshBalancesRequest):
    """Refresh wallet balances for multiple wallets (ASYNC)"""
    wallet_addresses = request.wallet_addresses

    # Use HeliusAPI for consistent balance calculation with real-time SOL price
    from helius_api import HeliusAPI

    helius = HeliusAPI(settings.HELIUS_API_KEY)

    async def fetch_balance(wallet_address: str):
        try:
            loop = asyncio.get_event_loop()
            # Use the same get_wallet_balance method that properly converts lamports to USD
            balance_usd, credits = await loop.run_in_executor(None, lambda: helius.get_wallet_balance(wallet_address))

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

    # Update database
    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        for result in results:
            if result["success"] and result["balance_usd"] is not None:
                await conn.execute(
                    "UPDATE early_buyer_wallets SET wallet_balance_usd = ? WHERE wallet_address = ?",
                    (result["balance_usd"], result["wallet_address"]),
                )
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
