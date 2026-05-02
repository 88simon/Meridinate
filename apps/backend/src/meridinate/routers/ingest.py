"""
Ingest Pipeline Router

Provides REST endpoints for the Discovery → Queue → Analysis pipeline:
- GET/POST /api/ingest/settings - View/update thresholds, budgets, flags
- GET /api/ingest/queue - List queue entries by tier/status
- POST /api/ingest/run-discovery - Trigger Discovery (DexScreener, free)
- POST /api/ingest/promote - Promote tokens to full analysis
- POST /api/ingest/discard - Mark tokens as discarded

Legacy endpoints (backward compatibility):
- POST /api/ingest/run-tier0 - Alias for run-discovery
- POST /api/ingest/run-tier1 - Deprecated (no-op)
"""

import asyncio
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, Field

from meridinate import analyzed_tokens_db as db
from meridinate.analyzed_tokens_db import get_db_connection
from meridinate.observability.structured_logger import log_info
from meridinate.settings import CURRENT_INGEST_SETTINGS, save_ingest_settings, API_BASE_URL
from meridinate.utils.models import (
    IngestQueueEntry,
    IngestQueueResponse,
    IngestQueueStats,
    IngestSettings,
    UpdateIngestSettingsRequest,
)

router = APIRouter(prefix="/api/ingest", tags=["Ingest"])


# ============================================================================
# Settings Endpoints
# ============================================================================


@router.get("/settings", response_model=IngestSettings)
async def get_ingest_settings():
    """
    Get current ingest pipeline settings

    Returns:
        IngestSettings with thresholds, batch sizes, credit budget, and flags
    """
    return CURRENT_INGEST_SETTINGS.copy()


@router.post("/settings")
async def update_ingest_settings(payload: UpdateIngestSettingsRequest):
    """
    Update ingest pipeline settings

    Args:
        payload: Settings to update (partial update supported)

    Returns:
        Updated settings
    """
    updates = {k: v for k, v in payload.model_dump(exclude_unset=True).items()}
    if not updates:
        return {"status": "noop", "settings": CURRENT_INGEST_SETTINGS}

    # Update in-memory settings
    CURRENT_INGEST_SETTINGS.update(updates)

    # Persist to file
    if not save_ingest_settings(CURRENT_INGEST_SETTINGS):
        raise HTTPException(status_code=500, detail="Failed to save ingest settings")

    # Log settings update
    log_info(
        "Ingest settings updated",
        updates=updates,
        event_type="settings_update",
        settings_type="ingest",
    )

    # Update scheduler if feature flags changed
    scheduler_flags = ["discovery_enabled", "auto_promote_enabled", "slow_lane_enabled"]
    if any(k in updates for k in scheduler_flags):
        from meridinate.scheduler import update_ingest_scheduler
        update_ingest_scheduler()

    # Update scan interval if it changed
    interval_flags = ["discovery_interval_minutes"]
    if any(k in updates for k in interval_flags):
        from meridinate.scheduler import update_scan_interval
        update_scan_interval()

    return {"status": "success", "settings": CURRENT_INGEST_SETTINGS.copy()}


# ============================================================================
# Queue Endpoints
# ============================================================================


