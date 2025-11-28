"""
Ingest Pipeline Router

Provides REST endpoints for the tiered token ingestion pipeline:
- GET/POST /api/ingest/settings - View/update thresholds, budgets, flags
- GET /api/ingest/queue - List queue entries by tier/status
- POST /api/ingest/run-tier0 - Trigger Tier-0 ingestion (DexScreener, free)
- POST /api/ingest/run-tier1 - Trigger Tier-1 enrichment (Helius, budgeted)
- POST /api/ingest/promote - Promote tokens to full analysis
- POST /api/ingest/discard - Mark tokens as discarded
"""

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from meridinate import analyzed_tokens_db as db
from meridinate.analyzed_tokens_db import get_db_connection
from meridinate.observability.structured_logger import log_info
from meridinate.settings import CURRENT_INGEST_SETTINGS, save_ingest_settings
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
    if any(k in updates for k in ["ingest_enabled", "enrich_enabled", "hot_refresh_enabled"]):
        from meridinate.scheduler import update_ingest_scheduler

        update_ingest_scheduler()

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
            last_tier0_run_at=CURRENT_INGEST_SETTINGS.get("last_tier0_run_at"),
            last_tier1_run_at=CURRENT_INGEST_SETTINGS.get("last_tier1_run_at"),
            last_tier1_credits_used=CURRENT_INGEST_SETTINGS.get("last_tier1_credits_used", 0),
            last_hot_refresh_at=CURRENT_INGEST_SETTINGS.get("last_hot_refresh_at"),
        )


# ============================================================================
# Trigger Endpoints
# ============================================================================


class Tier0RunRequest(BaseModel):
    """Optional overrides for Tier-0 ingestion"""

    max_tokens: Optional[int] = Field(None, ge=1, le=500, description="Override max tokens to fetch")
    mc_min: Optional[float] = Field(None, ge=0, description="Override minimum market cap")
    volume_min: Optional[float] = Field(None, ge=0, description="Override minimum volume")
    liquidity_min: Optional[float] = Field(None, ge=0, description="Override minimum liquidity")
    age_max_hours: Optional[float] = Field(None, ge=1, description="Override maximum age in hours")


class Tier1RunRequest(BaseModel):
    """Optional overrides for Tier-1 enrichment"""

    batch_size: Optional[int] = Field(None, ge=1, le=100, description="Override batch size")
    credit_budget: Optional[int] = Field(None, ge=1, le=1000, description="Override credit budget")
    mc_min: Optional[float] = Field(None, ge=0, description="Override minimum market cap")
    volume_min: Optional[float] = Field(None, ge=0, description="Override minimum volume")
    liquidity_min: Optional[float] = Field(None, ge=0, description="Override minimum liquidity")
    age_max_hours: Optional[float] = Field(None, ge=1, description="Override maximum age in hours")


class PromoteRequest(BaseModel):
    """Request to promote tokens to full analysis"""

    token_addresses: List[str] = Field(..., min_length=1, description="Token addresses to promote")
    register_webhooks: bool = Field(True, description="Register SWAB webhooks on promotion")


class DiscardRequest(BaseModel):
    """Request to discard tokens from the queue"""

    token_addresses: List[str] = Field(..., min_length=1, description="Token addresses to discard")
    reason: str = Field(default="manual", description="Reason for discarding")


@router.post("/run-tier0")
async def run_tier0(payload: Optional[Tier0RunRequest] = None):
    """
    Trigger Tier-0 ingestion (DexScreener, free).

    Fetches recently migrated/listed tokens from DexScreener, dedupes against
    existing tokens, and stores snapshots in the ingest queue.

    Args:
        payload: Optional overrides for ingestion parameters

    Returns:
        Ingestion results including tokens fetched, new, updated, skipped
    """
    from meridinate.tasks.ingest_tasks import run_tier0_ingestion

    # Check if ingestion is enabled (can be overridden by explicit call)
    if not CURRENT_INGEST_SETTINGS.get("ingest_enabled"):
        log_info("[Tier-0] Manual trigger (ingest_enabled=false)")

    params = payload.model_dump(exclude_unset=True) if payload else {}

    log_info("Tier-0 ingestion triggered", params=params, event_type="ingest_trigger", tier="tier0")

    result = await run_tier0_ingestion(**params)

    return {"status": "success", "result": result}


@router.post("/run-tier1")
async def run_tier1(payload: Optional[Tier1RunRequest] = None):
    """
    Trigger Tier-1 enrichment (Helius, budgeted).

    Selects tokens from queue that pass thresholds, enriches with Helius data
    (metadata + top holders), respects credit budget.

    Args:
        payload: Optional overrides for enrichment parameters

    Returns:
        Enrichment results including tokens processed, enriched, failed, credits used
    """
    from meridinate.tasks.ingest_tasks import run_tier1_enrichment

    # Check if enrichment is enabled (can be overridden by explicit call)
    if not CURRENT_INGEST_SETTINGS.get("enrich_enabled"):
        log_info("[Tier-1] Manual trigger (enrich_enabled=false)")

    params = payload.model_dump(exclude_unset=True) if payload else {}

    log_info("Tier-1 enrichment triggered", params=params, event_type="ingest_trigger", tier="tier1")

    result = await run_tier1_enrichment(**params)

    return {"status": "success", "result": result}


@router.post("/promote")
async def promote_tokens(payload: PromoteRequest):
    """
    Promote tokens from enriched tier to full analysis.

    Marks tokens for full analysis (MTEW detection, SWAB tracking).
    Only tokens in 'enriched' tier can be promoted.
    Optionally registers SWAB webhooks for tracking (default: True).

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
    register_webhooks: bool = Field(True, description="Register SWAB webhooks on promotion")


@router.post("/auto-promote")
async def trigger_auto_promote(payload: Optional[AutoPromoteRequest] = None):
    """
    Manually trigger auto-promote for enriched tokens.

    Promotes enriched tokens to full analysis (tier='analyzed') and
    optionally registers SWAB webhooks for tracking.

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

    return {"status": "success", "result": result}
