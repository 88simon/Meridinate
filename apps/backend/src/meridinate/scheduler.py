"""
Scheduler Module
================
Handles background job scheduling for:
- Position checking
- Ingest pipeline (Discovery ingestion, tracking refresh)

Uses APScheduler with asyncio support.
"""

import asyncio
from datetime import datetime
from typing import Dict, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from meridinate import analyzed_tokens_db as db
from meridinate.observability import log_error, log_info

# Global scheduler instance
_scheduler: Optional[AsyncIOScheduler] = None
_check_job_id = "swab_position_check"
_tier0_job_id = "ingest_tier0"
# _tier1_job_id removed — Tier-1 enrichment is fully deprecated
_hot_refresh_job_id = "ingest_hot_refresh"

# Track currently running jobs: job_id -> started_at timestamp
_running_jobs: Dict[str, datetime] = {}

# Credits per position check (getTokenAccountsByOwner = 1 credit standard RPC)
CREDITS_PER_POSITION_CHECK = 1
MAX_POSITIONS_PER_CHECK = 50


def mark_job_started(job_id: str) -> None:
    """Mark a job as currently running."""
    global _running_jobs
    _running_jobs[job_id] = datetime.now()


def mark_job_finished(job_id: str) -> None:
    """Mark a job as no longer running."""
    global _running_jobs
    _running_jobs.pop(job_id, None)


def get_running_jobs() -> list:
    """
    Get list of currently running jobs with elapsed time.

    Returns:
        List of dicts with job_id, name, started_at, elapsed_seconds
    """
    global _running_jobs

    job_names = {
        _check_job_id: "Position Check",
        _tier0_job_id: "Auto-Scan",
        _hot_refresh_job_id: "MC Tracker",
    }

    running = []
    now = datetime.now()

    for job_id, started_at in _running_jobs.items():
        elapsed = (now - started_at).total_seconds()
        running.append({
            "id": job_id,
            "name": job_names.get(job_id, job_id),
            "started_at": started_at.isoformat(),
            "elapsed_seconds": int(elapsed),
        })

    return running