@router.get("/queue", response_model=IngestQueueResponse)
async def get_ingest_queue(
    tier: Optional[str] = Query(None, description="Filter by tier: ingested, enriched, analyzed, discarded"),
    status: Optional[str] = Query(None, description="Filter by status: pending, completed, failed"),
    limit: int = Query(100, ge=1, le=500, description="Maximum entries to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
):
    """
    List tokens in the ingest queue

    Args:
        tier: Optional filter by tier (ingested, enriched, analyzed, discarded)
        status: Optional filter by status (pending, completed, failed)
        limit: Maximum number of entries to return (default 100)
        offset: Pagination offset (default 0)

    Returns:
        IngestQueueResponse with total count, counts by tier/status, and entries
    """
    def _query():
        return _get_ingest_queue_sync(tier, status, limit, offset)

    return await asyncio.to_thread(_query)


def _get_ingest_queue_sync(tier, status, limit, offset):
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Build query with optional filters
        where_clauses = []
        params = []

        if tier:
            where_clauses.append("tier = ?")
            params.append(tier)

        if status:
            where_clauses.append("status = ?")
            params.append(status)

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        # Get total count (with filters)
        cursor.execute(f"SELECT COUNT(*) FROM token_ingest_queue {where_sql}", params)
        total = cursor.fetchone()[0]

        # Get counts by tier
        cursor.execute(
            """
            SELECT tier, COUNT(*) as count
            FROM token_ingest_queue
            GROUP BY tier
        """
        )
        by_tier = {row["tier"]: row["count"] for row in cursor.fetchall()}

        # Get counts by status
        cursor.execute(
            """
            SELECT status, COUNT(*) as count
            FROM token_ingest_queue
            GROUP BY status
        """
        )
        by_status = {row["status"]: row["count"] for row in cursor.fetchall()}

        # Get entries with pagination
        cursor.execute(
            f"""
            SELECT
                token_address, token_name, token_symbol,
                first_seen_at, source, tier, status,
                ingested_at, enriched_at, analyzed_at, discarded_at,
                last_mc_usd, last_volume_usd, last_liquidity, age_hours,
                ingest_notes, last_error
            FROM token_ingest_queue
            {where_sql}
            ORDER BY first_seen_at DESC
            LIMIT ? OFFSET ?
        """,
            params + [limit, offset],
        )

        entries = [
            IngestQueueEntry(
                token_address=row["token_address"],
                token_name=row["token_name"],
                token_symbol=row["token_symbol"],
                first_seen_at=row["first_seen_at"],
                source=row["source"],
                tier=row["tier"],
                status=row["status"],
                ingested_at=row["ingested_at"],
                enriched_at=row["enriched_at"],
                analyzed_at=row["analyzed_at"],
                discarded_at=row["discarded_at"],
                last_mc_usd=row["last_mc_usd"],
                last_volume_usd=row["last_volume_usd"],
                last_liquidity=row["last_liquidity"],
                age_hours=row["age_hours"],
                ingest_notes=row["ingest_notes"],
                last_error=row["last_error"],
            )
            for row in cursor.fetchall()
        ]

        return IngestQueueResponse(
            total=total,
            by_tier=by_tier,
            by_status=by_status,
            entries=entries,
        )


@router.get("/queue/stats", response_model=IngestQueueStats)
async def get_ingest_queue_stats():
    """
    Get statistics about the ingest queue

    Returns:
        IngestQueueStats with counts by tier/status and last run info
    """
    return await asyncio.to_thread(_get_ingest_queue_stats_sync)


def _get_ingest_queue_stats_sync():
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Get total count
        cursor.execute("SELECT COUNT(*) FROM token_ingest_queue")
        total = cursor.fetchone()[0]

        # Get counts by tier
        cursor.execute(
            """
            SELECT tier, COUNT(*) as count
            FROM token_ingest_queue
            GROUP BY tier
        """
        )
        by_tier = {row["tier"]: row["count"] for row in cursor.fetchall()}

        # Get counts by status
        cursor.execute(
            """
            SELECT status, COUNT(*) as count
            FROM token_ingest_queue
            GROUP BY status
        """
        )
        by_status = {row["status"]: row["count"] for row in cursor.fetchall()}

        return IngestQueueStats(
            total=total,
            by_tier=by_tier,
            by_status=by_status,
            # New discovery-based naming
            last_discovery_run_at=CURRENT_INGEST_SETTINGS.get("last_discovery_run_at"),
            last_refresh_run_at=CURRENT_INGEST_SETTINGS.get("last_refresh_run_at"),
            # Legacy fields (backward compatibility)
            last_tier0_run_at=CURRENT_INGEST_SETTINGS.get("last_tier0_run_at") or CURRENT_INGEST_SETTINGS.get("last_discovery_run_at"),
            last_tier1_run_at=CURRENT_INGEST_SETTINGS.get("last_tier1_run_at"),
            last_tier1_credits_used=CURRENT_INGEST_SETTINGS.get("last_tier1_credits_used", 0),
            last_hot_refresh_at=CURRENT_INGEST_SETTINGS.get("last_hot_refresh_at") or CURRENT_INGEST_SETTINGS.get("last_refresh_run_at"),
        )


# ============================================================================
# Trigger Endpoints
# ============================================================================


class DiscoveryRunRequest(BaseModel):
    """Optional overrides for Discovery ingestion"""

    max_tokens: Optional[int] = Field(None, ge=1, le=500, description="Override max tokens to fetch")
    mc_min: Optional[float] = Field(None, ge=0, description="Override minimum market cap")
    volume_min: Optional[float] = Field(None, ge=0, description="Override minimum volume")
    liquidity_min: Optional[float] = Field(None, ge=0, description="Override minimum liquidity")
    age_max_hours: Optional[float] = Field(None, ge=1, description="Override maximum age in hours")


# Legacy alias for backward compatibility
Tier0RunRequest = DiscoveryRunRequest


class PromoteRequest(BaseModel):
    """Request to promote tokens to full analysis"""

    token_addresses: List[str] = Field(..., min_length=1, description="Token addresses to promote")
    register_webhooks: bool = Field(True, description="Register position tracking webhooks on promotion")


class DiscardRequest(BaseModel):
    """Request to discard tokens from the queue"""

    token_addresses: List[str] = Field(..., min_length=1, description="Token addresses to discard")
    reason: str = Field(default="manual", description="Reason for discarding")


@router.post("/run-mc-tracker", status_code=202)
async def run_mc_tracker_endpoint():
    """Trigger MC tracker in a background thread. Returns immediately."""
    from concurrent.futures import ThreadPoolExecutor

    def _run():
        from meridinate.tasks.mc_tracker import run_mc_tracker
        try:
            result = run_mc_tracker()
            log_info(f"[MC Tracker] Manual run complete: {result.get('tokens_updated', 0)} updated")
        except Exception as e:
            log_error(f"[MC Tracker] Manual run failed: {e}")

    ThreadPoolExecutor(max_workers=1).submit(_run)
    return {"status": "accepted", "message": "MC tracker running in background"}


@router.post("/run-scan", status_code=202)
async def run_scan():
    """
    Trigger Auto-Scan in a background thread. Returns immediately with 202.
    The scan runs completely off the event loop so the API stays responsive.
    """
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    _scan_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="auto-scan")

    def _run_scan_sync():
        """Run the entire scan synchronously in a separate thread."""
        from meridinate.tasks.ingest_tasks import run_auto_scan_sync
        try:
            result = run_auto_scan_sync()
            log_info(
                f"[Auto-Scan] Background scan complete: {result.get('tokens_scanned', 0)} scanned, "
                f"{result.get('credits_used', 0)} credits"
            )
            # Send WebSocket notification via HTTP loopback (safe from thread)
            try:
                import requests as req
                req.post(f"{API_BASE_URL}/notify/analysis_complete", json={
                    "job_id": "auto-scan",
                    "token_name": f"Auto-Scan ({result.get('tokens_scanned', 0)} tokens)",
                    "token_symbol": "SCAN",
                    "acronym": "SCAN",
                    "wallets_found": result.get("tokens_scanned", 0),
                    "token_id": 0,
                }, timeout=2)
            except Exception:
                pass
        except Exception as e:
            log_error(f"[Auto-Scan] Background scan failed: {e}")

    _scan_executor.submit(_run_scan_sync)

    log_info("[Auto-Scan] Manual trigger — running in background thread")
    return {"status": "accepted", "message": "Scan started in background. Results will appear in Recent Scans."}


