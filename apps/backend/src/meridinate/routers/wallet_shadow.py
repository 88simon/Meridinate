"""
Wallet Shadow API — Real-time bot tracking endpoints.
"""

import asyncio
import json
from typing import Optional

import aiosqlite
from fastapi import APIRouter, Query

from meridinate import settings
from meridinate.observability import log_info
from meridinate.routers.stats import _status_bar_cache

router = APIRouter()


PIPELINE_INFO = {
    "ingest_tier0": {
        "name": "Auto-Scan (Discovery)",
        "credits": "30-80 per token",
        "description": "Discovers new tokens from DexScreener, runs Helius analysis",
        "needed_for_tracker": False,
    },
    "ingest_hot_refresh": {
        "name": "MC Tracker",
        "credits": "0 (DexScreener, free)",
        "description": "Decay-based market cap polling, auto-verdicts",
        "needed_for_tracker": False,
    },
    "swab_position_check": {
        "name": "Position Checker",
        "credits": "~10 per position",
        "description": "Monitors wallet holdings, detects buys/sells, computes PnL",
        "needed_for_tracker": False,
    },
}


@router.post("/api/wallet-shadow/pipeline/{job_id}/pause")
async def pause_pipeline(job_id: str):
    """Pause a specific pipeline job."""
    from meridinate.scheduler import get_scheduler
    scheduler = get_scheduler()
    job = scheduler.get_job(job_id)
    if not job:
        return {"error": f"Job '{job_id}' not found"}
    job.pause()
    info = PIPELINE_INFO.get(job_id, {})
    log_info(f"[Pipelines] Paused: {info.get('name', job_id)}")
    _status_bar_cache.invalidate("status_bar")
    return {"success": True, "job_id": job_id, "status": "paused"}


@router.post("/api/wallet-shadow/pipeline/{job_id}/resume")
async def resume_pipeline(job_id: str):
    """Resume a specific pipeline job."""
    from meridinate.scheduler import get_scheduler
    scheduler = get_scheduler()
    job = scheduler.get_job(job_id)
    if not job:
        return {"error": f"Job '{job_id}' not found"}
    job.resume()
    info = PIPELINE_INFO.get(job_id, {})
    log_info(f"[Pipelines] Resumed: {info.get('name', job_id)}")
    _status_bar_cache.invalidate("status_bar")
    return {"success": True, "job_id": job_id, "status": "resumed"}


@router.post("/api/wallet-shadow/pipelines/pause-all")
async def pause_all_pipelines():
    """Pause all credit-consuming pipelines."""
    from meridinate.scheduler import get_scheduler
    scheduler = get_scheduler()
    paused = []
    for job in scheduler.get_jobs():
        job.pause()
        paused.append(job.id)
    log_info(f"[Pipelines] Paused all {len(paused)} jobs")
    _status_bar_cache.invalidate("status_bar")
    return {"status": "all_paused", "jobs_paused": paused}


@router.post("/api/wallet-shadow/pipelines/resume-all")
async def resume_all_pipelines():
    """Resume all pipelines."""
    from meridinate.scheduler import get_scheduler
    scheduler = get_scheduler()
    resumed = []
    for job in scheduler.get_jobs():
        job.resume()
        resumed.append(job.id)
    log_info(f"[Pipelines] Resumed all {len(resumed)} jobs")
    _status_bar_cache.invalidate("status_bar")
    return {"status": "all_resumed", "jobs_resumed": resumed}


@router.get("/api/wallet-shadow/pipeline-status")
async def pipeline_status():
    """Get status of all pipelines with individual pause state."""
    from meridinate.scheduler import get_scheduler
    scheduler = get_scheduler()

    jobs = []
    all_paused = True
    for job in scheduler.get_jobs():
        is_paused = job.next_run_time is None
        if not is_paused:
            all_paused = False
        info = PIPELINE_INFO.get(job.id, {})
        jobs.append({
            "id": job.id,
            "name": info.get("name", job.id),
            "paused": is_paused,
            "credits": info.get("credits", "unknown"),
            "description": info.get("description", ""),
            "needed_for_tracker": info.get("needed_for_tracker", False),
        })

    return {"all_paused": all_paused, "jobs": jobs}


