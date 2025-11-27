"""
SWAB Scheduler Module
=====================
Handles background job scheduling for SWAB position checking.
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
    """Start the SWAB scheduler."""
    global _scheduler

    scheduler = get_scheduler()

    if scheduler.running:
        log_info("SWAB scheduler already running")
        return

    # Load settings and configure job
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

    scheduler.start()
    log_info("SWAB scheduler started")


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
