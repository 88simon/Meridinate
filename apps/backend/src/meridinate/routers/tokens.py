"""
Tokens router - token management endpoints

Provides REST endpoints for token history, details, trash management, and exports
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiosqlite
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from meridinate.middleware.rate_limit import MARKET_CAP_RATE_LIMIT, READ_RATE_LIMIT, conditional_rate_limit
from meridinate.observability import log_error, log_info

from meridinate import analyzed_tokens_db as db
from meridinate import settings
from meridinate.cache import ResponseCache
from meridinate.utils.models import (
    AnalysisHistory,
    MessageResponse,
    RefreshMarketCapResult,
    RefreshMarketCapsRequest,
    RefreshMarketCapsResponse,
    TokenDetail,
    TokensResponse,
    TokenTagRequest,
    TokenTagsResponse,
    TopHoldersResponse,
    UpdateGemStatusRequest,
)
from meridinate.helius_api import HeliusAPI
from meridinate.credit_tracker import credit_tracker, CreditOperation

router = APIRouter()
cache = ResponseCache(name="tokens_history")


class LatestTokenResponse(BaseModel):
    """Response model for the latest analyzed token."""

    token_id: Optional[int] = None
    token_name: Optional[str] = None
    token_symbol: Optional[str] = None
    analysis_timestamp: Optional[str] = None
    wallets_found: Optional[int] = None
    credits_used: Optional[int] = None


@router.get("/api/tokens/latest", response_model=LatestTokenResponse)
@conditional_rate_limit(READ_RATE_LIMIT)
async def get_latest_token(request: Request):
    """
    Get the most recently analyzed token.

    Returns lightweight data for status bar display:
    - token_id, token_name, token_symbol
    - analysis_timestamp
    - wallets_found, credits_used
    """
    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        conn.row_factory = aiosqlite.Row
        query = """
            SELECT
                t.id as token_id,
                t.token_name,
                t.token_symbol,
                t.analysis_timestamp,
                COUNT(DISTINCT ebw.wallet_address) as wallets_found,
                COALESCE(t.last_analysis_credits, t.credits_used) as credits_used
            FROM analyzed_tokens t
            LEFT JOIN early_buyer_wallets ebw ON ebw.token_id = t.id
            WHERE t.deleted_at IS NULL OR t.deleted_at = ''
            GROUP BY t.id
            ORDER BY t.analysis_timestamp DESC
            LIMIT 1
        """
        cursor = await conn.execute(query)
        row = await cursor.fetchone()

        if not row:
            return LatestTokenResponse()

        return LatestTokenResponse(
            token_id=row["token_id"],
            token_name=row["token_name"],
            token_symbol=row["token_symbol"],
            analysis_timestamp=row["analysis_timestamp"],
            wallets_found=row["wallets_found"],
            credits_used=row["credits_used"],
        )


@router.get("/api/tokens/history", response_model=TokensResponse)
@conditional_rate_limit(READ_RATE_LIMIT)
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
                    t.credits_used, t.last_analysis_credits,
                    t.gem_status,
                    COALESCE(t.state_version, 0) as state_version,
                    t.top_holders_json,
                    t.top_holders_updated_at
                FROM analyzed_tokens t
                LEFT JOIN early_buyer_wallets ebw ON ebw.token_id = t.id
                WHERE t.deleted_at IS NULL OR t.deleted_at = ''
                GROUP BY t.id
                ORDER BY t.analysis_timestamp DESC
            """
            cursor = await conn.execute(query)
            rows = await cursor.fetchall()

            # Fetch all token tags in one query
            tag_cursor = await conn.execute(
                "SELECT token_id, tag FROM token_tags WHERE token_id IN ({})".format(
                    ",".join(str(dict(row)["id"]) for row in rows)
                )
                if rows
                else "SELECT token_id, tag FROM token_tags WHERE 0=1"
            )
            tag_rows = await tag_cursor.fetchall()

            # Group tags by token_id
            tags_by_token = {}
            for tag_row in tag_rows:
                token_id = tag_row[0]
                tag = tag_row[1]
                if token_id not in tags_by_token:
                    tags_by_token[token_id] = []
                tags_by_token[token_id].append(tag)

            tokens = []
            total_wallets = 0
            for row in rows:
                token_dict = dict(row)
                token_dict["tags"] = tags_by_token.get(token_dict["id"], [])

                # Parse top holders JSON
                top_holders_json = token_dict.get("top_holders_json")
                token_dict["top_holders"] = json.loads(top_holders_json) if top_holders_json else None

                tokens.append(token_dict)
                total_wallets += token_dict.get("wallets_found", 0)

            return {"total": len(tokens), "total_wallets": total_wallets, "tokens": tokens}

    result = await cache.deduplicate_request(cache_key, fetch_tokens)
    etag = cache.set(cache_key, result)
    response.headers["ETag"] = etag
    return result