def get_scheduler() -> AsyncIOScheduler:
    """Get or create the global scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler()
    return _scheduler


async def swab_position_check_job():
    """
    Scheduled job to check positions.

    Respects position tracker settings for:
    - auto_check_enabled
    - stale_threshold_minutes
    - daily_credit_budget
    """
    from meridinate.tasks.position_tracker import check_mtew_positions

    try:
        # Get current position tracker settings
        settings = db.get_swab_settings()

        # Check if auto-check is enabled
        if not settings["auto_check_enabled"]:
            log_info("Position auto-check disabled, skipping scheduled check")
            return

        # Check daily credit budget
        credits_remaining = settings["daily_credit_budget"] - settings["credits_used_today"]
        if credits_remaining <= 0:
            log_info("Position daily credit budget exhausted, skipping scheduled check")
            return

        # Calculate max positions to check based on remaining budget
        max_positions = min(MAX_POSITIONS_PER_CHECK, credits_remaining // CREDITS_PER_POSITION_CHECK)
        if max_positions <= 0:
            log_info("Position insufficient credits for position check")
            return

        mark_job_started(_check_job_id)

        log_info(
            f"Position scheduled check starting: max_positions={max_positions}, "
            f"credits_remaining={credits_remaining}"
        )

        # Run the position check
        result = await check_mtew_positions(
            older_than_minutes=settings["stale_threshold_minutes"],
            max_positions=max_positions,
            max_credits=credits_remaining,
        )

        # Update position tracker credits used
        db.update_swab_last_check(credits_used=result.get("credits_used", 0))

        log_info(
            f"Position scheduled check complete: "
            f"{result['positions_checked']} checked, "
            f"{result['still_holding']} holding, "
            f"{result['sold']} sold, "
            f"{result['credits_used']} credits used"
        )

        # Rebuild leaderboard cache after position data changes
        try:
            from meridinate.services.leaderboard_cache import rebuild_leaderboard_cache
            rebuild_leaderboard_cache()
        except Exception as cache_err:
            log_error(f"Leaderboard cache rebuild failed after position check: {cache_err}")

    except Exception as e:
        log_error(f"Position scheduled check failed: {e}")
        from meridinate.credit_tracker import get_credit_tracker
        get_credit_tracker().record_operation(
            operation="position_check", label="Position Check",
            credits=0, call_count=0, context={"error": str(e)},
        )
    finally:
        mark_job_finished(_check_job_id)


def update_scheduler_interval():
    """
    Update the scheduler interval based on position tracker settings.

    Call this when position tracker settings are updated.
    """
    global _scheduler

    if _scheduler is None:
        return

    settings = db.get_swab_settings()

    # Preserve pause state across reschedule
    was_paused = False
    existing = _scheduler.get_job(_check_job_id)
    if existing:
        was_paused = existing.next_run_time is None
        _scheduler.remove_job(_check_job_id)

    # Only add job if auto-check is enabled
    if settings["auto_check_enabled"]:
        interval_minutes = settings["check_interval_minutes"]
        _scheduler.add_job(
            swab_position_check_job,
            trigger=IntervalTrigger(minutes=interval_minutes),
            id=_check_job_id,
            name="Position Check",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        if was_paused:
            _scheduler.get_job(_check_job_id).pause()
            log_info(f"Position tracker updated: every {interval_minutes} min (still PAUSED)")
        else:
            log_info(f"Position tracker scheduler updated: checking every {interval_minutes} minutes")
    else:
        log_info("Position tracker scheduler: auto-check disabled")


def update_scan_interval():
    """
    Update the auto-scan interval based on ingest settings.
    Call this when scan interval settings are changed.
    """
    global _scheduler
    from meridinate.settings import CURRENT_INGEST_SETTINGS

    if _scheduler is None or not _scheduler.running:
        return

    interval = CURRENT_INGEST_SETTINGS.get("discovery_interval_minutes", 15)

    # Preserve pause state across reschedule
    was_paused = False
    existing = _scheduler.get_job(_tier0_job_id)
    if existing:
        was_paused = existing.next_run_time is None
        _scheduler.remove_job(_tier0_job_id)

    enabled = CURRENT_INGEST_SETTINGS.get("discovery_enabled")
    if enabled:
        _scheduler.add_job(
            ingest_tier0_job,
            trigger=IntervalTrigger(minutes=interval),
            id=_tier0_job_id,
            name="Auto-Scan (DexScreener + Helius)",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        # Re-pause if it was paused before the interval change
        if was_paused:
            _scheduler.get_job(_tier0_job_id).pause()
            log_info(f"[Auto-Scan] Interval updated to {interval} min (still PAUSED)")
        else:
            log_info(f"[Auto-Scan] Interval updated: every {interval} minutes")
    else:
        log_info("[Auto-Scan] Disabled")


def start_scheduler():
    """Start the scheduler with Position Tracker and Ingest jobs."""
    global _scheduler
    from meridinate.settings import CURRENT_INGEST_SETTINGS

    scheduler = get_scheduler()

    if scheduler.running:
        log_info("Scheduler already running")
        return

    # Load position tracker settings and configure job
    settings = db.get_swab_settings()

    if settings["auto_check_enabled"]:
        interval_minutes = settings["check_interval_minutes"]
        scheduler.add_job(
            swab_position_check_job,
            trigger=IntervalTrigger(minutes=interval_minutes),
            id=_check_job_id,
            name="Position Check",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        log_info(f"Position tracker scheduler configured: checking every {interval_minutes} minutes")
    else:
        log_info("Position tracker scheduler: auto-check disabled at startup")

    # Configure Auto-Scan job (feature-flagged)
    if CURRENT_INGEST_SETTINGS.get("discovery_enabled"):
        tier0_interval = CURRENT_INGEST_SETTINGS.get("discovery_interval_minutes", 15)
        scheduler.add_job(
            ingest_tier0_job,
            trigger=IntervalTrigger(minutes=tier0_interval),
            id=_tier0_job_id,
            name="Auto-Scan (DexScreener + Helius)",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        log_info(f"[Ingest] Discovery scheduler enabled: running every {tier0_interval} minutes")
    else:
        log_info("[Ingest] Discovery scheduler disabled at startup")

    # Tier-1 enrichment removed — fully deprecated

    # MC Tracker — decay-based polling, runs every 2 minutes
    # The tracker itself checks which tokens are due based on age-decay intervals
    scheduler.add_job(
        mc_tracker_job,
        trigger=IntervalTrigger(minutes=2),
        id=_hot_refresh_job_id,
        name="MC Tracker (decay-based)",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    log_info("[MC Tracker] Decay-based polling enabled: checking every 2 minutes")

    scheduler.start()
    log_info("Scheduler started")


def stop_scheduler():
    """Stop the Position tracker scheduler."""
    global _scheduler

    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        log_info("Position tracker scheduler stopped")


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
    Scheduled Auto-Scan job: discovers tokens from DexScreener and
    immediately runs Helius analysis on those passing filters.
    """
    from meridinate.settings import CURRENT_INGEST_SETTINGS
    from meridinate.tasks.ingest_tasks import run_auto_scan

    try:
        # Check if scanning is enabled
        if not CURRENT_INGEST_SETTINGS.get("discovery_enabled"):
            log_info("[Auto-Scan] Disabled, skipping scheduled run")
            return

        mark_job_started(_tier0_job_id)
        log_info("[Auto-Scan] Starting scheduled scan")

        result = await run_auto_scan()

        log_info(
            f"[Auto-Scan] Scheduled run complete: "
            f"{result['tokens_scanned']} scanned, {result['tokens_filtered']} filtered"
        )

    except Exception as e:
        log_error(f"[Auto-Scan] Scheduled run failed: {e}")
        from meridinate.credit_tracker import get_credit_tracker
        get_credit_tracker().record_operation(
            operation="auto_scan", label="Auto-Scan",
            credits=0, call_count=0, context={"error": str(e)},
        )
    finally:
        mark_job_finished(_tier0_job_id)


