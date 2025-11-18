"""
Tokens router - token management endpoints

Provides REST endpoints for token history, details, trash management, and exports
"""

import json
from datetime import datetime
from typing import Any, Dict, List

import aiosqlite
from fastapi import APIRouter, HTTPException, Request, Response

import analyzed_tokens_db as db
from app import settings
from app.cache import ResponseCache
from app.utils.models import (
    AnalysisHistory,
    MessageResponse,
    RefreshMarketCapResult,
    RefreshMarketCapsRequest,
    RefreshMarketCapsResponse,
    TokenDetail,
    TokensResponse,
)
from helius_api import HeliusAPI

router = APIRouter()
cache = ResponseCache()


@router.get("/api/tokens/history", response_model=TokensResponse)
async def get_tokens_history(request: Request, response: Response):
    """Get all non-deleted tokens with wallet counts (with caching)"""
    cache_key = "tokens_history"

    # Check cache first
    cached_data, cached_etag = cache.get(cache_key)
    if cached_data:
        if_none_match = request.headers.get("if-none-match")
        if if_none_match and if_none_match == cached_etag:
            response.status_code = 304
            return Response(status_code=304)
        response.headers["ETag"] = cached_etag
        return cached_data

    # Fetch from database
    async def fetch_tokens():
        async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
            conn.row_factory = aiosqlite.Row
            query = """
                SELECT
                    t.id,
                    t.token_address,
                    t.token_name,
                    t.token_symbol,
                    t.acronym,
                    t.analysis_timestamp,
                    t.first_buy_timestamp,
                    t.market_cap_usd,
                    t.market_cap_usd_current,
                    t.market_cap_usd_previous,
                    t.market_cap_updated_at,
                    t.market_cap_ath,
                    t.market_cap_ath_timestamp,
                    COUNT(DISTINCT ebw.wallet_address) as wallets_found,
                    t.credits_used, t.last_analysis_credits
                FROM analyzed_tokens t
                LEFT JOIN early_buyer_wallets ebw ON ebw.token_id = t.id
                WHERE t.deleted_at IS NULL OR t.deleted_at = ''
                GROUP BY t.id
                ORDER BY t.analysis_timestamp DESC
            """
            cursor = await conn.execute(query)
            rows = await cursor.fetchall()

            tokens = []
            total_wallets = 0
            for row in rows:
                token_dict = dict(row)
                tokens.append(token_dict)
                total_wallets += token_dict.get("wallets_found", 0)

            return {"total": len(tokens), "total_wallets": total_wallets, "tokens": tokens}

    result = await cache.deduplicate_request(cache_key, fetch_tokens)
    etag = cache.set(cache_key, result)
    response.headers["ETag"] = etag
    return result


@router.get("/api/tokens/trash", response_model=TokensResponse)
async def get_deleted_tokens():
    """Get all soft-deleted tokens"""
    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        conn.row_factory = aiosqlite.Row
        query = """
            SELECT
                t.*, COUNT(DISTINCT ebw.wallet_address) as wallets_found
            FROM analyzed_tokens t
            LEFT JOIN early_buyer_wallets ebw ON ebw.token_id = t.id
            WHERE t.deleted_at IS NOT NULL
            GROUP BY t.id
            ORDER BY t.deleted_at DESC
        """
        cursor = await conn.execute(query)
        rows = await cursor.fetchall()

        tokens = [dict(row) for row in rows]
        return {"total": len(tokens), "total_wallets": sum(t.get("wallets_found", 0) for t in tokens), "tokens": tokens}


@router.get("/api/tokens/{token_id}", response_model=TokenDetail)
async def get_token_by_id(token_id: int):
    """Get token details with wallets and axiom export"""
    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        conn.row_factory = aiosqlite.Row

        # Get token info
        token_query = "SELECT * FROM analyzed_tokens WHERE id = ? AND deleted_at IS NULL"
        cursor = await conn.execute(token_query, (token_id,))
        token_row = await cursor.fetchone()

        if not token_row:
            raise HTTPException(status_code=404, detail="Token not found")

        token = dict(token_row)

        # Get wallets for this token
        wallets_query = """
            SELECT * FROM early_buyer_wallets
            WHERE token_id = ?
            ORDER BY first_buy_timestamp ASC
        """
        cursor = await conn.execute(wallets_query, (token_id,))
        wallet_rows = await cursor.fetchall()
        token["wallets"] = [dict(row) for row in wallet_rows]

        # Get axiom export
        axiom_query = "SELECT axiom_json FROM analyzed_tokens WHERE id = ?"
        cursor = await conn.execute(axiom_query, (token_id,))
        axiom_row = await cursor.fetchone()
        token["axiom_json"] = json.loads(axiom_row[0]) if axiom_row and axiom_row[0] else []

        return token