@router.get("/api/tokens/trash", response_model=TokensResponse)
@conditional_rate_limit(READ_RATE_LIMIT)
async def get_deleted_tokens(request: Request):
    """Get all soft-deleted tokens"""
    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        conn.row_factory = aiosqlite.Row
        query = """
            SELECT
                t.*,
                COUNT(DISTINCT ebw.wallet_address) as wallets_found
            FROM analyzed_tokens t
            LEFT JOIN early_buyer_wallets ebw ON ebw.token_id = t.id
            WHERE t.deleted_at IS NOT NULL
            GROUP BY t.id
            ORDER BY t.deleted_at DESC
        """
        cursor = await conn.execute(query)
        rows = await cursor.fetchall()

        # Fetch all token tags
        if rows:
            tag_cursor = await conn.execute(
                "SELECT token_id, tag FROM token_tags WHERE token_id IN ({})".format(
                    ",".join(str(dict(row)["id"]) for row in rows)
                )
            )
            tag_rows = await tag_cursor.fetchall()
            tags_by_token = {}
            for tag_row in tag_rows:
                token_id, tag = tag_row[0], tag_row[1]
                if token_id not in tags_by_token:
                    tags_by_token[token_id] = []
                tags_by_token[token_id].append(tag)
        else:
            tags_by_token = {}

        tokens = []
        for row in rows:
            token_dict = dict(row)
            token_dict["tags"] = tags_by_token.get(token_dict["id"], [])

            # Parse top holders JSON
            top_holders_json = token_dict.get("top_holders_json")
            token_dict["top_holders"] = json.loads(top_holders_json) if top_holders_json else None

            tokens.append(token_dict)

        return {"total": len(tokens), "total_wallets": sum(t.get("wallets_found", 0) for t in tokens), "tokens": tokens}