@router.get("/scan-progress")
async def get_scan_progress():
    """
    Get current auto-scan progress (lightweight, no DB query).
    Auto-clears stuck state if the heartbeat is stale (>10 min) so the UI
    never lies about a scan that's actually dead.
    """
    from meridinate.tasks.ingest_tasks import get_scan_progress
    return get_scan_progress()


@router.post("/scan-progress/reset")
async def reset_scan_progress_endpoint():
    """
    Manually clear stuck scan-progress state without restarting the backend.
    The orphaned worker thread (if any) keeps running in background but the
    UI immediately reflects the reset, and the scheduler can fire a new scan.
    """
    from meridinate.tasks.ingest_tasks import reset_scan_progress
    return reset_scan_progress(reason="manual_endpoint")


@router.post("/run-discovery")
async def run_discovery(payload: Optional[DiscoveryRunRequest] = None):
    """
    Trigger Discovery ingestion (DexScreener, free).

    Fetches recently migrated/listed tokens from DexScreener, dedupes against
    existing tokens, and stores snapshots in the ingest queue.

    Args:
        payload: Optional overrides for ingestion parameters

    Returns:
        Ingestion results including tokens fetched, new, updated, skipped
    """
    from meridinate.tasks.ingest_tasks import run_tier0_ingestion

    # Check if discovery is enabled (can be overridden by explicit call)
    discovery_enabled = CURRENT_INGEST_SETTINGS.get("discovery_enabled")
    if not discovery_enabled:
        log_info("[Discovery] Manual trigger (discovery_enabled=false)")

    params = payload.model_dump(exclude_unset=True) if payload else {}

    log_info("Discovery ingestion triggered", params=params, event_type="ingest_trigger", tier="discovery")

    result = await run_tier0_ingestion(**params)

    # Log high-level operation for persistent history
    from meridinate.credit_tracker import get_credit_tracker
    get_credit_tracker().record_operation(
        operation="discovery_ingestion",
        label="Discovery Ingestion",
        credits=0,  # DexScreener is free
        call_count=result.get("tokens_fetched", 0),
        context={
            "tokens_new": result.get("tokens_new", 0),
            "tokens_updated": result.get("tokens_updated", 0),
        }
    )

    return {"status": "success", "result": result}


