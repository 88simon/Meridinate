"""
Starred Items (Favorites) API

Manages starred wallets and tokens. Starred items appear in the Codex
and receive priority in tracking/backfill cycles.
"""

import aiosqlite
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List

from meridinate import settings

router = APIRouter()


class StarRequest(BaseModel):
    item_type: str  # "wallet" or "token"
    item_address: str
    nametag: Optional[str] = None


class StarredItem(BaseModel):
    id: int
    item_type: str
    item_address: str
    nametag: Optional[str]
    starred_at: str


class StarredResponse(BaseModel):
    wallets: List[StarredItem]
    tokens: List[StarredItem]
    total: int


@router.get("/api/starred")
async def get_starred():
    """Get all starred items (wallets + tokens), with token names for starred tokens."""
    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("""
            SELECT s.*,
                   t.id as token_id,
                   t.token_name,
                   t.token_symbol
            FROM starred_items s
            LEFT JOIN analyzed_tokens t
                ON s.item_type = 'token' AND s.item_address = t.token_address
                AND (t.deleted_at IS NULL OR t.deleted_at = '')
            ORDER BY s.starred_at DESC
        """)
        rows = [dict(r) for r in await cursor.fetchall()]

    wallets = [r for r in rows if r["item_type"] == "wallet"]
    tokens = [r for r in rows if r["item_type"] == "token"]

    return {"wallets": wallets, "tokens": tokens, "total": len(rows)}


@router.post("/api/starred")
async def star_item(req: StarRequest):
    """Star a wallet or token."""
    if req.item_type not in ("wallet", "token"):
        raise HTTPException(status_code=400, detail="item_type must be 'wallet' or 'token'")

    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        await conn.execute(
            "INSERT OR IGNORE INTO starred_items (item_type, item_address, nametag) VALUES (?, ?, ?)",
            (req.item_type, req.item_address, req.nametag),
        )
        await conn.commit()

    return {"status": "starred", "item_type": req.item_type, "item_address": req.item_address}


@router.delete("/api/starred")
async def unstar_item(item_type: str, item_address: str):
    """Unstar a wallet or token."""
    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        await conn.execute(
            "DELETE FROM starred_items WHERE item_type = ? AND item_address = ?",
            (item_type, item_address),
        )
        await conn.commit()

    return {"status": "unstarred", "item_type": item_type, "item_address": item_address}


@router.get("/api/starred/check")
async def check_starred(item_type: str, item_address: str):
    """Check if an item is starred."""
    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        cursor = await conn.execute(
            "SELECT 1 FROM starred_items WHERE item_type = ? AND item_address = ?",
            (item_type, item_address),
        )
        row = await cursor.fetchone()

    return {"starred": row is not None}


@router.put("/api/starred/nametag")
async def update_nametag(req: StarRequest):
    """Update the nametag for a starred item."""
    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        await conn.execute(
            "UPDATE starred_items SET nametag = ? WHERE item_type = ? AND item_address = ?",
            (req.nametag, req.item_type, req.item_address),
        )
        await conn.commit()

    return {"status": "updated"}


@router.get("/api/starred/addresses")
async def get_starred_addresses():
    """Get just the addresses of all starred items (for quick lookup in frontend)."""
    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        cursor = await conn.execute("SELECT item_type, item_address FROM starred_items")
        rows = await cursor.fetchall()

    wallet_set = [r[1] for r in rows if r[0] == "wallet"]
    token_set = [r[1] for r in rows if r[0] == "token"]

    return {"wallets": wallet_set, "tokens": token_set}