@router.post("/api/tokens/refresh-market-caps", response_model=RefreshMarketCapsResponse)
@conditional_rate_limit(MARKET_CAP_RATE_LIMIT)
async def refresh_market_caps(request: Request, data: RefreshMarketCapsRequest):
    """Refresh current market cap for multiple tokens"""
    from meridinate.settings import HELIUS_API_KEY

    helius = HeliusAPI(HELIUS_API_KEY)
    results = []
    total_credits = 0

    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        conn.row_factory = aiosqlite.Row

        for token_id in data.token_ids:
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
                if ath_timestamp is not None:
                    # New peak reached - update both current and highest
                    await conn.execute(
                        """
                        UPDATE analyzed_tokens
                        SET market_cap_usd_previous = market_cap_usd_current,
                            market_cap_usd_current = ?,
                            market_cap_ath = ?,
                            market_cap_ath_timestamp = ?,
                            market_cap_updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                        """,
                        (market_cap_usd, market_cap_ath, ath_timestamp, token_id),
                    )
                    print(f"[Database] New peak market cap for token {token_id}: ${market_cap_ath:,.2f}")
                else:
                    # No new peak - only update current market cap
                    await conn.execute(
                        """
                        UPDATE analyzed_tokens
                        SET market_cap_usd_previous = market_cap_usd_current,
                            market_cap_usd_current = ?,
                            market_cap_updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                        """,
                        (market_cap_usd, token_id),
                    )

                await conn.commit()
                print(
                    f"[Database] Updated market cap for token {token_id}: ${market_cap_usd:,.2f}"
                    if market_cap_usd
                    else f"[Database] Updated market cap for token {token_id}: N/A"
                )

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
    # Invalidate the cached tokens history so the frontend sees fresh market caps
    cache.invalidate("tokens_history")

    # Record batch market cap refresh credits
    if total_credits > 0:
        credit_tracker.record_batch(
            CreditOperation.MARKET_CAP_REFRESH,
            credits=total_credits,
            count=len(data.token_ids),
            context={"successful": successful, "token_ids": data.token_ids},
        )

    return {
        "message": f"Refreshed {successful}/{len(data.token_ids)} token market caps",
        "results": results,
        "total_tokens": len(data.token_ids),
        "successful": successful,
        "api_credits_used": total_credits,
    }


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

        # Get token tags
        tags_query = "SELECT tag FROM token_tags WHERE token_id = ?"
        cursor = await conn.execute(tags_query, (token_id,))
        tag_rows = await cursor.fetchall()
        token["tags"] = [row[0] for row in tag_rows]

        # Parse top holders JSON
        top_holders_json = token.get("top_holders_json")
        token["top_holders"] = json.loads(top_holders_json) if top_holders_json else None

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

    cache.invalidate("tokens_history")
    return {"message": "Token moved to trash"}


@router.post("/api/tokens/{token_id}/restore", response_model=MessageResponse)
async def restore_token(token_id: int):
    """Restore a soft-deleted token"""
    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        query = "UPDATE analyzed_tokens SET deleted_at = NULL WHERE id = ?"
        await conn.execute(query, (token_id,))
        await conn.commit()

    cache.invalidate("tokens_history")
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

    cache.invalidate("tokens_history")
    return {"message": "Token permanently deleted"}


@router.post("/api/tokens/{token_id}/gem-status", response_model=MessageResponse)
@conditional_rate_limit(READ_RATE_LIMIT)
async def update_gem_status(token_id: int, request: Request, data: UpdateGemStatusRequest):
    """Update the gem status of a token (gem, dud, or null to clear)"""
    gem_status = data.gem_status

    # Validate gem_status value
    if gem_status is not None and gem_status not in ["gem", "dud"]:
        raise HTTPException(status_code=400, detail="gem_status must be 'gem', 'dud', or null")

    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        # Simple update - no version checking needed
        await conn.execute("UPDATE analyzed_tokens SET gem_status = ? WHERE id = ?", (gem_status, token_id))
        await conn.commit()

    # Invalidate both tokens cache and multi-token wallets cache
    cache.invalidate("tokens_history")
    cache.invalidate("multi_early_buyer_wallets")

    status_msg = "cleared" if gem_status is None else f"set to {gem_status}"
    return {"message": f"Token gem status {status_msg}"}


# ============================================================================
# Token Tags Endpoints
# ============================================================================


@router.get("/api/tokens/{token_id}/tags", response_model=TokenTagsResponse)
async def get_token_tags(token_id: int):
    """Get tags for a token"""
    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        conn.row_factory = aiosqlite.Row
        query = "SELECT tag FROM token_tags WHERE token_id = ?"
        cursor = await conn.execute(query, (token_id,))
        rows = await cursor.fetchall()
        tags = [row[0] for row in rows]
        return {"tags": tags}