@router.post("/run-tier0")
async def run_tier0(payload: Optional[Tier0RunRequest] = None):
    """
    Legacy endpoint: Alias for /run-discovery.

    Trigger Discovery ingestion (DexScreener, free).

    Args:
        payload: Optional overrides for ingestion parameters

    Returns:
        Ingestion results including tokens fetched, new, updated, skipped
    """
    return await run_discovery(payload)



@router.post("/promote")
async def promote_tokens(payload: PromoteRequest):
    """
    Promote tokens from Discovery Queue to full analysis.

    Marks tokens for full analysis (recurring wallet detection, position tracking).
    Tokens in 'ingested' or 'enriched' tier can be promoted.
    Optionally registers position tracking webhooks (default: True).

    Args:
        payload: Token addresses to promote and webhook options

    Returns:
        Promotion results including tokens promoted, failed, and webhooks registered
    """
    from meridinate.tasks.ingest_tasks import promote_tokens_to_analysis

    log_info(
        "Token promotion triggered",
        token_count=len(payload.token_addresses),
        register_webhooks=payload.register_webhooks,
        event_type="ingest_promote",
    )

    result = await promote_tokens_to_analysis(
        payload.token_addresses,
        register_webhooks=payload.register_webhooks,
    )

    # Log high-level operation for persistent history
    from meridinate.credit_tracker import get_credit_tracker
    get_credit_tracker().record_operation(
        operation="token_promotion",
        label="Token Promotion",
        credits=result.get("credits_used", 0),
        call_count=result.get("tokens_promoted", 0),
        context={
            "webhooks_registered": result.get("webhooks_registered", 0),
            "tokens_failed": result.get("tokens_failed", 0),
        }
    )

    return {"status": "success", "result": result}


