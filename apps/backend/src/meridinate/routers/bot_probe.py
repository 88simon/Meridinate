"""
Bot Probe API

Endpoints for running deep bot probes, retrieving profiles,
and comparing bot strategies.
"""

import json
import threading
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional

import aiosqlite
from fastapi import APIRouter, Query

from meridinate import settings
from meridinate.observability import log_info, log_error

router = APIRouter()

CHICAGO_TZ = ZoneInfo("America/Chicago")

# In-memory probe status
_probe_status = {
    "running": False,
    "wallet": None,
    "phase": "",
    "detail": "",
    "progress_current": 0,
    "progress_total": 0,
    "credits_used": 0,
}
_probe_lock = threading.Lock()


def _update_probe_status(**kwargs):
    with _probe_lock:
        _probe_status.update(kwargs)


def _run_probe_background(wallet_address: str, phases: str):
    """Run probe phases in background thread."""
    from meridinate.services.bot_probe import run_phase1_full_transactions, run_phase2_discover_unknown_tokens
    from meridinate.services.bot_profile_builder import build_profile

    _update_probe_status(running=True, wallet=wallet_address, phase="starting",
                         detail="Initializing probe...", progress_current=0, progress_total=0, credits_used=0)
    try:
        total_credits = 0

        if "1" in phases or "all" in phases:
            _update_probe_status(phase="phase1", detail="Collecting full transaction history...")

            def on_p1_progress(current, total, token_name, credits):
                _update_probe_status(
                    detail=f"Phase 1: {current}/{total} — {token_name}",
                    progress_current=current, progress_total=total, credits_used=credits,
                )

            result1 = run_phase1_full_transactions(wallet_address, on_progress=on_p1_progress)
            total_credits += result1.get("credits_used", 0)
            _update_probe_status(
                detail=f"Phase 1 complete: {result1.get('transactions_parsed', 0)} txs, "
                       f"{result1.get('round_trips', 0)} round-trips, {total_credits} credits",
                credits_used=total_credits,
            )

        if "2" in phases or "all" in phases:
            _update_probe_status(phase="phase2", detail="Discovering unknown tokens...")

            def on_p2_progress(current, total, credits):
                _update_probe_status(
                    detail=f"Phase 2: scanning main wallet sigs {current}/{total}",
                    progress_current=current, progress_total=total, credits_used=total_credits + credits,
                )

            result2 = run_phase2_discover_unknown_tokens(wallet_address, on_progress=on_p2_progress)
            total_credits += result2.get("credits_used", 0)
            _update_probe_status(
                detail=f"Phase 2 complete: {result2.get('unknown_tokens_discovered', 0)} unknown tokens found",
                credits_used=total_credits,
            )

        if "3" in phases or "all" in phases:
            _update_probe_status(phase="phase3", detail="Computing strategy profile...")
            profile = build_profile(wallet_address)
            archetype = profile.get("archetype", "unknown")
            wr = profile.get("performance", {}).get("win_rate_by_trade", 0)
            _update_probe_status(
                detail=f"Phase 3 complete: {archetype}, {wr:.0%} win rate",
            )

        _update_probe_status(
            phase="complete",
            detail=f"Probe complete — {total_credits} credits used",
            credits_used=total_credits,
        )

    except Exception as e:
        log_error(f"[BotProbe] Probe failed: {e}")
        import traceback
        traceback.print_exc()
        _update_probe_status(phase="error", detail=str(e))
    finally:
        _update_probe_status(running=False)


@router.post("/api/bot-probe/run")
async def run_probe(
    wallet: str = Query(..., description="Wallet address to probe"),
    phases: str = Query("all", description="Phases to run: all, 1, 2, 3, 12, 13, 23"),
):
    """Start a deep bot probe as a background job."""
    with _probe_lock:
        if _probe_status["running"]:
            return {"status": "already_running", "wallet": _probe_status["wallet"]}

    thread = threading.Thread(target=_run_probe_background, args=(wallet, phases), daemon=True)
    thread.start()

    return {"status": "started", "wallet": wallet, "phases": phases}