@router.post("/api/tokens/{token_id}/tags", response_model=MessageResponse)
@conditional_rate_limit(READ_RATE_LIMIT)
async def add_token_tag(token_id: int, request: Request, data: TokenTagRequest):
    """Add a tag to a token (e.g., gem, dud)"""
    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        try:
            await conn.execute(
                "INSERT INTO token_tags (token_id, tag) VALUES (?, ?)",
                (token_id, data.tag),
            )
            await conn.commit()
            log_info("Token tag added", token_id=token_id, tag=data.tag)
        except aiosqlite.IntegrityError:
            log_error("Failed to add token tag - tag already exists", token_id=token_id, tag=data.tag)
            raise HTTPException(status_code=400, detail="Tag already exists for this token")

    # Invalidate caches
    cache.invalidate("tokens_history")
    cache.invalidate("multi_early_buyer_wallets")

    return {"message": f"Tag '{data.tag}' added successfully"}


@router.delete("/api/tokens/{token_id}/tags", response_model=MessageResponse)
@conditional_rate_limit(READ_RATE_LIMIT)
async def remove_token_tag(token_id: int, request: Request, data: TokenTagRequest):
    """Remove a tag from a token"""
    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        await conn.execute("DELETE FROM token_tags WHERE token_id = ? AND tag = ?", (token_id, data.tag))
        await conn.commit()
        log_info("Token tag removed", token_id=token_id, tag=data.tag)

    # Invalidate caches
    cache.invalidate("tokens_history")
    cache.invalidate("multi_early_buyer_wallets")

    return {"message": f"Tag '{data.tag}' removed successfully"}


@router.get("/api/tokens/{mint_address}/top-holders", response_model=TopHoldersResponse)
@conditional_rate_limit(READ_RATE_LIMIT)
async def get_top_holders(mint_address: str, request: Request, limit: int = None):
    """
    Get top N token holders for a given token mint address.

    This endpoint:
    1. Calls Helius getTokenLargestAccounts API (1 credit)
    2. Returns top N holders with their balances
    3. Updates token's cumulative API credits if token exists in DB

    Args:
        mint_address: Token mint address to analyze
        limit: Number of top holders to return (default: from settings, range: 5-20)

    Returns:
        TopHoldersResponse with holder addresses and balances
    """
    try:
        # Get limit from settings if not provided
        if limit is None:
            api_settings = get_api_settings()
            limit = api_settings.topHoldersLimit

        # Validate limit range (aligned with Helius API cap and frontend)
        if limit < 5 or limit > 20:
            raise HTTPException(status_code=400, detail="Limit must be between 5 and 20")

        # Initialize Helius API with separate Top Holders API key
        from meridinate.settings import HELIUS_TOP_HOLDERS_API_KEY

        helius = HeliusAPI(HELIUS_TOP_HOLDERS_API_KEY)

        # Fetch top holders
        log_info("Fetching top holders", mint_address=mint_address[:8], limit=limit)
        holders_data, credits_used = helius.get_top_holders(mint_address, limit=limit)

        if not holders_data:
            log_error("No holders found", mint_address=mint_address[:8])
            raise HTTPException(status_code=404, detail="No holders found for this token")

        # Fetch token metadata to get symbol
        token_symbol = None
        try:
            token_metadata, metadata_credits = helius.get_token_metadata(mint_address)
            credits_used += metadata_credits
            if token_metadata:
                # Extract symbol from onChainMetadata
                on_chain = token_metadata.get("onChainMetadata", {})
                metadata = on_chain.get("metadata", {})
                token_symbol = metadata.get("symbol", "TOKEN")
        except Exception as e:
            log_error(f"Failed to fetch token metadata: {str(e)}", mint_address=mint_address[:8])
            token_symbol = "TOKEN"  # Fallback

        # Fetch wallet balances in USD for each holder
        for holder in holders_data:
            try:
                wallet_balance_usd, balance_credits = helius.get_wallet_balance(holder["address"])
                holder["wallet_balance_usd"] = wallet_balance_usd
                credits_used += balance_credits
            except Exception as e:
                log_error(f"Failed to fetch wallet balance for {holder['address'][:8]}: {str(e)}")
                holder["wallet_balance_usd"] = None

        # Update API credits for this token if it exists in database
        try:
            async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
                # Check if token exists
                cursor = await conn.execute(
                    "SELECT id, credits_used FROM analyzed_tokens WHERE token_address = ?", (mint_address,)
                )
                row = await cursor.fetchone()

                if row:
                    token_id, current_credits = row
                    new_credits = (current_credits or 0) + credits_used

                    # Prepare top holders JSON for storage
                    top_holders_json = json.dumps(holders_data)

                    # Update cumulative credits and top holders data
                    await conn.execute(
                        """UPDATE analyzed_tokens
                        SET credits_used = ?,
                            last_analysis_credits = ?,
                            top_holders_json = ?,
                            top_holders_updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?""",
                        (new_credits, credits_used, top_holders_json, token_id),
                    )
                    await conn.commit()
                    log_info(
                        "Updated token credits and top holders data",
                        token_id=token_id,
                        credits_added=credits_used,
                        total_credits=new_credits,
                        holders_count=len(holders_data),
                    )

                    # Invalidate tokens cache to show updated credits
                    cache.invalidate("tokens_history")
        except Exception as db_error:
            # Log database error but don't fail the request
            log_error(f"Failed to update token credits: {str(db_error)}", mint_address=mint_address[:8])

        # Format response
        return TopHoldersResponse(
            token_address=mint_address,
            token_symbol=token_symbol,
            holders=holders_data,
            total_holders=len(holders_data),
            api_credits_used=credits_used,
        )
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        log_error(f"Error in get_top_holders: {str(e)}", mint_address=mint_address[:8])
        raise HTTPException(status_code=500, detail=f"Failed to fetch top holders: {str(e)}")