@router.post("/discard")
async def discard_tokens(payload: DiscardRequest):
    """
    Mark tokens in the queue as discarded.

    Discarded tokens are kept for historical reference but excluded from
    future processing.

    Args:
        payload: Token addresses to discard and reason

    Returns:
        Number of tokens discarded
    """
    count = db.discard_ingest_queue_tokens(payload.token_addresses, payload.reason)

    log_info(
        "Tokens discarded",
        token_count=count,
        reason=payload.reason,
        event_type="ingest_discard",
    )

    return {"status": "success", "discarded": count}


class HotRefreshRequest(BaseModel):
    """Optional overrides for hot token refresh"""

    max_age_hours: Optional[float] = Field(None, ge=1, le=168, description="Override max age for hot tokens (hours)")
    max_tokens: Optional[int] = Field(None, ge=1, le=500, description="Override max tokens to refresh")


@router.post("/refresh-hot")
async def refresh_hot_tokens(payload: Optional[HotRefreshRequest] = None):
    """
    Trigger MC/volume refresh for hot tokens (DexScreener, free).

    Refreshes snapshot data (MC, volume, liquidity, age) for recently
    ingested/enriched tokens. This keeps metrics fresh for promotion decisions.

    Args:
        payload: Optional overrides for refresh parameters

    Returns:
        Refresh results including tokens checked, updated, failed
    """
    from meridinate.tasks.ingest_tasks import run_hot_token_refresh

    params = payload.model_dump(exclude_unset=True) if payload else {}

    log_info("Hot token refresh triggered", params=params, event_type="ingest_trigger", tier="hot_refresh")

    result = await run_hot_token_refresh(**params)

    return {"status": "success", "result": result}


class AutoPromoteRequest(BaseModel):
    """Optional overrides for auto-promote"""

    max_promotions: Optional[int] = Field(None, ge=1, le=50, description="Override max promotions")
    register_webhooks: bool = Field(True, description="Register position tracking webhooks on promotion")


@router.post("/auto-promote")
async def trigger_auto_promote(payload: Optional[AutoPromoteRequest] = None):
    """
    Manually trigger auto-promote for enriched tokens.

    Promotes enriched tokens to full analysis (tier='analyzed') and
    optionally registers position tracking webhooks.

    Note: This is the same logic that runs automatically after Tier-1
    enrichment when auto_promote_enabled is True.

    Args:
        payload: Optional overrides for auto-promote parameters

    Returns:
        Auto-promote results including tokens promoted and webhooks registered
    """
    from meridinate.tasks.ingest_tasks import run_auto_promote

    params = payload.model_dump(exclude_unset=True) if payload else {}

    log_info("Auto-promote triggered", params=params, event_type="ingest_trigger", tier="auto_promote")

    result = await run_auto_promote(**params)

    # Log high-level operation for persistent history
    from meridinate.credit_tracker import get_credit_tracker
    get_credit_tracker().record_operation(
        operation="auto_promotion",
        label="Auto Promotion",
        credits=result.get("credits_used", 0),
        call_count=result.get("tokens_promoted", 0),
        context={
            "webhooks_registered": result.get("webhooks_registered", 0),
            "trigger": "manual",
        }
    )

    return {"status": "success", "result": result}


@router.post("/control-cohort")
async def select_control_cohort():
    """
    Select random low-score tokens for control cohort tracking.

    This helps validate the scoring system by tracking tokens that
    would normally be culled to see if they perform well.

    The number of tokens selected is controlled by the
    control_cohort_daily_quota setting.

    Returns:
        Control cohort selection results
    """
    from meridinate.tasks.performance_scorer import run_control_cohort_selection

    log_info("Control cohort selection triggered", event_type="ingest_trigger", tier="control_cohort")

    result = await run_control_cohort_selection()

    return {"status": "success", "result": result}


@router.get("/control-cohort")
async def get_control_cohort(limit: int = 50):
    """
    Get tokens marked as control cohort.

    Args:
        limit: Maximum number of tokens to return

    Returns:
        List of control cohort tokens
    """
    from meridinate import analyzed_tokens_db as db

    tokens = db.get_control_cohort_tokens(limit=limit)
    return {"status": "success", "count": len(tokens), "tokens": tokens}