@router.get("/api/bot-probe/status")
async def probe_status():
    """Get current probe status."""
    with _probe_lock:
        return dict(_probe_status)


@router.get("/api/bot-probe/profile/{wallet_address}")
async def get_profile(wallet_address: str):
    """Get a computed bot profile."""
    try:
        async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                "SELECT * FROM bot_probe_profiles WHERE wallet_address = ?",
                (wallet_address,),
            )
            row = await cur.fetchone()
            if row:
                result = dict(row)
                if result.get("profile_json"):
                    result["profile"] = json.loads(result["profile_json"])
                if result.get("comparison_json"):
                    result["comparison"] = json.loads(result["comparison_json"])
                return result
            return {"error": "Profile not found"}
    except Exception as e:
        return {"error": str(e)}


@router.post("/api/bot-probe/compare")
async def compare_bots(
    wallet_a: str = Query(..., description="First wallet address"),
    wallet_b: str = Query(..., description="Second wallet address"),
):
    """Compare two bot profiles."""
    from meridinate.services.bot_profile_builder import compare_profiles
    return compare_profiles(wallet_a, wallet_b)


@router.get("/api/bot-probe/runs")
async def list_runs(
    wallet: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
):
    """List probe runs."""
    try:
        async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
            conn.row_factory = aiosqlite.Row
            if wallet:
                cur = await conn.execute(
                    "SELECT * FROM bot_probe_runs WHERE wallet_address = ? ORDER BY id DESC LIMIT ?",
                    (wallet, limit),
                )
            else:
                cur = await conn.execute(
                    "SELECT * FROM bot_probe_runs ORDER BY id DESC LIMIT ?", (limit,),
                )
            return {"runs": [dict(r) for r in await cur.fetchall()]}
    except Exception as e:
        return {"runs": [], "error": str(e)}


@router.get("/api/bot-probe/transactions/{wallet_address}")
async def get_transactions(
    wallet_address: str,
    token: Optional[str] = Query(None, description="Filter by token address"),
    limit: int = Query(200, ge=1, le=1000),
):
    """Get probe transactions for a wallet."""
    try:
        async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
            conn.row_factory = aiosqlite.Row
            if token:
                cur = await conn.execute(
                    "SELECT * FROM bot_probe_transactions WHERE wallet_address = ? AND token_address = ? ORDER BY timestamp_unix LIMIT ?",
                    (wallet_address, token, limit),
                )
            else:
                cur = await conn.execute(
                    "SELECT * FROM bot_probe_transactions WHERE wallet_address = ? ORDER BY timestamp_unix DESC LIMIT ?",
                    (wallet_address, limit),
                )
            return {"transactions": [dict(r) for r in await cur.fetchall()]}
    except Exception as e:
        return {"transactions": [], "error": str(e)}


@router.get("/api/bot-probe/round-trips/{wallet_address}")
async def get_round_trips(
    wallet_address: str,
    token: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
):
    """Get FIFO round-trips for a wallet."""
    try:
        async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
            conn.row_factory = aiosqlite.Row
            if token:
                cur = await conn.execute(
                    "SELECT * FROM bot_probe_round_trips WHERE wallet_address = ? AND token_address = ? ORDER BY entry_timestamp_unix LIMIT ?",
                    (wallet_address, token, limit),
                )
            else:
                cur = await conn.execute(
                    "SELECT * FROM bot_probe_round_trips WHERE wallet_address = ? ORDER BY entry_timestamp_unix DESC LIMIT ?",
                    (wallet_address, limit),
                )
            return {"round_trips": [dict(r) for r in await cur.fetchall()]}
    except Exception as e:
        return {"round_trips": [], "error": str(e)}