# =============================================================================
# Performance Scoring Endpoints
# =============================================================================


class ScoreTokensRequest(BaseModel):
    """Request model for scoring tokens."""

    token_addresses: Optional[List[str]] = None
    score_all_hot: bool = False


class ScoreTokensResponse(BaseModel):
    """Response model for token scoring."""

    status: str
    tokens_scored: int = 0
    tokens_skipped: int = 0
    by_bucket: Dict[str, int] = {}
    errors: List[str] = []
    message: Optional[str] = None


class PerformanceSnapshotResponse(BaseModel):
    """Response model for a performance snapshot."""

    id: int
    token_address: str
    captured_at: str
    price_usd: Optional[float] = None
    mc_usd: Optional[float] = None
    volume_24h_usd: Optional[float] = None
    liquidity_usd: Optional[float] = None
    holder_count: Optional[int] = None
    top_holder_share: Optional[float] = None
    our_positions_pnl_usd: Optional[float] = None
    lp_locked: Optional[bool] = None
    ingest_tier_snapshot: Optional[str] = None


class TokenPerformanceResponse(BaseModel):
    """Response model for token performance data."""

    token_address: str
    performance_score: Optional[float] = None
    performance_bucket: Optional[str] = None
    score_explanation: Optional[List[Dict]] = None
    score_timestamp: Optional[str] = None
    snapshots: List[PerformanceSnapshotResponse] = []


@router.post("/api/tokens/score", response_model=ScoreTokensResponse)
@conditional_rate_limit(READ_RATE_LIMIT)
async def score_tokens(request: Request, payload: ScoreTokensRequest):
    """
    Recompute performance scores for tokens.

    Can score specific tokens by address or all hot tokens.

    Args:
        payload: ScoreTokensRequest with token_addresses or score_all_hot flag

    Returns:
        ScoreTokensResponse with scoring results
    """
    from meridinate.tasks.performance_scorer import score_tokens as do_score_tokens
    from meridinate.tasks.performance_scorer import score_all_hot_tokens

    try:
        if payload.score_all_hot:
            result = await score_all_hot_tokens()
        elif payload.token_addresses:
            result = await do_score_tokens(payload.token_addresses)
        else:
            return ScoreTokensResponse(
                status="error",
                message="Provide token_addresses or set score_all_hot=true",
            )

        if result.get("status") == "disabled":
            return ScoreTokensResponse(
                status="disabled",
                message=result.get("message", "Scoring is disabled"),
            )

        return ScoreTokensResponse(
            status="success",
            tokens_scored=result.get("tokens_scored", 0),
            tokens_skipped=result.get("tokens_skipped", 0),
            by_bucket=result.get("by_bucket", {}),
            errors=result.get("errors", []),
        )

    except Exception as e:
        log_error(f"Error scoring tokens: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/tokens/{token_address}/performance", response_model=TokenPerformanceResponse)