@router.get("/api/tokens/{token_id}/history", response_model=AnalysisHistory)
async def get_token_analysis_history(token_id: int):
    """Get analysis history for a specific token"""
    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        conn.row_factory = aiosqlite.Row

        # Verify token exists
        token_query = "SELECT id FROM analyzed_tokens WHERE id = ?"
        cursor = await conn.execute(token_query, (token_id,))
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Token not found")

        # Fetch analysis runs
        runs_query = """
            SELECT id, analysis_timestamp, wallets_found, credits_used
            FROM analysis_runs
            WHERE token_id = ?
            ORDER BY analysis_timestamp DESC
        """
        cursor = await conn.execute(runs_query, (token_id,))
        run_rows = await cursor.fetchall()

        runs = []
        for run_row in run_rows:
            run = dict(run_row)
            wallets_query = """
                SELECT *
                FROM early_buyer_wallets
                WHERE analysis_run_id = ?
                ORDER BY position ASC
            """
            wallet_cursor = await conn.execute(wallets_query, (run["id"],))
            wallet_rows = await wallet_cursor.fetchall()
            run["wallets"] = [dict(w) for w in wallet_rows]
            runs.append(run)

        return {"token_id": token_id, "total_runs": len(runs), "runs": runs}


@router.delete("/api/tokens/{token_id}", response_model=MessageResponse)
async def soft_delete_token(token_id: int):
    """Soft delete a token (move to trash)"""
    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        query = "UPDATE analyzed_tokens SET deleted_at = ? WHERE id = ?"
        await conn.execute(query, (datetime.utcnow().isoformat(), token_id))
        await conn.commit()

    cache.invalidate("tokens")
    return {"message": "Token moved to trash"}


@router.post("/api/tokens/{token_id}/restore", response_model=MessageResponse)
async def restore_token(token_id: int):
    """Restore a soft-deleted token"""
    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        query = "UPDATE analyzed_tokens SET deleted_at = NULL WHERE id = ?"
        await conn.execute(query, (token_id,))
        await conn.commit()

    cache.invalidate("tokens")
    return {"message": "Token restored"}


@router.delete("/api/tokens/{token_id}/permanent", response_model=MessageResponse)
async def permanent_delete_token(token_id: int):
    """Permanently delete a token and all associated data"""
    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        # Delete in order: wallets, analysis runs, token
        await conn.execute("DELETE FROM early_buyer_wallets WHERE token_id = ?", (token_id,))
        await conn.execute("DELETE FROM analysis_runs WHERE token_id = ?", (token_id,))
        await conn.execute("DELETE FROM analyzed_tokens WHERE id = ?", (token_id,))
        await conn.commit()

    cache.invalidate("tokens")
    return {"message": "Token permanently deleted"}


