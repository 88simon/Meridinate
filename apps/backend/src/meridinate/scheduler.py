"""
Scheduler Module
================
Handles background job scheduling for:
- SWAB position checking
- Ingest pipeline (Tier-0 ingestion, Tier-1 enrichment)

Uses APScheduler with asyncio support.
"""

import asyncio
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from meridinate import analyzed_tokens_db as db
from meridinate.observability import log_error, log_info

# Global scheduler instance
_scheduler: Optional[AsyncIOScheduler] = None
_check_job_id = "swab_position_check"
_tier0_job_id = "ingest_tier0"
_tier1_job_id = "ingest_tier1"
_hot_refresh_job_id = "ingest_hot_refresh"


def get_scheduler() -> AsyncIOScheduler:
    """Get or create the global scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler()
    return _scheduler


async def swab_position_check_job():
    """
    Scheduled job to check SWAB positions.

    Respects SWAB settings for:
    - auto_check_enabled
    - stale_threshold_minutes
    - daily_credit_budget
    """
    from meridinate.tasks.position_tracker import check_mtew_positions

    try:
        # Get current SWAB settings
        settings = db.get_swab_settings()

        # Check if auto-check is enabled
        if not settings["auto_check_enabled"]:
            log_info("SWAB auto-check disabled, skipping scheduled check")
            return

        # Check daily credit budget
        credits_remaining = settings["daily_credit_budget"] - settings["credits_used_today"]
        if credits_remaining <= 0:
            log_info("SWAB daily credit budget exhausted, skipping scheduled check")
            return

        # Calculate max positions to check based on remaining budget
        # Each position costs ~10 credits
        max_positions = min(50, credits_remaining // 10)
        if max_positions <= 0:
            log_info("SWAB insufficient credits for position check")
            return

        log_info(
            f"SWAB scheduled check starting: max_positions={max_positions}, "
            f"credits_remaining={credits_remaining}"
        )

        # Run the position check
        result = await check_mtew_positions(
            older_than_minutes=settings["stale_threshold_minutes"],
            max_positions=max_positions,
            max_credits=credits_remaining,
        )

        # Update SWAB credits used
        db.update_swab_last_check(credits_used=result.get("credits_used", 0))

        log_info(
            f"SWAB scheduled check complete: "
            f"{result['positions_checked']} checked, "
            f"{result['still_holding']} holding, "
            f"{result['sold']} sold, "
            f"{result['credits_used']} credits used"
        )

    except Exception as e:
        log_error(f"SWAB scheduled check failed: {e}")


def update_scheduler_interval():
    """
    Update the scheduler interval based on SWAB settings.

    Call this when SWAB settings are updated.
    """
    global _scheduler

    if _scheduler is None:
        return

    settings = db.get_swab_settings()

    # Remove existing job if present
    if _scheduler.get_job(_check_job_id):
        _scheduler.remove_job(_check_job_id)

    # Only add job if auto-check is enabled
    if settings["auto_check_enabled"]:
        interval_minutes = settings["check_interval_minutes"]
        _scheduler.add_job(
            swab_position_check_job,
            trigger=IntervalTrigger(minutes=interval_minutes),
            id=_check_job_id,
            name="SWAB Position Check",
            replace_existing=True,
        )
        log_info(f"SWAB scheduler updated: checking every {interval_minutes} minutes")
    else:
        log_info("SWAB scheduler: auto-check disabled")


def start_scheduler():
    """Start the scheduler with SWAB and Ingest jobs."""
    global _scheduler
    from meridinate.settings import CURRENT_INGEST_SETTINGS

    scheduler = get_scheduler()

    if scheduler.running:
        log_info("Scheduler already running")
        return

    # Load SWAB settings and configure job
    settings = db.get_swab_settings()

    if settings["auto_check_enabled"]:
        interval_minutes = settings["check_interval_minutes"]
        scheduler.add_job(
            swab_position_check_job,
            trigger=IntervalTrigger(minutes=interval_minutes),
            id=_check_job_id,
            name="SWAB Position Check",
            replace_existing=True,
        )
        log_info(f"SWAB scheduler configured: checking every {interval_minutes} minutes")
    else:
        log_info("SWAB scheduler: auto-check disabled at startup")

    # Configure Ingest jobs (feature-flagged)
    if CURRENT_INGEST_SETTINGS.get("ingest_enabled"):
        scheduler.add_job(
            ingest_tier0_job,
            trigger=IntervalTrigger(hours=1),
            id=_tier0_job_id,
            name="Ingest Tier-0 (DexScreener)",
            replace_existing=True,
        )
        log_info("[Ingest] Tier-0 scheduler enabled: running hourly")
    else:
        log_info("[Ingest] Tier-0 scheduler disabled at startup")

    if CURRENT_INGEST_SETTINGS.get("enrich_enabled"):
        scheduler.add_job(
            ingest_tier1_job,
            trigger=IntervalTrigger(hours=4),
            id=_tier1_job_id,
            name="Ingest Tier-1 (Helius Enrichment)",
            replace_existing=True,
        )
        log_info("[Ingest] Tier-1 scheduler enabled: running every 4 hours")
    else:
        log_info("[Ingest] Tier-1 scheduler disabled at startup")

    # Configure Hot Refresh job (feature-flagged, runs every 2 hours)
    if CURRENT_INGEST_SETTINGS.get("hot_refresh_enabled"):
        scheduler.add_job(
            ingest_hot_refresh_job,
            trigger=IntervalTrigger(hours=2),
            id=_hot_refresh_job_id,
            name="Ingest Hot Token Refresh (DexScreener)",
            replace_existing=True,
        )
        log_info("[Ingest] Hot Refresh scheduler enabled: running every 2 hours")
    else:
        log_info("[Ingest] Hot Refresh scheduler disabled at startup")

    scheduler.start()
    log_info("Scheduler started")


def stop_scheduler():
    """Stop the SWAB scheduler."""
    global _scheduler

    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        log_info("SWAB scheduler stopped")


def get_scheduler_status() -> dict:
    """Get current scheduler status."""
    global _scheduler

    settings = db.get_swab_settings()

    status = {
        "running": _scheduler is not None and _scheduler.running,
        "auto_check_enabled": settings["auto_check_enabled"],
        "check_interval_minutes": settings["check_interval_minutes"],
        "last_check_at": settings["last_check_at"],
        "next_check_at": None,
    }

    if _scheduler is not None and _scheduler.running:
        job = _scheduler.get_job(_check_job_id)
        if job and job.next_run_time:
            status["next_check_at"] = job.next_run_time.isoformat()

    return status


# ============================================================================
# Ingest Pipeline Scheduler Jobs
# ============================================================================


async def ingest_tier0_job():
    """
    Scheduled job for Tier-0 ingestion (DexScreener, free).

    Respects ingest settings for:
    - ingest_enabled flag
    - tier0_max_tokens_per_run
    - Threshold filters (mc_min, volume_min, etc.)
    """
    from meridinate.settings import CURRENT_INGEST_SETTINGS
    from meridinate.tasks.ingest_tasks import run_tier0_ingestion

    try:
        # Check if ingestion is enabled
        if not CURRENT_INGEST_SETTINGS.get("ingest_enabled"):
            log_info("[Tier-0] Auto-ingestion disabled, skipping scheduled run")
            return

        log_info("[Tier-0] Starting scheduled ingestion")

        result = await run_tier0_ingestion()

        log_info(
            f"[Tier-0] Scheduled run complete: "
            f"{result['tokens_new']} new, {result['tokens_updated']} updated"
        )

    except Exception as e:
        log_error(f"[Tier-0] Scheduled run failed: {e}")


async def ingest_tier1_job():
    """
    Scheduled job for Tier-1 enrichment (Helius, budgeted).

    Respects ingest settings for:
    - enrich_enabled flag
    - tier1_batch_size
    - tier1_credit_budget_per_run
    - Threshold filters
    - auto_promote_enabled (triggers auto-promote after enrichment)
    """
    from meridinate.settings import CURRENT_INGEST_SETTINGS
    from meridinate.tasks.ingest_tasks import run_tier1_enrichment

    try:
        # Check if enrichment is enabled
        if not CURRENT_INGEST_SETTINGS.get("enrich_enabled"):
            log_info("[Tier-1] Auto-enrichment disabled, skipping scheduled run")
            return

        log_info("[Tier-1] Starting scheduled enrichment")

        result = await run_tier1_enrichment()

        log_info(
            f"[Tier-1] Scheduled run complete: "
            f"{result['tokens_enriched']} enriched, {result['credits_used']} credits used"
        )

        # Log auto-promote results if triggered
        if "auto_promote" in result:
            ap = result["auto_promote"]
            log_info(
                f"[Tier-1] Auto-promote results: "
                f"{ap.get('tokens_promoted', 0)} promoted, "
                f"{ap.get('webhooks_registered', 0)} webhooks"
            )

    except Exception as e:
        log_error(f"[Tier-1] Scheduled run failed: {e}")


async def ingest_hot_refresh_job():
    """
    Scheduled job for hot token MC/volume refresh (DexScreener, free).

    Refreshes snapshots for recently ingested/enriched tokens to keep
    metrics fresh for promotion decisions.

    Respects ingest settings for:
    - hot_refresh_enabled flag
    - hot_refresh_age_hours
    - hot_refresh_max_tokens
    """
    from meridinate.settings import CURRENT_INGEST_SETTINGS
    from meridinate.tasks.ingest_tasks import run_hot_token_refresh

    try:
        # Check if hot refresh is enabled
        if not CURRENT_INGEST_SETTINGS.get("hot_refresh_enabled"):
            log_info("[Hot Refresh] Disabled, skipping scheduled run")
            return

        log_info("[Hot Refresh] Starting scheduled refresh")

        result = await run_hot_token_refresh()

        log_info(
            f"[Hot Refresh] Scheduled run complete: "
            f"{result['tokens_updated']} updated, {result['tokens_failed']} failed"
        )

    except Exception as e:
        log_error(f"[Hot Refresh] Scheduled run failed: {e}")


def update_ingest_scheduler():
    """
    Update the ingest scheduler based on settings.

    Call this when ingest settings are updated.
    """
    global _scheduler
    from meridinate.settings import CURRENT_INGEST_SETTINGS

    if _scheduler is None:
        return

    # Remove existing jobs if present
    if _scheduler.get_job(_tier0_job_id):
        _scheduler.remove_job(_tier0_job_id)
    if _scheduler.get_job(_tier1_job_id):
        _scheduler.remove_job(_tier1_job_id)
    if _scheduler.get_job(_hot_refresh_job_id):
        _scheduler.remove_job(_hot_refresh_job_id)

    # Add Tier-0 job if enabled (runs hourly)
    if CURRENT_INGEST_SETTINGS.get("ingest_enabled"):
        _scheduler.add_job(
            ingest_tier0_job,
            trigger=IntervalTrigger(hours=1),
            id=_tier0_job_id,
            name="Ingest Tier-0 (DexScreener)",
            replace_existing=True,
        )
        log_info("[Ingest] Tier-0 scheduler enabled: running hourly")
    else:
        log_info("[Ingest] Tier-0 scheduler disabled")

    # Add Tier-1 job if enabled (runs every 4 hours)
    if CURRENT_INGEST_SETTINGS.get("enrich_enabled"):
        _scheduler.add_job(
            ingest_tier1_job,
            trigger=IntervalTrigger(hours=4),
            id=_tier1_job_id,
            name="Ingest Tier-1 (Helius Enrichment)",
            replace_existing=True,
        )
        log_info("[Ingest] Tier-1 scheduler enabled: running every 4 hours")
    else:
        log_info("[Ingest] Tier-1 scheduler disabled")

    # Add Hot Refresh job if enabled (runs every 2 hours)
    if CURRENT_INGEST_SETTINGS.get("hot_refresh_enabled"):
        _scheduler.add_job(
            ingest_hot_refresh_job,
            trigger=IntervalTrigger(hours=2),
            id=_hot_refresh_job_id,
            name="Ingest Hot Token Refresh (DexScreener)",
            replace_existing=True,
        )
        log_info("[Ingest] Hot Refresh scheduler enabled: running every 2 hours")
    else:
        log_info("[Ingest] Hot Refresh scheduler disabled")