# ============================================================================
# Real-Time Token Detection (Helius Enhanced WebSocket)
# ============================================================================

@router.post("/realtime/start")
async def start_realtime_listener():
    """Start the real-time PumpFun token detection WebSocket."""
    from meridinate.services.realtime_listener import get_realtime_listener
    listener = get_realtime_listener()
    if listener.is_running:
        return {"status": "already_running", **listener.stats}
    await listener.start()
    return {"status": "started", **listener.stats}


@router.post("/realtime/stop")
async def stop_realtime_listener():
    """Stop the real-time token detection WebSocket."""
    from meridinate.services.realtime_listener import get_realtime_listener
    listener = get_realtime_listener()
    if not listener.is_running:
        return {"status": "already_stopped"}
    await listener.stop()
    return {"status": "stopped"}


@router.get("/realtime/status")
async def get_realtime_status():
    """Get the status and stats of the real-time listener."""
    from meridinate.services.realtime_listener import get_realtime_listener
    listener = get_realtime_listener()
    return {
        "running": listener.is_running,
        **listener.stats,
    }


@router.get("/realtime/feed")
async def get_realtime_feed(limit: int = Query(50, ge=1, le=100)):
    """
    Get the real-time token detection feed.
    Returns recently detected tokens with conviction scores, newest first.
    """
    from meridinate.services.realtime_listener import get_realtime_listener
    listener = get_realtime_listener()
    feed = listener.get_feed(limit=limit)
    return {
        "running": listener.is_running,
        "total_in_feed": len(feed),
        "stats": listener.stats,
        "tokens": feed,
    }


@router.get("/followup/status")
async def get_followup_status():
    """Get the status and tracked tokens of the follow-up tracker."""
    from meridinate.services.followup_tracker import get_followup_tracker
    tracker = get_followup_tracker()
    return {
        "running": tracker.is_running,
        **tracker.stats,
        "tokens": tracker.get_tracked_tokens(limit=50),
    }


