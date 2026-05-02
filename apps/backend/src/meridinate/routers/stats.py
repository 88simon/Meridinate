"""
Stats router - API credit usage and system statistics endpoints

Provides REST endpoints for monitoring API credit usage and system health.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from meridinate.cache import ResponseCache
from meridinate.middleware.rate_limit import READ_RATE_LIMIT, conditional_rate_limit
from meridinate.credit_tracker import get_credit_tracker, CreditOperation

# Status bar cache — 15 second TTL (scheduler jobs run on 2+ minute intervals)
_status_bar_cache = ResponseCache(ttl=15, name="status_bar")

router = APIRouter()


class CreditUsageStatsResponse(BaseModel):
    """Response model for credit usage statistics."""

    total_credits: int
    period_start: str
    period_end: str
    by_operation: Dict[str, int]
    transaction_count: int
    session_credits: int


class CreditTransactionResponse(BaseModel):
    """Response model for a single credit transaction."""

    id: int
    operation: str
    credits: int
    timestamp: Optional[str]
    token_id: Optional[int]
    wallet_address: Optional[str]
    context: Optional[Dict[str, Any]]


class CreditTransactionsListResponse(BaseModel):
    """Response model for credit transactions list."""

    transactions: List[CreditTransactionResponse]
    total: int


class OperationCostsResponse(BaseModel):
    """Response model for operation cost estimates."""

    costs: Dict[str, int]


class AggregatedOperationResponse(BaseModel):
    """Response model for an aggregated operation group."""

    operation: str
    label: str
    credits: int
    timestamp: str
    transaction_count: int


class AggregatedOperationsListResponse(BaseModel):
    """Response model for aggregated operations list."""

    operations: List[AggregatedOperationResponse]


class OperationLogEntryResponse(BaseModel):
    """Response model for a persisted operation log entry."""

    id: int
    operation: str
    label: str
    credits: int
    call_count: int
    timestamp: str
    context: Optional[Dict[str, Any]]


class OperationLogListResponse(BaseModel):
    """Response model for operation log list."""

    operations: List[OperationLogEntryResponse]
    total: int


class ScheduledJobResponse(BaseModel):
    """Response model for a scheduled job."""

    id: str
    name: str
    enabled: bool
    next_run_at: Optional[str]
    interval_minutes: int


class RunningJobResponse(BaseModel):
    """Response model for a currently running job."""

    id: str
    name: str
    started_at: str
    elapsed_seconds: int


class ScheduledJobsListResponse(BaseModel):
    """Response model for scheduled jobs list."""

    jobs: List[ScheduledJobResponse]
    running_jobs: List[RunningJobResponse]
    scheduler_running: bool


@router.get("/api/stats/credits/today", response_model=CreditUsageStatsResponse)
@conditional_rate_limit(READ_RATE_LIMIT)
async def get_credits_today(request: Request):
    """
    Get API credit usage for today.

    Returns:
        Credit usage statistics including total credits, breakdown by operation,
        and transaction count for the current day.
    """
    tracker = get_credit_tracker()
    stats = tracker.get_daily_usage()
    ops_total = tracker.get_daily_credits_from_operations()

    return CreditUsageStatsResponse(
        total_credits=max(ops_total, stats.total_credits),
        period_start=stats.period_start.isoformat(),
        period_end=stats.period_end.isoformat(),
        by_operation=stats.by_operation,
        transaction_count=stats.transaction_count,
        session_credits=tracker.get_session_credits(),
    )


@router.get("/api/stats/credits/range", response_model=CreditUsageStatsResponse)
@conditional_rate_limit(READ_RATE_LIMIT)
async def get_credits_range(
    request: Request,
    days: int = Query(default=7, ge=1, le=90, description="Number of days to look back"),
):
    """
    Get API credit usage for a date range.

    Args:
        days: Number of days to look back (default: 7, max: 90)

    Returns:
        Aggregated credit usage statistics for the specified period.
    """
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    tracker = get_credit_tracker()
    stats = tracker.get_usage_range(start_date, end_date)

    return CreditUsageStatsResponse(
        total_credits=stats.total_credits,
        period_start=stats.period_start.isoformat(),
        period_end=stats.period_end.isoformat(),
        by_operation=stats.by_operation,
        transaction_count=stats.transaction_count,
        session_credits=tracker.get_session_credits(),
    )


@router.get("/api/stats/credits/transactions", response_model=CreditTransactionsListResponse)
@conditional_rate_limit(READ_RATE_LIMIT)
async def get_credit_transactions(
    request: Request,
    limit: int = Query(default=50, ge=1, le=500, description="Maximum number of transactions"),
    operation: Optional[str] = Query(default=None, description="Filter by operation type"),
    token_id: Optional[int] = Query(default=None, description="Filter by token ID"),
):
    """
    Get recent credit transactions with optional filtering.

    Args:
        limit: Maximum number of transactions to return
        operation: Filter by operation type (e.g., 'wallet_balance', 'token_analysis')
        token_id: Filter by token ID

    Returns:
        List of credit transactions with metadata.
    """
    # Validate operation if provided
    op_filter = None
    if operation:
        try:
            op_filter = CreditOperation(operation)
        except ValueError:
            # Invalid operation name, will return empty results
            pass

    transactions = get_credit_tracker().get_recent_transactions(
        limit=limit,
        operation=op_filter,
        token_id=token_id,
    )

    return CreditTransactionsListResponse(
        transactions=[
            CreditTransactionResponse(
                id=tx.id,
                operation=tx.operation,
                credits=tx.credits,
                timestamp=tx.timestamp.isoformat() if tx.timestamp else None,
                token_id=tx.token_id,
                wallet_address=tx.wallet_address,
                context=tx.context,
            )
            for tx in transactions
        ],
        total=len(transactions),
    )


@router.get("/api/stats/credits/operations", response_model=AggregatedOperationsListResponse)
@conditional_rate_limit(READ_RATE_LIMIT)
async def get_aggregated_operations(
    request: Request,
    limit: int = Query(default=5, ge=1, le=20, description="Maximum number of operation groups"),
    window_seconds: int = Query(default=3, ge=1, le=60, description="Time window for grouping (seconds)"),
):
    """
    Get recent credit operations aggregated by time window.

    Groups individual API calls into high-level operations (e.g., batch operations
    that run multiple calls within a short time window are shown as a single entry).

    Args:
        limit: Maximum number of operation groups to return
        window_seconds: Time window for grouping transactions (default: 3 seconds)

    Returns:
        List of aggregated operation groups with labels and total credits.
    """
    # Operation label mapping for display
    OPERATION_LABELS = {
        "wallet_balance": "Wallet Balance",
        "token_metadata": "Token Metadata",
        "account_owner": "Account Owner",
        "token_largest_accounts": "Top Holders",
        "get_transaction": "Transaction Fetch",
        "signatures_for_address": "Signature Lookup",
        "token_accounts": "Token Accounts",
        "transactions_for_address": "Transaction History",
        "token_analysis": "Token Analysis",
        "top_holders_fetch": "Top Holders Fetch",
        "market_cap_refresh": "Market Cap Refresh",
        "wallet_refresh": "Wallet Refresh",
        "position_check": "Position Check",
    }

    # High-level operation inference based on operation mix
    def infer_operation_label(ops: Dict[str, int]) -> str:
        """Infer a high-level operation name from the mix of low-level operations."""
        op_names = set(ops.keys())

        # Token analysis typically involves many different operations
        if "token_analysis" in op_names:
            return "Token Analysis"

        # Market cap refresh
        if "market_cap_refresh" in op_names:
            return "Market Cap Refresh"

        # Top holders fetch
        if "top_holders_fetch" in op_names or "token_largest_accounts" in op_names:
            return "Top Holders Fetch"

        # Position check
        if "position_check" in op_names:
            return "Position Check"

        # Wallet refresh (batch balance checks)
        if op_names == {"wallet_balance"} or (
            "wallet_balance" in op_names and "account_owner" in op_names and len(op_names) <= 2
        ):
            total = sum(ops.values())
            if total > 10:
                return "Batch Wallet Refresh"
            return "Wallet Balance Check"

        # Helius enrichment (mix of wallet_balance, account_owner, token_metadata)
        if {"wallet_balance", "account_owner"}.issubset(op_names):
            return "Helius Enrichment"

        # Default: use the most common operation
        if ops:
            primary_op = max(ops.keys(), key=lambda k: ops[k])
            return OPERATION_LABELS.get(primary_op, primary_op.replace("_", " ").title())

        return "Unknown Operation"

    # Fetch more transactions than needed to ensure we can aggregate
    transactions = get_credit_tracker().get_recent_transactions(limit=limit * 50)

    if not transactions:
        return AggregatedOperationsListResponse(operations=[])

    # Group transactions by time window
    groups = []
    current_group = None
    window = timedelta(seconds=window_seconds)

    for tx in transactions:
        if tx.timestamp is None:
            continue

        if current_group is None:
            current_group = {
                "start_time": tx.timestamp,
                "end_time": tx.timestamp,
                "operations": {tx.operation: tx.credits},
                "total_credits": tx.credits,
                "transaction_count": 1,
            }
        elif tx.timestamp >= current_group["end_time"] - window:
            # Add to current group
            current_group["end_time"] = tx.timestamp
            current_group["operations"][tx.operation] = (
                current_group["operations"].get(tx.operation, 0) + tx.credits
            )
            current_group["total_credits"] += tx.credits
            current_group["transaction_count"] += 1
        else:
            # Start a new group
            groups.append(current_group)
            current_group = {
                "start_time": tx.timestamp,
                "end_time": tx.timestamp,
                "operations": {tx.operation: tx.credits},
                "total_credits": tx.credits,
                "transaction_count": 1,
            }

        if len(groups) >= limit:
            break

    # Don't forget the last group
    if current_group and len(groups) < limit:
        groups.append(current_group)

    # Convert groups to response format
    aggregated = []
    for group in groups[:limit]:
        label = infer_operation_label(group["operations"])

        # Determine primary operation for the response
        primary_op = max(group["operations"].keys(), key=lambda k: group["operations"][k])

        aggregated.append(
            AggregatedOperationResponse(
                operation=primary_op,
                label=label,
                credits=group["total_credits"],
                timestamp=group["start_time"].isoformat(),
                transaction_count=group["transaction_count"],
            )
        )

    return AggregatedOperationsListResponse(operations=aggregated)


@router.get("/api/stats/credits/operation-log", response_model=OperationLogListResponse)
@conditional_rate_limit(READ_RATE_LIMIT)
async def get_operation_log(
    request: Request,
    limit: int = Query(default=30, ge=1, le=100, description="Maximum number of operations to return"),
):
    """
    Get recent high-level operations from the persistent log.

    This endpoint returns persisted operation records that survive restarts.
    Each entry represents a user-facing operation like "Token Analysis",
    "Position Check", "Tier-1 Enrichment", etc.

    Args:
        limit: Maximum number of operations to return (default: 30, max: 100)

    Returns:
        List of operation log entries ordered by timestamp descending.
    """
    entries = get_credit_tracker().get_recent_operations(limit=limit)

    return OperationLogListResponse(
        operations=[
            OperationLogEntryResponse(
                id=entry.id,
                operation=entry.operation,
                label=entry.label,
                credits=entry.credits,
                call_count=entry.call_count,
                timestamp=entry.timestamp.isoformat() if entry.timestamp else "",
                context=entry.context,
            )
            for entry in entries
        ],
        total=len(entries),
    )


@router.get("/api/stats/credits/token/{token_id}")
@conditional_rate_limit(READ_RATE_LIMIT)
async def get_token_credits(request: Request, token_id: int):
    """
    Get total credits used for a specific token.

    Args:
        token_id: Token ID to query

    Returns:
        Total credits used for the token.
    """
    total = get_credit_tracker().get_token_credits(token_id)

    return {"token_id": token_id, "total_credits": total}


@router.get("/api/stats/credits/costs", response_model=OperationCostsResponse)
@conditional_rate_limit(READ_RATE_LIMIT)
async def get_operation_costs(request: Request):
    """
    Get credit cost estimates for each operation type.

    Returns:
        Dictionary mapping operation names to their credit costs.
    """
    from meridinate.credit_tracker import CREDIT_COSTS

    return OperationCostsResponse(
        costs={op.value: cost for op, cost in CREDIT_COSTS.items()}
    )


@router.get("/api/stats/credits/estimate")
@conditional_rate_limit(READ_RATE_LIMIT)
async def estimate_operation_cost(
    request: Request,
    operation: str = Query(..., description="Operation type to estimate"),
    count: int = Query(default=1, ge=1, description="Number of operations"),
):
    """
    Estimate credit cost for a planned operation.

    Args:
        operation: Operation type (e.g., 'wallet_balance', 'transactions_for_address')
        count: Number of operations to perform

    Returns:
        Estimated credit cost.
    """
    try:
        op = CreditOperation(operation)
        estimated = get_credit_tracker().estimate_operation_cost(op, count)
        return {
            "operation": operation,
            "count": count,
            "estimated_credits": estimated,
        }
    except ValueError:
        return {
            "operation": operation,
            "count": count,
            "estimated_credits": count,  # Default to 1 credit per operation
            "warning": f"Unknown operation type: {operation}",
        }


@router.get("/api/stats/scheduler/jobs", response_model=ScheduledJobsListResponse)
@conditional_rate_limit(READ_RATE_LIMIT)
async def get_scheduled_jobs(request: Request):
    """
    Get status of all scheduled background jobs.

    Returns:
        List of scheduled jobs with their next run times and enabled status,
        plus any currently running jobs with elapsed time.
        Used by the frontend to show live countdowns and running status.
    """
    from meridinate.scheduler import get_all_scheduled_jobs, get_running_jobs, get_scheduler

    scheduler = get_scheduler()
    jobs = get_all_scheduled_jobs()
    running = get_running_jobs()

    return ScheduledJobsListResponse(
        jobs=[
            ScheduledJobResponse(
                id=job["id"],
                name=job["name"],
                enabled=job["enabled"],
                next_run_at=job["next_run_at"],
                interval_minutes=job["interval_minutes"],
            )
            for job in jobs
        ],
        running_jobs=[
            RunningJobResponse(
                id=rj["id"],
                name=rj["name"],
                started_at=rj["started_at"],
                elapsed_seconds=rj["elapsed_seconds"],
            )
            for rj in running
        ],
        scheduler_running=scheduler.running if scheduler else False,
    )


@router.get("/api/stats/status-bar")
@conditional_rate_limit(READ_RATE_LIMIT)
async def get_status_bar(request: Request):
    """
    Single endpoint for the global status bar. Returns scheduler timers,
    token polling tier breakdown, credit usage, and relevant settings.
    All values are live and reflect current settings.
    """
    # Short-lived cache to avoid redundant heavy aggregation on rapid polling
    cached, _ = _status_bar_cache.get("status_bar")
    if cached is not None:
        return cached

    import aiosqlite
    from meridinate.scheduler import get_all_scheduled_jobs, get_running_jobs
    from meridinate.settings import DATABASE_FILE
    from meridinate.tasks.mc_tracker import get_poll_interval_minutes

    # Scheduler jobs (timers)
    jobs = get_all_scheduled_jobs()
    running = get_running_jobs()
    running_ids = {rj["id"] for rj in running}

    timers = {}
    for job in jobs:
        timers[job["id"]] = {
            "name": job["name"],
            "enabled": job["enabled"],
            "next_run_at": job["next_run_at"],
            "interval_minutes": job["interval_minutes"],
            "is_running": job["id"] in running_ids,
            "paused": job.get("paused", False),
        }

    # Token polling tier breakdown
    tiers = {"fresh": 0, "maturing": 0, "aging": 0, "old": 0, "retired": 0}
    verdicts = {"wins": 0, "losses": 0, "pending": 0}

    async with aiosqlite.connect(DATABASE_FILE) as conn:
        conn.row_factory = aiosqlite.Row

        # Get all active tokens with age + verdict info
        cursor = await conn.execute("""
            SELECT t.id, t.analysis_timestamp, t.market_cap_usd_current, t.market_cap_usd
            FROM analyzed_tokens t
            WHERE t.deleted_at IS NULL OR t.deleted_at = ''
        """)
        tokens = await cursor.fetchall()

        # Get all verdict tags
        cursor = await conn.execute(
            "SELECT token_id, tag FROM token_tags WHERE tag IN ('verified-win', 'verified-loss')"
        )
        verdict_map = {}
        for row in await cursor.fetchall():
            verdict_map[row[0]] = row[1]

        # Get tokens with open positions
        cursor = await conn.execute(
            "SELECT DISTINCT token_id FROM mtew_token_positions WHERE still_holding = 1"
        )
        tokens_with_positions = {row[0] for row in await cursor.fetchall()}

        # Get position tracker settings (for daily budget + check interval)
        cursor = await conn.execute(
            "SELECT daily_credit_budget, check_interval_minutes FROM swab_settings LIMIT 1"
        )
        swab_row = await cursor.fetchone()
        position_daily_budget = swab_row[0] if swab_row else 500
        position_check_interval = swab_row[1] if swab_row else 5

        # Position tracker stats
        cursor = await conn.execute("""
            SELECT
                COUNT(*) as total_tracked,
                SUM(CASE WHEN still_holding = 1 THEN 1 ELSE 0 END) as still_holding,
                SUM(CASE WHEN still_holding = 0 THEN 1 ELSE 0 END) as exited,
                AVG(CASE WHEN pnl_source = 'helius_enhanced' AND total_sold_usd > 0
                    THEN total_sold_usd / NULLIF(total_bought_usd, 0) END) as avg_return,
                SUM(CASE WHEN pnl_source = 'helius_enhanced' AND realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN pnl_source = 'helius_enhanced' AND realized_pnl <= 0 AND still_holding = 0 THEN 1 ELSE 0 END) as losses
            FROM mtew_token_positions
        """)
        pos_row = await cursor.fetchone()
        total_tracked = pos_row[0] or 0
        still_holding = pos_row[1] or 0
        exited = pos_row[2] or 0
        avg_return = pos_row[3]
        pos_wins = pos_row[4] or 0
        pos_losses = pos_row[5] or 0
        pos_total = pos_wins + pos_losses
        win_rate = (pos_wins / pos_total * 100) if pos_total > 0 else 0

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    total_active = 0
    tokens_scanned_today = 0
    for token in tokens:
        token_id = token[0]
        ts_str = token[1]
        current_mc = token[2] or token[3] or 0
        verdict = verdict_map.get(token_id)

        if not ts_str:
            continue

        try:
            ts = str(ts_str)
            if "T" in ts:
                analysis_time = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            else:
                analysis_time = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            age_hours = (now - analysis_time).total_seconds() / 3600
            if analysis_time >= today_start:
                tokens_scanned_today += 1
        except Exception:
            continue

        # Count verdicts
        if verdict == "verified-win":
            verdicts["wins"] += 1
        elif verdict == "verified-loss":
            verdicts["losses"] += 1
        else:
            verdicts["pending"] += 1

        # Retirement check (mirrors mc_tracker logic)
        if current_mc < 1000 and age_hours > 24:
            tiers["retired"] += 1
            continue
        if verdict and token_id not in tokens_with_positions:
            tiers["retired"] += 1
            continue
        if not verdict and age_hours > 336:
            tiers["retired"] += 1
            continue

        # Active — categorize by age tier
        total_active += 1
        if age_hours <= 6:
            tiers["fresh"] += 1
        elif age_hours <= 72:
            tiers["maturing"] += 1
        elif age_hours <= 168:
            tiers["aging"] += 1
        else:
            tiers["old"] += 1

    # Credit usage today — use operation_log sum for accuracy
    tracker = get_credit_tracker()
    daily_stats = tracker.get_daily_usage()
    credits_today_actual = tracker.get_daily_credits_from_operations()

    # Per-job credit breakdown: daily totals + last run cost + last run time + status
    job_names = ["auto_scan", "mc_tracker", "position_check"]
    job_credits = {
        name: {
            "today": daily_stats.by_operation.get(name, 0),
            "last_run": 0,
            "last_run_at": None,
            "last_run_context": None,
        }
        for name in job_names
    }
    # Find last run info from operation log
    recent_ops = tracker.get_recent_operations(limit=50)
    seen = set()
    for op in recent_ops:
        if op.operation in job_credits and op.operation not in seen:
            job_credits[op.operation]["last_run"] = op.credits
            job_credits[op.operation]["last_run_at"] = (op.timestamp.isoformat() + "Z") if op.timestamp else None
            job_credits[op.operation]["last_run_context"] = op.context
            seen.add(op.operation)
        if len(seen) == len(job_credits):
            break

    # Get discovery interval from ingest settings
    from meridinate.settings import CURRENT_INGEST_SETTINGS
    discovery_interval = CURRENT_INGEST_SETTINGS.get("discovery_interval_minutes", 15)

    result = {
        "timers": timers,
        "polling": {
            "total_tokens": len(tokens),
            "total_active": total_active,
            "tokens_scanned_today": tokens_scanned_today,
            "tiers": tiers,
            "tier_intervals": {
                "fresh": "2-5 min",
                "maturing": "15 min - 1 hour",
                "aging": "4 hours",
                "old": "12-24 hours",
            },
            "verdicts": verdicts,
        },
        "positions": {
            "total_tracked": total_tracked,
            "still_holding": still_holding,
            "exited": exited,
            "win_rate": round(win_rate),
            "avg_return": round(avg_return, 1) if avg_return else None,
        },
        "credits": {
            "used_today": max(credits_today_actual, daily_stats.total_credits),
            "position_daily_budget": position_daily_budget,
            "by_job": job_credits,
        },
        "settings": {
            "discovery_interval_minutes": discovery_interval,
            "mc_check_interval_minutes": 2,
            "position_check_interval_minutes": position_check_interval,
        },
        "realtime": await asyncio.to_thread(_get_realtime_stats),
        "followup": _get_followup_stats(),
        "clobr": _get_clobr_stats(),
    }

    _status_bar_cache.set("status_bar", result)
    return result


def _get_followup_stats() -> dict:
    """Get follow-up tracker stats for the status bar."""
    try:
        from meridinate.services.followup_tracker import get_followup_tracker
        tracker = get_followup_tracker()
        return {
            "running": tracker.is_running,
            **tracker.stats,
        }
    except Exception:
        return {"running": False, "active_tracking": 0}


def _get_clobr_stats() -> dict:
    """Get CLOBr enrichment stats for the status bar."""
    from meridinate.settings import CURRENT_INGEST_SETTINGS, CLOBR_API_KEY
    enabled = bool(CURRENT_INGEST_SETTINGS.get("clobr_enabled")) and bool(CLOBR_API_KEY)
    result = {
        "enabled": enabled,
        "min_score": CURRENT_INGEST_SETTINGS.get("clobr_min_score", 30),
        "has_key": bool(CLOBR_API_KEY),
        "calls_today": 0,
    }
    if enabled:
        try:
            from meridinate.services.clobr_service import get_clobr_service
            svc = get_clobr_service()
            if svc:
                result["calls_today"] = svc.calls_today
        except Exception:
            pass
    return result


def _get_realtime_stats() -> dict:
    """Get real-time listener stats for the status bar."""
    try:
        from meridinate.services.realtime_listener import get_realtime_listener
        listener = get_realtime_listener()
        stats = {
            "running": listener.is_running,
            **listener.stats,
        }

        # Add cross-system metrics from database
        try:
            import sqlite3
            from meridinate.settings import DATABASE_FILE
            conn = sqlite3.connect(DATABASE_FILE)
            cursor = conn.cursor()

            # How many webhook tokens were picked up by auto-scan
            cursor.execute("SELECT COUNT(*) FROM webhook_detections WHERE auto_scan_token_id IS NOT NULL")
            picked_up = cursor.fetchone()[0]

            # How many were rejected by webhook and saved auto-scan credits
            cursor.execute("SELECT COUNT(*) FROM webhook_detections WHERE status = 'rejected' AND auto_scan_token_id IS NULL")
            credits_saved = cursor.fetchone()[0]

            # Average time to migration
            cursor.execute("SELECT AVG(time_to_migration_minutes) FROM webhook_detections WHERE time_to_migration_minutes IS NOT NULL")
            avg_migration = cursor.fetchone()[0]

            # Conviction accuracy: high conviction tokens that became wins
            cursor.execute("""
                SELECT
                    SUM(CASE WHEN wd.conviction_score >= 70 AND tt.tag = 'verified-win' THEN 1 ELSE 0 END) as high_conv_wins,
                    SUM(CASE WHEN wd.conviction_score >= 70 AND tt.tag IS NOT NULL THEN 1 ELSE 0 END) as high_conv_total
                FROM webhook_detections wd
                LEFT JOIN token_tags tt ON tt.token_id = wd.auto_scan_token_id AND tt.tag IN ('verified-win', 'verified-loss')
                WHERE wd.auto_scan_token_id IS NOT NULL
            """)
            acc_row = cursor.fetchone()
            high_conv_wins = acc_row[0] or 0
            high_conv_total = acc_row[1] or 0

            conn.close()

            stats["cross_system"] = {
                "tokens_picked_up": picked_up,
                "tokens_rejected_saved_credits": credits_saved,
                "avg_migration_minutes": round(avg_migration, 1) if avg_migration else None,
                "conviction_accuracy": round(high_conv_wins / high_conv_total * 100) if high_conv_total > 0 else None,
            }
        except Exception:
            stats["cross_system"] = {}

        return stats
    except Exception:
        return {"running": False}
