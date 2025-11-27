"""
Stats router - API credit usage and system statistics endpoints

Provides REST endpoints for monitoring API credit usage and system health.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from meridinate.middleware.rate_limit import READ_RATE_LIMIT, conditional_rate_limit
from meridinate.credit_tracker import credit_tracker, CreditOperation

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


@router.get("/api/stats/credits/today", response_model=CreditUsageStatsResponse)
@conditional_rate_limit(READ_RATE_LIMIT)
async def get_credits_today(request: Request):
    """
    Get API credit usage for today.

    Returns:
        Credit usage statistics including total credits, breakdown by operation,
        and transaction count for the current day.
    """
    stats = credit_tracker.get_daily_usage()

    return CreditUsageStatsResponse(
        total_credits=stats.total_credits,
        period_start=stats.period_start.isoformat(),
        period_end=stats.period_end.isoformat(),
        by_operation=stats.by_operation,
        transaction_count=stats.transaction_count,
        session_credits=credit_tracker.get_session_credits(),
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

    stats = credit_tracker.get_usage_range(start_date, end_date)

    return CreditUsageStatsResponse(
        total_credits=stats.total_credits,
        period_start=stats.period_start.isoformat(),
        period_end=stats.period_end.isoformat(),
        by_operation=stats.by_operation,
        transaction_count=stats.transaction_count,
        session_credits=credit_tracker.get_session_credits(),
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

    transactions = credit_tracker.get_recent_transactions(
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
    total = credit_tracker.get_token_credits(token_id)

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
        estimated = credit_tracker.estimate_operation_cost(op, count)
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