@conditional_rate_limit(READ_RATE_LIMIT)
async def get_token_performance(
    token_address: str,
    request: Request,
    limit: int = 20,
    since_hours: Optional[float] = None,
):
    """
    Get performance data and snapshots for a token.

    Returns current score, bucket, explanation, and recent snapshots.

    Args:
        token_address: Token address
        limit: Max snapshots to return (default: 20)
        since_hours: Only return snapshots from last N hours

    Returns:
        TokenPerformanceResponse with score and snapshot history
    """
    try:
        # Get token's current score from database
        async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(
                """
                SELECT performance_score, performance_bucket, score_explanation, score_timestamp
                FROM analyzed_tokens
                WHERE token_address = ?
            """,
                (token_address,),
            )
            row = await cursor.fetchone()

        score = None
        bucket = None
        explanation = None
        score_timestamp = None

        if row:
            score = row["performance_score"]
            bucket = row["performance_bucket"]
            score_timestamp = row["score_timestamp"]
            if row["score_explanation"]:
                try:
                    explanation = json.loads(row["score_explanation"])
                except Exception:
                    explanation = None

        # Get snapshots
        snapshots = db.get_performance_snapshots(
            token_address, limit=limit, since_hours=since_hours
        )

        # Convert snapshots to response models
        snapshot_responses = []
        for snap in snapshots:
            snapshot_responses.append(
                PerformanceSnapshotResponse(
                    id=snap["id"],
                    token_address=snap["token_address"],
                    captured_at=snap["captured_at"],
                    price_usd=snap.get("price_usd"),
                    mc_usd=snap.get("mc_usd"),
                    volume_24h_usd=snap.get("volume_24h_usd"),
                    liquidity_usd=snap.get("liquidity_usd"),
                    holder_count=snap.get("holder_count"),
                    top_holder_share=snap.get("top_holder_share"),
                    our_positions_pnl_usd=snap.get("our_positions_pnl_usd"),
                    lp_locked=bool(snap.get("lp_locked")) if snap.get("lp_locked") is not None else None,
                    ingest_tier_snapshot=snap.get("ingest_tier_snapshot"),
                )
            )

        return TokenPerformanceResponse(
            token_address=token_address,
            performance_score=score,
            performance_bucket=bucket,
            score_explanation=explanation,
            score_timestamp=score_timestamp,
            snapshots=snapshot_responses,
        )

    except Exception as e:
        log_error(f"Error getting token performance: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class PrimeTokensResponse(BaseModel):
    """Response model for prime tokens ready to promote."""

    count: int
    tokens: List[Dict[str, Any]]


@router.get("/api/tokens/prime-for-promotion", response_model=PrimeTokensResponse)
@conditional_rate_limit(READ_RATE_LIMIT)
async def get_prime_tokens_for_promotion(request: Request, limit: int = 10):
    """
    Get Prime-bucket tokens that are ready for promotion.

    These are tokens scored as 'prime' that are still in ingested/enriched tier.

    Args:
        limit: Max tokens to return (default: 10)

    Returns:
        PrimeTokensResponse with list of tokens ready to promote
    """
    try:
        tokens = db.get_prime_tokens_for_promotion(limit=limit)
        return PrimeTokensResponse(count=len(tokens), tokens=tokens)
    except Exception as e:
        log_error(f"Error getting prime tokens: {e}")
        raise HTTPException(status_code=500, detail=str(e))