@router.post("/api/wallet-shadow/rename")
async def rename_wallet(
    wallet: str = Query(...),
    label: str = Query(..., description="New label"),
):
    """Rename a tracked wallet."""
    try:
        async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
            await conn.execute(
                "UPDATE wallet_shadow_targets SET label = ? WHERE wallet_address = ?",
                (label, wallet),
            )
            await conn.commit()
            return {"success": True, "message": f"Renamed to '{label}'"}
    except Exception as e:
        return {"error": str(e)}


@router.post("/api/wallet-shadow/track")
async def add_wallet(
    wallet: str = Query(..., description="Wallet address to track"),
    label: str = Query("", description="Label for this wallet"),
):
    """Add a wallet to real-time tracking."""
    from meridinate.services.wallet_shadow import add_tracked_wallet, get_shadow_listener
    result = add_tracked_wallet(wallet, label)

    # Refresh the listener's wallet list if it's running
    listener = get_shadow_listener()
    if listener._running:
        await listener.refresh_wallets()

    return result


@router.post("/api/wallet-shadow/untrack")
async def remove_wallet(wallet: str = Query(...)):
    """Stop tracking a wallet (keeps history)."""
    from meridinate.services.wallet_shadow import remove_tracked_wallet, get_shadow_listener
    result = remove_tracked_wallet(wallet)

    listener = get_shadow_listener()
    if listener._running:
        await listener.refresh_wallets()

    return result


@router.get("/api/wallet-shadow/targets")
async def list_targets():
    """List all tracked wallets."""
    from meridinate.services.wallet_shadow import get_tracked_wallets
    return {"targets": get_tracked_wallets()}


@router.post("/api/wallet-shadow/start")
async def start_listener():
    """Start the real-time shadow listener."""
    from meridinate.services.wallet_shadow import get_shadow_listener
    listener = get_shadow_listener()
    if listener._running:
        return {"status": "already_running", **listener.get_stats()}
    await listener.start()
    return {"status": "started", **listener.get_stats()}


@router.post("/api/wallet-shadow/stop")
async def stop_listener():
    """Stop the real-time shadow listener."""
    from meridinate.services.wallet_shadow import get_shadow_listener
    listener = get_shadow_listener()
    await listener.stop()
    return {"status": "stopped"}


@router.get("/api/wallet-shadow/status")
async def get_status():
    """Get listener status and stats."""
    from meridinate.services.wallet_shadow import get_shadow_listener
    return get_shadow_listener().get_stats()


@router.get("/api/wallet-shadow/feed")
async def get_feed(
    limit: int = Query(50, ge=1, le=200),
    wallet: Optional[str] = Query(None),
):
    """Get live trade feed from in-memory buffer."""
    from meridinate.services.wallet_shadow import get_shadow_listener
    return {"trades": get_shadow_listener().get_feed(limit=limit, wallet=wallet)}


@router.get("/api/wallet-shadow/trades")
async def get_trades(
    wallet: Optional[str] = Query(None),
    token: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
):
    """Get stored trades from database."""
    try:
        async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
            conn.row_factory = aiosqlite.Row
            query = "SELECT * FROM wallet_shadow_trades WHERE 1=1"
            params = []
            if wallet:
                query += " AND wallet_address = ?"
                params.append(wallet)
            if token:
                query += " AND token_address = ?"
                params.append(token)
            query += " ORDER BY timestamp_unix DESC LIMIT ?"
            params.append(limit)
            cur = await conn.execute(query, params)
            return {"trades": [dict(r) for r in await cur.fetchall()]}
    except Exception as e:
        return {"trades": [], "error": str(e)}


