"""
Tags router - wallet tagging and Codex endpoints

Provides REST endpoints for wallet tagging operations
"""

import aiosqlite
from fastapi import APIRouter, HTTPException

from meridinate import analyzed_tokens_db as db
from meridinate import settings
from meridinate.cache import ResponseCache
from meridinate.utils.models import (
    AddTagRequest,
    BatchTagsRequest,
    CodexResponse,
    MessageResponse,
    NametagResponse,
    RemoveTagRequest,
    SetNametagRequest,
    TagsResponse,
    WalletTagsResponse,
)
from meridinate.secure_logging import log_error

router = APIRouter()
cache = ResponseCache()


@router.get("/wallets/{wallet_address}/tags", response_model=WalletTagsResponse)
async def get_wallet_tags(wallet_address: str):
    """Get tags for a wallet"""
    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        conn.row_factory = aiosqlite.Row
        query = "SELECT tag, is_kol FROM wallet_tags WHERE wallet_address = ?"
        cursor = await conn.execute(query, (wallet_address,))
        rows = await cursor.fetchall()
        tags = [{"tag": row[0], "is_kol": bool(row[1])} for row in rows]
        return {"tags": tags}


@router.post("/wallets/{wallet_address}/tags", response_model=MessageResponse)
async def add_wallet_tag(wallet_address: str, request: AddTagRequest):
    """Add a tag to a wallet"""
    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        try:
            await conn.execute(
                "INSERT INTO wallet_tags (wallet_address, tag, is_kol) VALUES (?, ?, ?)",
                (wallet_address, request.tag, request.is_kol),
            )
            await conn.commit()
        except aiosqlite.IntegrityError:
            raise HTTPException(status_code=400, detail="Tag already exists for this wallet")

    cache.invalidate("codex")
    return {"message": "Tag added successfully"}


@router.delete("/wallets/{wallet_address}/tags", response_model=MessageResponse)
async def remove_wallet_tag(wallet_address: str, request: RemoveTagRequest):
    """Remove a tag from a wallet"""
    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        await conn.execute(
            "DELETE FROM wallet_tags WHERE wallet_address = ? AND tag = ?", (wallet_address, request.tag)
        )
        await conn.commit()

    cache.invalidate("codex")
    return {"message": "Tag removed successfully"}


@router.get("/tags", response_model=TagsResponse)
async def get_all_tags():
    """Get all unique tags"""
    cache_key = "all_tags"
    cached_data, _ = cache.get(cache_key)
    if cached_data:
        return cached_data

    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        query = "SELECT DISTINCT tag FROM wallet_tags ORDER BY tag"
        cursor = await conn.execute(query)
        rows = await cursor.fetchall()
        tags = [row[0] for row in rows]
        result = {"tags": tags}
        cache.set(cache_key, result)
        return result


@router.get("/codex", response_model=CodexResponse)
async def get_codex():
    """Get all wallets with tags (Codex)"""
    cache_key = "codex"
    cached_data, _ = cache.get(cache_key)
    if cached_data:
        return cached_data

    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        conn.row_factory = aiosqlite.Row
        query = """
            SELECT wallet_address, tag, is_kol
            FROM wallet_tags
            ORDER BY wallet_address, tag
        """
        cursor = await conn.execute(query)
        rows = await cursor.fetchall()

        # Group by wallet_address
        wallets_dict = {}
        for row in rows:
            wallet_addr = row[0]
            if wallet_addr not in wallets_dict:
                wallets_dict[wallet_addr] = {"wallet_address": wallet_addr, "nametag": None, "tags": [], "token_count": 0}
            wallets_dict[wallet_addr]["tags"].append({"tag": row[1], "is_kol": bool(row[2])})

        # Get token counts for each wallet
        wallet_addresses = list(wallets_dict.keys())
        if wallet_addresses:
            # Use COUNT(DISTINCT token_id) to get number of unique tokens each wallet appears in
            placeholders = ",".join("?" * len(wallet_addresses))
            token_count_query = f"""
                SELECT ebw.wallet_address, COUNT(DISTINCT ebw.token_id) as token_count
                FROM early_buyer_wallets ebw
                JOIN analyzed_tokens at ON ebw.token_id = at.id
                WHERE ebw.wallet_address IN ({placeholders})
                  AND (at.is_deleted = 0 OR at.is_deleted IS NULL)
                GROUP BY ebw.wallet_address
            """
            cursor = await conn.execute(token_count_query, wallet_addresses)
            token_count_rows = await cursor.fetchall()

            for row in token_count_rows:
                wallet_addr = row[0]
                token_count = row[1]
                if wallet_addr in wallets_dict:
                    wallets_dict[wallet_addr]["token_count"] = token_count

            # Get nametags for each wallet
            nametag_query = f"""
                SELECT wallet_address, nametag
                FROM wallet_nametags
                WHERE wallet_address IN ({placeholders})
            """
            cursor = await conn.execute(nametag_query, wallet_addresses)
            nametag_rows = await cursor.fetchall()

            for row in nametag_rows:
                wallet_addr = row[0]
                nametag = row[1]
                if wallet_addr in wallets_dict:
                    wallets_dict[wallet_addr]["nametag"] = nametag

        result = {"wallets": list(wallets_dict.values())}
        cache.set(cache_key, result)
        return result


@router.post("/wallets/batch-tags")
async def get_batch_wallet_tags(payload: BatchTagsRequest):
    """Get tags for multiple wallets in one query"""
    if not payload.addresses:
        raise HTTPException(status_code=400, detail="addresses array is required")
    try:
        return db.get_multi_wallet_tags(payload.addresses)
    except Exception as exc:
        log_error(f"Failed to get batch wallet tags: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/tags/{tag}/wallets")
async def get_wallets_by_tag(tag: str):
    """Get all wallets with a specific tag"""
    try:
        wallets = db.get_wallets_by_tag(tag)
        return {"tag": tag, "wallets": wallets}
    except Exception as exc:
        log_error(f"Failed to get wallets by tag: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/wallets/{wallet_address}/nametag", response_model=NametagResponse)
async def get_wallet_nametag(wallet_address: str):
    """Get the nametag (display name) for a wallet"""
    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        cursor = await conn.execute(
            "SELECT nametag FROM wallet_nametags WHERE wallet_address = ?",
            (wallet_address,)
        )
        row = await cursor.fetchone()
        return {"wallet_address": wallet_address, "nametag": row[0] if row else None}


@router.put("/wallets/{wallet_address}/nametag", response_model=MessageResponse)
async def set_wallet_nametag(wallet_address: str, request: SetNametagRequest):
    """Set or update the nametag (display name) for a wallet"""
    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        await conn.execute(
            """
            INSERT INTO wallet_nametags (wallet_address, nametag, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(wallet_address) DO UPDATE SET
                nametag = excluded.nametag,
                updated_at = CURRENT_TIMESTAMP
            """,
            (wallet_address, request.nametag)
        )
        await conn.commit()

    cache.invalidate("codex")
    return {"message": "Nametag updated successfully"}


@router.delete("/wallets/{wallet_address}/nametag", response_model=MessageResponse)
async def delete_wallet_nametag(wallet_address: str):
    """Remove the nametag (display name) from a wallet"""
    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        await conn.execute(
            "DELETE FROM wallet_nametags WHERE wallet_address = ?",
            (wallet_address,)
        )
        await conn.commit()

    cache.invalidate("codex")
    return {"message": "Nametag removed successfully"}