@router.post("/api/tokens/refresh-market-caps", response_model=RefreshMarketCapsResponse)
async def refresh_market_caps(request: RefreshMarketCapsRequest):
    """Refresh current market cap for multiple tokens"""
    from app.settings import HELIUS_API_KEY

    helius = HeliusAPI(HELIUS_API_KEY)
    results = []
    total_credits = 0

    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        conn.row_factory = aiosqlite.Row

        for token_id in request.token_ids:
            try:
                # Get token address
                cursor = await conn.execute("SELECT token_address FROM analyzed_tokens WHERE id = ?", (token_id,))
                row = await cursor.fetchone()

                if not row:
                    results.append(
                        {
                            "token_id": token_id,
                            "market_cap_usd_current": None,
                            "market_cap_usd_previous": None,
                            "market_cap_updated_at": None,
                            "market_cap_ath": None,
                            "market_cap_ath_timestamp": None,
                            "success": False,
                        }
                    )
                    continue

                token_address = row["token_address"]

                # Get current highest observed market cap and original analysis market cap from database
                cursor = await conn.execute(
                    "SELECT market_cap_ath, market_cap_usd FROM analyzed_tokens WHERE id = ?",
                    (token_id,),
                )
                ath_row = await cursor.fetchone()
                current_ath = ath_row["market_cap_ath"] if ath_row else None
                original_market_cap = ath_row["market_cap_usd"] if ath_row else None

                # Fetch current market cap (DexScreener primary, Helius fallback)
                market_cap_usd, credits = helius.get_market_cap_with_fallback(token_address)
                total_credits += credits

                # Track highest observed: compare current, stored ATH, and original analysis market cap
                # The highest should be the maximum of all three values
                market_cap_ath = current_ath
                ath_timestamp = None

                # Determine the true highest value considering all sources
                candidates = [v for v in [current_ath, original_market_cap, market_cap_usd] if v is not None and v > 0]
                if candidates:
                    true_highest = max(candidates)

                    # Update if the true highest is different from current stored ATH
                    if current_ath is None or true_highest > current_ath:
                        from datetime import datetime, timezone

                        # Determine which value is the new peak
                        if market_cap_usd is not None and market_cap_usd == true_highest:
                            # Current market cap is the new peak
                            market_cap_ath = market_cap_usd
                            ath_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                            previous_value = current_ath if current_ath is not None else 0
                            print(
                                f"[Peak MC] New peak for token {token_id}: ${market_cap_ath:,.2f} (previous: ${previous_value:,.2f})"
                            )
                        elif original_market_cap is not None and original_market_cap == true_highest:
                            # Original analysis market cap is the highest
                            market_cap_ath = original_market_cap
                            # Use analysis timestamp
                            cursor = await conn.execute(
                                "SELECT analysis_timestamp FROM analyzed_tokens WHERE id = ?",
                                (token_id,),
                            )
                            analysis_row = await cursor.fetchone()
                            if analysis_row:
                                ath_timestamp = analysis_row["analysis_timestamp"]
                                previous_value = current_ath if current_ath is not None else 0
                                print(
                                    f"[Peak MC] Updating peak from analysis for token {token_id}: ${market_cap_ath:,.2f} (previous: ${previous_value:,.2f})"
                                )

                # Update database with current market cap and highest observed
                db.update_token_market_cap_with_ath(token_id, market_cap_usd, market_cap_ath, ath_timestamp)

                # Get the updated timestamp, peak data, and previous value
                cursor = await conn.execute(
                    "SELECT market_cap_updated_at, market_cap_ath, market_cap_ath_timestamp, market_cap_usd_previous FROM analyzed_tokens WHERE id = ?",
                    (token_id,),
                )
                updated_row = await cursor.fetchone()
                market_cap_updated_at = updated_row["market_cap_updated_at"] if updated_row else None
                market_cap_ath_db = updated_row["market_cap_ath"] if updated_row else None
                ath_timestamp_db = updated_row["market_cap_ath_timestamp"] if updated_row else None
                market_cap_usd_previous = updated_row["market_cap_usd_previous"] if updated_row else None

                results.append(
                    {
                        "token_id": token_id,
                        "market_cap_usd_current": market_cap_usd,
                        "market_cap_usd_previous": market_cap_usd_previous,
                        "market_cap_updated_at": market_cap_updated_at,
                        "market_cap_ath": market_cap_ath_db,
                        "market_cap_ath_timestamp": ath_timestamp_db,
                        "success": True,
                    }
                )

            except Exception as e:
                print(f"[ERROR] Failed to refresh market cap for token {token_id}: {str(e)}")
                import traceback

                traceback.print_exc()
                results.append(
                    {
                        "token_id": token_id,
                        "market_cap_usd_current": None,
                        "market_cap_usd_previous": None,
                        "market_cap_updated_at": None,
                        "market_cap_ath": None,
                        "market_cap_ath_timestamp": None,
                        "success": False,
                    }
                )

    successful = sum(1 for r in results if r["success"])
    cache.invalidate("tokens")

    return {
        "message": f"Refreshed {successful}/{len(request.token_ids)} token market caps",
        "results": results,
        "total_tokens": len(request.token_ids),
        "successful": successful,
        "api_credits_used": total_credits,
    }