@router.get("/api/wallet-shadow/signal-wallets/{wallet_address}")
async def get_signal_wallets(
    wallet_address: str,
    min_appearances: int = Query(2, ge=1, description="Minimum times a wallet appeared before the tracked bot"),
    limit: int = Query(30, ge=1, le=100),
):
    """
    Signal wallet frequency analysis — find wallets that consistently
    appear before a tracked bot enters a token. These are likely the
    bot's private allowlist / signal sources.
    """
    try:
        async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
            conn.row_factory = aiosqlite.Row

            # Frequency: which wallets appear most often as preceding buyers?
            cur = await conn.execute("""
                SELECT preceding_wallet,
                       COUNT(*) as times_preceded,
                       COUNT(DISTINCT token_address) as unique_tokens,
                       ROUND(AVG(seconds_before_tracked), 1) as avg_seconds_before,
                       ROUND(MIN(seconds_before_tracked), 1) as min_seconds_before,
                       ROUND(MAX(seconds_before_tracked), 1) as max_seconds_before,
                       ROUND(AVG(preceding_sol_amount), 4) as avg_sol
                FROM wallet_shadow_preceding_buyers
                WHERE tracked_wallet = ?
                GROUP BY preceding_wallet
                HAVING times_preceded >= ?
                ORDER BY times_preceded DESC
                LIMIT ?
            """, (wallet_address, min_appearances, limit))
            signal_wallets = [dict(r) for r in await cur.fetchall()]

            # Total trades analyzed
            cur2 = await conn.execute(
                "SELECT COUNT(DISTINCT token_address) as tokens_analyzed FROM wallet_shadow_preceding_buyers WHERE tracked_wallet = ?",
                (wallet_address,),
            )
            meta = dict(await cur2.fetchone())

            # For each signal wallet, get the tokens they preceded on
            for sw in signal_wallets:
                cur3 = await conn.execute("""
                    SELECT pb.token_address, t.token_name, pb.seconds_before_tracked, pb.preceding_sol_amount
                    FROM wallet_shadow_preceding_buyers pb
                    LEFT JOIN analyzed_tokens t ON t.token_address = pb.token_address
                    WHERE pb.tracked_wallet = ? AND pb.preceding_wallet = ?
                    ORDER BY pb.preceding_timestamp_unix DESC
                    LIMIT 10
                """, (wallet_address, sw["preceding_wallet"]))
                sw["recent_tokens"] = [dict(r) for r in await cur3.fetchall()]

            return {
                "wallet_address": wallet_address,
                "tokens_analyzed": meta.get("tokens_analyzed", 0),
                "signal_wallets": signal_wallets,
            }
    except Exception as e:
        return {"error": str(e)}


@router.get("/api/wallet-shadow/convergences")
async def get_convergences(limit: int = Query(20, ge=1, le=100)):
    """Get cross-bot convergence events — tokens where 2+ tracked wallets entered."""
    try:
        async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                "SELECT * FROM wallet_shadow_convergences ORDER BY first_entry_unix DESC LIMIT ?",
                (limit,),
            )
            convergences = []
            for r in await cur.fetchall():
                d = dict(r)
                if d.get("wallets_json"):
                    try:
                        d["wallets"] = json.loads(d["wallets_json"])
                    except Exception:
                        d["wallets"] = []
                convergences.append(d)
            return {"convergences": convergences}
    except Exception as e:
        return {"convergences": [], "error": str(e)}


@router.get("/api/wallet-shadow/open-positions")
async def get_open_positions(wallet: Optional[str] = Query(None)):
    """Get current open positions per wallet — net buys minus sells per token."""
    try:
        async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
            conn.row_factory = aiosqlite.Row
            query = """
                SELECT wallet_address, token_address, token_name,
                       SUM(CASE WHEN direction = 'buy' THEN sol_amount ELSE 0 END) as total_bought_sol,
                       SUM(CASE WHEN direction = 'sell' THEN sol_amount ELSE 0 END) as total_sold_sol,
                       SUM(CASE WHEN direction = 'buy' THEN token_amount ELSE 0 END) as tokens_bought,
                       SUM(CASE WHEN direction = 'sell' THEN token_amount ELSE 0 END) as tokens_sold,
                       SUM(CASE WHEN direction = 'buy' THEN 1 ELSE 0 END) as buy_count,
                       SUM(CASE WHEN direction = 'sell' THEN 1 ELSE 0 END) as sell_count,
                       MIN(CASE WHEN direction = 'buy' THEN timestamp_unix END) as first_buy_unix,
                       MAX(timestamp_unix) as last_action_unix
                FROM wallet_shadow_trades
                WHERE 1=1
            """
            params: list = []
            if wallet:
                query += " AND wallet_address = ?"
                params.append(wallet)
            query += " GROUP BY wallet_address, token_address HAVING tokens_bought > tokens_sold * 0.99"

            cur = await conn.execute(query, params)
            rows = [dict(r) for r in await cur.fetchall()]

            # Compute per-position metrics
            positions = []
            for r in rows:
                remaining_tokens = r["tokens_bought"] - r["tokens_sold"]
                net_sol = r["total_bought_sol"] - r["total_sold_sol"]
                positions.append({
                    **r,
                    "remaining_tokens": round(remaining_tokens, 6),
                    "net_sol_deployed": round(net_sol, 6),
                    "status": "open" if remaining_tokens > 0.001 else "closed",
                })

            # Summary per wallet
            by_wallet = {}
            for p in positions:
                if p["status"] != "open":
                    continue
                w = p["wallet_address"]
                if w not in by_wallet:
                    by_wallet[w] = {"open_positions": 0, "total_sol_deployed": 0}
                by_wallet[w]["open_positions"] += 1
                by_wallet[w]["total_sol_deployed"] += p["net_sol_deployed"]

            return {
                "positions": [p for p in positions if p["status"] == "open"],
                "by_wallet": by_wallet,
            }
    except Exception as e:
        return {"positions": [], "by_wallet": {}, "error": str(e)}