@router.get("/lifecycle/{token_address}")
async def get_token_lifecycle(token_address: str):
    """
    Get complete lifecycle data for a token — stitches birth (RTTF),
    trajectory (follow-up), analysis (auto-scan), and verdict into one record.
    """
    import aiosqlite
    from meridinate import settings as app_settings

    lifecycle = {
        "token_address": token_address,
        "birth": None,
        "trajectory": None,
        "analysis": None,
        "verdict": None,
        "accuracy": None,
    }

    async with aiosqlite.connect(app_settings.DATABASE_FILE) as conn:
        conn.row_factory = aiosqlite.Row

        # Birth data (from webhook_detections)
        cursor = await conn.execute(
            "SELECT * FROM webhook_detections WHERE token_address = ?",
            (token_address,)
        )
        birth_row = await cursor.fetchone()
        if birth_row:
            birth = dict(birth_row)
            # Parse trajectory from conviction_vs_outcome
            trajectory_data = None
            if birth.get("conviction_vs_outcome"):
                try:
                    import json
                    trajectory_data = json.loads(birth["conviction_vs_outcome"])
                except Exception:
                    pass
            lifecycle["birth"] = {
                "detected_at": birth.get("detected_at"),
                "conviction_score": birth.get("conviction_score"),
                "deployer_score": birth.get("deployer_score"),
                "safety_score": birth.get("safety_score"),
                "social_proof_score": birth.get("social_proof_score"),
                "status": birth.get("status"),
                "deployer_address": birth.get("deployer_address"),
                "deployer_token_count": birth.get("deployer_token_count"),
                "deployer_win_rate": birth.get("deployer_win_rate"),
                "token_name": birth.get("token_name"),
                "token_symbol": birth.get("token_symbol"),
                "initial_sol": birth.get("initial_sol"),
            }
            lifecycle["trajectory"] = trajectory_data

        # Analysis data (from analyzed_tokens)
        cursor = await conn.execute(
            "SELECT * FROM analyzed_tokens WHERE token_address = ? AND (deleted_at IS NULL OR deleted_at = '')",
            (token_address,)
        )
        analysis_row = await cursor.fetchone()
        if analysis_row:
            analysis = dict(analysis_row)
            token_id = analysis["id"]

            # Get verdict
            cursor = await conn.execute(
                "SELECT tag FROM token_tags WHERE token_id = ? AND tag IN ('verified-win', 'verified-loss') LIMIT 1",
                (token_id,)
            )
            verdict_row = await cursor.fetchone()
            verdict = verdict_row[0] if verdict_row else None

            # Get win multiplier
            cursor = await conn.execute(
                "SELECT tag FROM token_tags WHERE token_id = ? AND tag LIKE 'win:%' LIMIT 1",
                (token_id,)
            )
            mult_row = await cursor.fetchone()
            multiplier = mult_row[0] if mult_row else None

            lifecycle["analysis"] = {
                "token_id": token_id,
                "analysis_timestamp": analysis.get("analysis_timestamp"),
                "market_cap_usd": analysis.get("market_cap_usd"),
                "market_cap_usd_current": analysis.get("market_cap_usd_current"),
                "market_cap_ath": analysis.get("market_cap_ath"),
                "wallets_found": analysis.get("wallets_found"),
                "score_momentum": analysis.get("score_momentum"),
                "score_smart_money": analysis.get("score_smart_money"),
                "score_risk": analysis.get("score_risk"),
                "score_composite": analysis.get("score_composite"),
                "holder_top1_pct": analysis.get("holder_top1_pct"),
                "mc_volatility": analysis.get("mc_volatility"),
                "deployer_is_top_holder": analysis.get("deployer_is_top_holder"),
                "webhook_detected_at": analysis.get("webhook_detected_at"),
                "webhook_conviction_score": analysis.get("webhook_conviction_score"),
                "time_to_migration_minutes": analysis.get("time_to_migration_minutes"),
            }

            lifecycle["verdict"] = {
                "verdict": verdict,
                "multiplier": multiplier,
                "ath_multiple": (analysis["market_cap_ath"] / analysis["market_cap_usd"])
                    if analysis.get("market_cap_ath") and analysis.get("market_cap_usd") and analysis["market_cap_usd"] > 0
                    else None,
            }

            # Accuracy check
            if lifecycle["birth"] and verdict:
                birth_status = lifecycle["birth"]["status"]
                was_correct = (
                    (birth_status == "high_conviction" and verdict == "verified-win") or
                    (birth_status == "rejected" and verdict == "verified-loss") or
                    (birth_status == "weak" and verdict == "verified-loss")
                )
                lifecycle["accuracy"] = {
                    "birth_prediction": birth_status,
                    "actual_outcome": verdict,
                    "prediction_correct": was_correct,
                }

    return lifecycle


@router.get("/realtime/history")
async def get_realtime_history(
    limit: int = Query(100, ge=1, le=500),
    status: Optional[str] = Query(None, description="Filter by status: high_conviction, watching, weak, rejected"),
    min_score: Optional[int] = Query(None, ge=0, le=100),
    max_score: Optional[int] = Query(None, ge=0, le=100),
):
    """
    Get persisted webhook detection history from database.
    This is the audit view — shows everything that was saved, with filters.
    """
    import aiosqlite
    from meridinate import settings as app_settings

    async with aiosqlite.connect(app_settings.DATABASE_FILE) as conn:
        conn.row_factory = aiosqlite.Row

        query = "SELECT * FROM webhook_detections WHERE 1=1"
        params = []

        if status:
            query += " AND status = ?"
            params.append(status)
        if min_score is not None:
            query += " AND conviction_score >= ?"
            params.append(min_score)
        if max_score is not None:
            query += " AND conviction_score <= ?"
            params.append(max_score)

        query += " ORDER BY detected_at DESC LIMIT ?"
        params.append(limit)

        cursor = await conn.execute(query, params)
        rows = [dict(r) for r in await cursor.fetchall()]

        # Get totals by status
        cursor = await conn.execute(
            "SELECT status, COUNT(*) as cnt FROM webhook_detections GROUP BY status"
        )
        status_counts = {r["status"]: r["cnt"] for r in await cursor.fetchall()}

        # Get total
        cursor = await conn.execute("SELECT COUNT(*) FROM webhook_detections")
        total = (await cursor.fetchone())[0]

        # Cross-system stats
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM webhook_detections WHERE auto_scan_token_id IS NOT NULL"
        )
        linked = (await cursor.fetchone())[0]

    return {
        "total": total,
        "showing": len(rows),
        "status_counts": status_counts,
        "linked_to_auto_scan": linked,
        "detections": rows,
    }


