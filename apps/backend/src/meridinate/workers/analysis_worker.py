"""
Analysis task worker using arq for async background processing

This worker handles background token analysis jobs using Redis-backed queue (arq).
Jobs are enqueued from the FastAPI endpoints and processed asynchronously.
"""

import asyncio
import json
import os
from datetime import datetime
from typing import Any, Dict

from arq import create_pool
from arq.connections import RedisSettings
from redis.asyncio import Redis

from meridinate import analyzed_tokens_db as db
from meridinate.helius_api import TokenAnalyzer, generate_axiom_export, generate_token_acronym
from meridinate.observability import (
    log_analysis_complete,
    log_analysis_failed,
    log_analysis_start,
    log_error,
    log_info,
    metrics_collector,
)
from meridinate.settings import HELIUS_API_KEY, REDIS_URL


async def analyze_token_task(
    ctx: Dict[str, Any], job_id: str, token_address: str, settings: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Background task for token analysis

    Args:
        ctx: arq context (provides Redis connection and other utilities)
        job_id: Unique job identifier
        token_address: Token mint address to analyze
        settings: Analysis settings (min_usd, max_credits, time_window_hours, etc.)

    Returns:
        Dict with status and results

    Raises:
        Exception if analysis fails (will be retried up to max_tries)
    """
    redis: Redis = ctx["redis"]

    try:
        # Update job status to processing
        await redis.set(f"job:{job_id}:status", "processing")
        await redis.set(f"job:{job_id}:started_at", datetime.now().isoformat())

        # Track metrics
        metrics_collector.job_started(job_id)
        log_analysis_start(job_id, token_address)

        # Run analysis (synchronous TokenAnalyzer)
        analyzer = TokenAnalyzer(HELIUS_API_KEY)
        result = await asyncio.to_thread(
            analyzer.analyze_token,
            mint_address=token_address,
            min_usd=settings.get("min_usd", 50.0),
            time_window_hours=settings.get("time_window_hours", 1),
            max_transactions=settings.get("transaction_limit", 500),
            max_credits=settings.get("max_credits", 1000),
            max_wallets_to_store=settings.get("max_wallets", 10),
        )

        # Extract token info
        token_info = result.get("token_info")
        if token_info is None:
            token_name = "Unknown"
            token_symbol = "UNK"
        else:
            metadata = token_info.get("onChainMetadata", {}).get("metadata", {})
            token_name = metadata.get("name", "Unknown")
            token_symbol = metadata.get("symbol", "UNK")

        # Check if analysis found any meaningful data
        early_bidders = result.get("early_bidders", [])
        if len(early_bidders) == 0 and token_info is None:
            error_msg = result.get("error", "No transactions found")
            log_info("Analysis found no data - skipping database save", wallets_found=0)
            metrics_collector.job_completed(job_id, 0, result.get("api_credits_used", 0))

            # Update Redis job status
            await redis.set(f"job:{job_id}:status", "completed")
            await redis.set(f"job:{job_id}:error", error_msg)
            await redis.set(f"job:{job_id}:completed_at", datetime.now().isoformat())

            return {"status": "completed", "wallets_found": 0, "error": error_msg}

        # Generate acronym
        acronym = generate_token_acronym(token_name, token_symbol)

        # Convert datetime objects to strings
        for bidder in early_bidders:
            if "first_buy_time" in bidder and hasattr(bidder["first_buy_time"], "isoformat"):
                bidder["first_buy_time"] = bidder["first_buy_time"].isoformat()

        # Generate Axiom export
        axiom_export = generate_axiom_export(
            early_bidders=early_bidders,
            token_name=token_name,
            token_symbol=token_symbol,
            limit=settings.get("max_wallets", 10),
        )

        # Save to database (run in thread to avoid blocking)
        token_id = await asyncio.to_thread(
            db.save_analyzed_token,
            token_address=token_address,
            token_name=token_name,
            token_symbol=token_symbol,
            acronym=acronym,
            early_bidders=early_bidders,
            axiom_json=axiom_export,
            first_buy_timestamp=result.get("first_transaction_time"),
            credits_used=result.get("api_credits_used", 0),
            max_wallets=settings.get("max_wallets", 10),
            market_cap_usd=result.get("market_cap_usd"),
            top_holders=result.get("top_holders"),
        )
        log_info("Saved token to database", token_id=token_id, acronym=acronym)

        # Invalidate cached token list
        try:
            from meridinate.routers.tokens import cache as tokens_cache

            tokens_cache.invalidate("tokens_history")
        except Exception as cache_err:
            log_error("Failed to invalidate token cache after analysis", error=str(cache_err))

        # Get file paths
        analysis_filepath = db.get_analysis_file_path(token_id, token_name, in_trash=False)
        axiom_filepath = db.get_axiom_file_path(token_id, acronym, in_trash=False)

        # Ensure directories exist
        os.makedirs(os.path.dirname(analysis_filepath), exist_ok=True)
        os.makedirs(os.path.dirname(axiom_filepath), exist_ok=True)

        # Save files (run in thread)
        await asyncio.to_thread(lambda: open(analysis_filepath, "w").write(json.dumps(result, indent=2)))
        await asyncio.to_thread(lambda: open(axiom_filepath, "w").write(json.dumps(axiom_export, indent=2)))

        # Update database with file paths (run in thread)
        await asyncio.to_thread(db.update_token_file_paths, token_id, analysis_filepath, axiom_filepath)

        result_filename = os.path.basename(analysis_filepath)

        # Update Redis with results
        await redis.set(f"job:{job_id}:status", "completed")
        await redis.set(f"job:{job_id}:result", json.dumps(result))
        await redis.set(f"job:{job_id}:result_file", result_filename)
        await redis.set(f"job:{job_id}:axiom_file", axiom_filepath)
        await redis.set(f"job:{job_id}:token_id", str(token_id))
        await redis.set(f"job:{job_id}:token_name", token_name)
        await redis.set(f"job:{job_id}:token_symbol", token_symbol)
        await redis.set(f"job:{job_id}:acronym", acronym)
        await redis.set(f"job:{job_id}:wallets_found", str(len(early_bidders)))
        await redis.set(f"job:{job_id}:completed_at", datetime.now().isoformat())

        # Track completion metrics
        credits_used = result.get("api_credits_used", 0)
        metrics_collector.job_completed(job_id, len(early_bidders), credits_used)
        log_analysis_complete(job_id, len(early_bidders), credits_used)

        # Send WebSocket notification (fire-and-forget)
        try:
            import httpx

            notification_data = {
                "job_id": job_id,
                "token_name": token_name,
                "token_symbol": token_symbol,
                "acronym": acronym,
                "wallets_found": len(early_bidders),
                "token_id": token_id,
            }
            async with httpx.AsyncClient() as client:
                await client.post(
                    "http://localhost:5003/notify/analysis_complete",
                    json=notification_data,
                    timeout=1,
                )
            log_info("WebSocket notification sent", event="analysis_complete")
        except Exception as notify_error:
            log_error("Failed to send WebSocket notification", error=str(notify_error))

        return {"status": "completed", "wallets_found": len(early_bidders), "token_id": token_id}

    except Exception as e:
        error_msg = str(e)
        metrics_collector.job_failed(job_id, error_msg)
        log_analysis_failed(job_id, error_msg)

        # Update Redis status
        await redis.set(f"job:{job_id}:status", "failed")
        await redis.set(f"job:{job_id}:error", error_msg)
        await redis.set(f"job:{job_id}:completed_at", datetime.now().isoformat())

        # Re-raise to trigger arq retry mechanism
        raise


class WorkerSettings:
    """arq worker configuration"""

    # Task functions to register
    functions = [analyze_token_task]

    # Redis connection settings
    redis_settings = RedisSettings.from_dsn(REDIS_URL)

    # Retry configuration
    max_tries = 3  # Retry failed jobs up to 3 times
    retry_jobs = True  # Enable automatic retry on failure

    # Job timeout (10 minutes for token analysis)
    job_timeout = 600

    # Worker settings
    max_jobs = 5  # Max concurrent analysis jobs per worker
    poll_delay = 0.5  # Check for new jobs every 500ms

    # Health check interval (seconds)
    health_check_interval = 60

    # Job retention (keep job results for 24 hours)
    keep_result = 86400