@router.get("/api/wallet-shadow/token-heat")
async def get_token_heat(minutes: int = Query(30, ge=5, le=1440)):
    """Token heat map — tokens with the most entries from tracked wallets recently."""
    try:
        async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
            conn.row_factory = aiosqlite.Row
            import time as _time
            cutoff = int(_time.time()) - (minutes * 60)

            cur = await conn.execute("""
                SELECT token_address, token_name,
                       COUNT(*) as total_entries,
                       COUNT(DISTINCT wallet_address) as unique_wallets,
                       SUM(CASE WHEN direction = 'buy' THEN 1 ELSE 0 END) as buys,
                       SUM(CASE WHEN direction = 'sell' THEN 1 ELSE 0 END) as sells,
                       ROUND(SUM(CASE WHEN direction = 'buy' THEN sol_amount ELSE 0 END), 4) as total_sol_in,
                       MIN(timestamp_unix) as first_entry_unix,
                       MAX(timestamp_unix) as last_entry_unix,
                       GROUP_CONCAT(DISTINCT wallet_address) as wallets
                FROM wallet_shadow_trades
                WHERE timestamp_unix >= ? AND direction = 'buy'
                GROUP BY token_address
                ORDER BY unique_wallets DESC, total_entries DESC
                LIMIT 20
            """, (cutoff,))
            tokens = [dict(r) for r in await cur.fetchall()]

            # Resolve wallet labels
            targets = {}
            tcur = await conn.execute("SELECT wallet_address, label FROM wallet_shadow_targets")
            for r in await tcur.fetchall():
                targets[r[0]] = r[1]

            for t in tokens:
                wallet_list = (t.get("wallets") or "").split(",")
                t["wallet_labels"] = [targets.get(w, w) for w in wallet_list if w]
                del t["wallets"]

            return {"tokens": tokens, "window_minutes": minutes}
    except Exception as e:
        return {"tokens": [], "error": str(e)}