@router.get("/realtime/accuracy")
async def get_conviction_accuracy():
    """
    Conviction accuracy report card.
    Shows how well our birth conviction scores predicted actual outcomes.
    """
    import aiosqlite
    from meridinate import settings as app_settings

    async with aiosqlite.connect(app_settings.DATABASE_FILE) as conn:
        conn.row_factory = aiosqlite.Row

        # Get all webhook detections that have been linked to analyzed tokens with verdicts
        cursor = await conn.execute("""
            SELECT wd.status as birth_status, wd.conviction_score,
                   tt.tag as verdict, wd.token_name
            FROM webhook_detections wd
            JOIN token_tags tt ON tt.token_id = wd.auto_scan_token_id
                AND tt.tag IN ('verified-win', 'verified-loss')
            WHERE wd.auto_scan_token_id IS NOT NULL
        """)
        rows = await cursor.fetchall()

        # Compute accuracy by birth status
        by_status = {}
        for row in rows:
            status = row["birth_status"] or "unknown"
            verdict = row["verdict"]
            if status not in by_status:
                by_status[status] = {"total": 0, "wins": 0, "losses": 0}
            by_status[status]["total"] += 1
            if verdict == "verified-win":
                by_status[status]["wins"] += 1
            else:
                by_status[status]["losses"] += 1

        # Compute accuracy metrics
        accuracy = {}
        for status, counts in by_status.items():
            total = counts["total"]
            wins = counts["wins"]
            if status in ("high_conviction",):
                accuracy[status] = {
                    **counts,
                    "accuracy": round(wins / total * 100) if total > 0 else None,
                    "description": "% that actually won",
                }
            elif status in ("rejected", "weak"):
                accuracy[status] = {
                    **counts,
                    "accuracy": round(counts["losses"] / total * 100) if total > 0 else None,
                    "description": "% correctly identified as losses",
                }
            else:
                accuracy[status] = {
                    **counts,
                    "accuracy": round(wins / total * 100) if total > 0 else None,
                    "description": "% that won",
                }

        # Overall stats
        total_with_verdict = len(rows)
        correct = sum(1 for r in rows if
            (r["birth_status"] == "high_conviction" and r["verdict"] == "verified-win") or
            (r["birth_status"] in ("rejected", "weak") and r["verdict"] == "verified-loss")
        )

    return {
        "total_with_verdict": total_with_verdict,
        "overall_accuracy": round(correct / total_with_verdict * 100) if total_with_verdict > 0 else None,
        "by_status": accuracy,
        "message": "Accuracy improves as more tokens complete their lifecycle (detection → verdict)."
                   f" Currently {total_with_verdict} tokens have both a birth prediction and a verdict."
    }


@router.delete("/realtime/history/{token_address}")
async def delete_detection(token_address: str):
    """Delete a specific webhook detection (for correcting bad data)."""
    import aiosqlite
    from meridinate import settings as app_settings

    async with aiosqlite.connect(app_settings.DATABASE_FILE) as conn:
        cursor = await conn.execute(
            "DELETE FROM webhook_detections WHERE token_address = ?",
            (token_address,)
        )
        await conn.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Detection not found")

    return {"status": "deleted", "token_address": token_address}