async def mc_tracker_job():
    """
    Scheduled MC tracker job — runs every 2 minutes.
    The tracker itself determines which tokens are due based on age-decay intervals.
    Runs in a thread to avoid blocking the event loop.
    """
    import asyncio
    try:
        mark_job_started(_hot_refresh_job_id)
        from meridinate.tasks.mc_tracker import run_mc_tracker
        result = await asyncio.to_thread(run_mc_tracker)
        log_info(
            f"[MC Tracker] {result.get('tokens_updated', 0)} updated, "
            f"{result.get('verdicts_computed', 0)} verdicts"
        )

        # Rebuild leaderboard cache only if tokens were actually updated
        if result.get('tokens_updated', 0) > 0 or result.get('verdicts_computed', 0) > 0:
            try:
                from meridinate.services.leaderboard_cache import rebuild_leaderboard_cache
                await asyncio.to_thread(rebuild_leaderboard_cache)
            except Exception as cache_err:
                log_error(f"Leaderboard cache rebuild failed after MC tracker: {cache_err}")

    except Exception as e:
        log_error(f"[MC Tracker] Job failed: {e}")
        from meridinate.credit_tracker import get_credit_tracker
        get_credit_tracker().record_operation(
            operation="mc_tracker", label="MC Tracker",
            credits=0, call_count=0, context={"error": str(e)},
        )
    finally:
        mark_job_finished(_hot_refresh_job_id)



def update_ingest_scheduler():
    """
    Update the ingest scheduler based on settings.

    Call this when ingest settings are updated.
    """
    global _scheduler
    from meridinate.settings import CURRENT_INGEST_SETTINGS

    if _scheduler is None:
        return

    # Preserve pause states across reschedule
    paused_states = {}
    for job_id in [_tier0_job_id, _hot_refresh_job_id]:
        existing = _scheduler.get_job(job_id)
        if existing:
            paused_states[job_id] = existing.next_run_time is None
            _scheduler.remove_job(job_id)

    def _add_and_maybe_pause(job_func, trigger, job_id, name):
        _scheduler.add_job(job_func, trigger=trigger, id=job_id, name=name, replace_existing=True, max_instances=1, coalesce=True)
        if paused_states.get(job_id, False):
            _scheduler.get_job(job_id).pause()
            log_info(f"[Ingest] {name} updated (still PAUSED)")
        else:
            log_info(f"[Ingest] {name} enabled")

    # Add Discovery job if enabled
    if CURRENT_INGEST_SETTINGS.get("discovery_enabled"):
        tier0_interval = CURRENT_INGEST_SETTINGS.get("discovery_interval_minutes", 15)
        _add_and_maybe_pause(ingest_tier0_job, IntervalTrigger(minutes=tier0_interval), _tier0_job_id, f"Auto-Scan (every {tier0_interval} min)")
    else:
        log_info("[Ingest] Discovery scheduler disabled")


def get_all_scheduled_jobs() -> list:
    """
    Get status of all scheduled jobs with their next run times.

    Returns:
        List of job status dictionaries with id, name, enabled, next_run_at, interval
    """
    global _scheduler
    from meridinate.settings import CURRENT_INGEST_SETTINGS

    jobs = []

    # Position Check
    swab_settings = db.get_swab_settings()
    swab_job = {
        "id": _check_job_id,
        "name": "Position Check",
        "enabled": swab_settings["auto_check_enabled"],
        "next_run_at": None,
        "interval_minutes": swab_settings["check_interval_minutes"],
    }
    if _scheduler is not None and _scheduler.running:
        job = _scheduler.get_job(_check_job_id)
        if job:
            if job.next_run_time:
                swab_job["next_run_at"] = job.next_run_time.isoformat()
            else:
                swab_job["paused"] = True
    jobs.append(swab_job)

    # Auto-Scan
    tier0_interval = CURRENT_INGEST_SETTINGS.get("discovery_interval_minutes", 15)
    tier0_job = {
        "id": _tier0_job_id,
        "name": "Auto-Scan",
        "enabled": CURRENT_INGEST_SETTINGS.get("discovery_enabled", False),
        "next_run_at": None,
        "interval_minutes": tier0_interval,
    }
    if _scheduler is not None and _scheduler.running:
        job = _scheduler.get_job(_tier0_job_id)
        if job:
            if job.next_run_time:
                tier0_job["next_run_at"] = job.next_run_time.isoformat()
            else:
                tier0_job["paused"] = True
    jobs.append(tier0_job)

    # MC Tracker (always enabled — decay-based polling)
    hot_refresh_job = {
        "id": _hot_refresh_job_id,
        "name": "MC Tracker",
        "enabled": True,
        "next_run_at": None,
        "interval_minutes": 2,
    }
    if _scheduler is not None and _scheduler.running:
        job = _scheduler.get_job(_hot_refresh_job_id)
        if job:
            if job.next_run_time:
                hot_refresh_job["next_run_at"] = job.next_run_time.isoformat()
            else:
                hot_refresh_job["paused"] = True
    jobs.append(hot_refresh_job)

    return jobs