@router.get("/api/wallet-shadow/alerts")
async def get_alerts(limit: int = Query(20, ge=1, le=100)):
    """
    Get real-time alerts: sizing anomalies, copy/follow events, convergence.
    Computed from recent trade data.
    """
    try:
        async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
            conn.row_factory = aiosqlite.Row
            alerts = []
            import time as _time
            now = int(_time.time())

            # Get targets for labels
            targets = {}
            tcur = await conn.execute("SELECT wallet_address, label FROM wallet_shadow_targets")
            for r in await tcur.fetchall():
                targets[r[0]] = r[1]

            def _label(addr):
                return targets.get(addr) or addr[:12] + '...'

            # 1. SIZING ANOMALIES — trades > 2x the wallet's average
            for wallet_addr, label in targets.items():
                cur = await conn.execute("""
                    SELECT AVG(sol_amount) as avg_sol, COUNT(*) as trade_count
                    FROM wallet_shadow_trades
                    WHERE wallet_address = ? AND direction = 'buy'
                """, (wallet_addr,))
                stats = await cur.fetchone()
                if not stats or not stats["avg_sol"] or stats["trade_count"] < 3:
                    continue

                avg_sol = stats["avg_sol"]
                cur2 = await conn.execute("""
                    SELECT token_name, token_address, sol_amount, timestamp, timestamp_unix
                    FROM wallet_shadow_trades
                    WHERE wallet_address = ? AND direction = 'buy' AND sol_amount > ? * 2
                    ORDER BY timestamp_unix DESC LIMIT 5
                """, (wallet_addr, avg_sol))
                for r in await cur2.fetchall():
                    multiple = round(r["sol_amount"] / avg_sol, 1)
                    alerts.append({
                        "type": "sizing_anomaly",
                        "wallet": wallet_addr,
                        "wallet_label": label,
                        "token": r["token_address"],
                        "token_name": r["token_name"],
                        "detail": f"{multiple}x avg size ({r['sol_amount']:.4f} vs {avg_sol:.4f} SOL avg)",
                        "timestamp_unix": r["timestamp_unix"],
                        "timestamp": r["timestamp"],
                    })

            # 2. COPY/FOLLOW EVENTS — one tracked wallet enters within 30s of another
            cur3 = await conn.execute("""
                SELECT a.wallet_address as leader, b.wallet_address as follower,
                       a.token_address, a.token_name,
                       a.timestamp_unix as leader_time, b.timestamp_unix as follower_time,
                       b.timestamp_unix - a.timestamp_unix as delay_seconds,
                       a.sol_amount as leader_sol, b.sol_amount as follower_sol
                FROM wallet_shadow_trades a
                JOIN wallet_shadow_trades b ON a.token_address = b.token_address
                    AND a.wallet_address != b.wallet_address
                    AND a.direction = 'buy' AND b.direction = 'buy'
                    AND b.timestamp_unix > a.timestamp_unix
                    AND b.timestamp_unix - a.timestamp_unix <= 30
                ORDER BY b.timestamp_unix DESC
                LIMIT 20
            """)
            for r in await cur3.fetchall():
                alerts.append({
                    "type": "copy_follow",
                    "wallet": r["follower"],
                    "wallet_label": _label(r["follower"]),
                    "leader": r["leader"],
                    "leader_label": _label(r["leader"]),
                    "token": r["token_address"],
                    "token_name": r["token_name"],
                    "detail": f"{_label(r['follower'])} followed {_label(r['leader'])} by {r['delay_seconds']}s",
                    "timestamp_unix": r["follower_time"],
                    "delay_seconds": r["delay_seconds"],
                })

            # Sort all alerts by time, newest first
            alerts.sort(key=lambda a: a.get("timestamp_unix", 0), reverse=True)
            return {"alerts": alerts[:limit]}
    except Exception as e:
        return {"alerts": [], "error": str(e)}


@router.get("/api/wallet-shadow/summary/{wallet_address}")
async def get_wallet_summary(wallet_address: str):
    """Get a summary of captured trades for a wallet."""
    try:
        async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
            conn.row_factory = aiosqlite.Row

            # Trade counts
            cur = await conn.execute("""
                SELECT direction, COUNT(*) as count, ROUND(SUM(sol_amount), 4) as total_sol,
                       COUNT(DISTINCT token_address) as tokens
                FROM wallet_shadow_trades WHERE wallet_address = ?
                GROUP BY direction
            """, (wallet_address,))
            directions = {r["direction"]: dict(r) for r in await cur.fetchall()}

            # Time range
            cur = await conn.execute("""
                SELECT MIN(timestamp) as first_trade, MAX(timestamp) as last_trade,
                       COUNT(*) as total_trades, COUNT(DISTINCT token_address) as unique_tokens
                FROM wallet_shadow_trades WHERE wallet_address = ?
            """, (wallet_address,))
            overview = dict(await cur.fetchone())

            # Recent trades
            cur = await conn.execute("""
                SELECT token_name, token_address, direction, sol_amount, token_amount,
                       timestamp, tip_type, entry_seconds_after_creation
                FROM wallet_shadow_trades WHERE wallet_address = ?
                ORDER BY timestamp_unix DESC LIMIT 20
            """, (wallet_address,))
            recent = [dict(r) for r in await cur.fetchall()]

            return {
                "wallet_address": wallet_address,
                "overview": overview,
                "by_direction": directions,
                "recent_trades": recent,
            }
    except Exception as e:
        return {"error": str(e)}
