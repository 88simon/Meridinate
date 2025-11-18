"""
Analysis router - token analysis and job management endpoints

Provides REST endpoints for queuing analysis jobs and checking status
"""

import asyncio
import csv
import io
import json
import os
import requests
import uuid
from datetime import datetime
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

import analyzed_tokens_db as db
from app.observability import (
    log_analysis_complete,
    log_analysis_failed,
    log_analysis_start,
    log_error,
    log_info,
    metrics_collector,
    sanitize_address,
    set_job_id,
)
from app.settings import CURRENT_API_SETTINGS, HELIUS_API_KEY
from app.state import ANALYSIS_EXECUTOR, get_all_analysis_jobs, get_analysis_job, set_analysis_job, update_analysis_job
from app.utils.models import (
    AnalysisJob,
    AnalysisJobSummary,
    AnalysisListResponse,
    AnalysisSettings,
    AnalyzeTokenRequest,
    QueueTokenResponse,
)
from app.utils.validators import is_valid_solana_address
from helius_api import TokenAnalyzer, generate_axiom_export, generate_token_acronym

router = APIRouter()


def run_token_analysis_sync(
    job_id: str,
    token_address: str,
    min_usd: float,
    time_window_hours: int,
    max_transactions: int,
    max_credits: int,
    max_wallets: int,
):
    """Synchronous worker function for background thread pool"""
    try:
        # Start metrics tracking
        metrics_collector.job_started(job_id)
        log_analysis_start(job_id, token_address)
        update_analysis_job(job_id, {"status": "processing"})

        analyzer = TokenAnalyzer(HELIUS_API_KEY)
        result = analyzer.analyze_token(
            mint_address=token_address,
            min_usd=min_usd,
            time_window_hours=time_window_hours,
            max_transactions=max_transactions,
            max_credits=max_credits,
            max_wallets_to_store=max_wallets,
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
            update_analysis_job(job_id, {"status": "completed", "result": result, "error": error_msg})
            return

        # Generate acronym
        acronym = generate_token_acronym(token_name, token_symbol)

        # Convert datetime objects to strings
        for bidder in early_bidders:
            if "first_buy_time" in bidder and hasattr(bidder["first_buy_time"], "isoformat"):
                bidder["first_buy_time"] = bidder["first_buy_time"].isoformat()

        # Generate Axiom export
        axiom_export = generate_axiom_export(
            early_bidders=early_bidders, token_name=token_name, token_symbol=token_symbol, limit=max_wallets
        )

        # Save to database
        token_id = db.save_analyzed_token(
            token_address=token_address,
            token_name=token_name,
            token_symbol=token_symbol,
            acronym=acronym,
            early_bidders=early_bidders,
            axiom_json=axiom_export,
            first_buy_timestamp=result.get("first_transaction_time"),
            credits_used=result.get("api_credits_used", 0),
            max_wallets=max_wallets,
            market_cap_usd=result.get("market_cap_usd"),
        )
        log_info("Saved token to database", token_id=token_id, acronym=acronym)

        # Get file paths
        analysis_filepath = db.get_analysis_file_path(token_id, token_name, in_trash=False)
        axiom_filepath = db.get_axiom_file_path(token_id, acronym, in_trash=False)

        # Ensure directories exist
        os.makedirs(os.path.dirname(analysis_filepath), exist_ok=True)
        os.makedirs(os.path.dirname(axiom_filepath), exist_ok=True)

        # Save files
        with open(analysis_filepath, "w") as f:
            json.dump(result, f, indent=2)
        with open(axiom_filepath, "w") as f:
            json.dump(axiom_export, f, indent=2)

        # Update database with file paths
        db.update_token_file_paths(token_id, analysis_filepath, axiom_filepath)

        result_filename = os.path.basename(analysis_filepath)

        # Update job with results
        update_analysis_job(
            job_id,
            {
                "status": "completed",
                "result": result,
                "result_file": result_filename,
                "axiom_file": axiom_filepath,
                "token_id": token_id,
            },
        )

        # Track completion metrics
        credits_used = result.get("api_credits_used", 0)
        metrics_collector.job_completed(job_id, len(early_bidders), credits_used)
        log_analysis_complete(job_id, len(early_bidders), credits_used)

        # Send WebSocket notification via HTTP endpoint
        try:
            notification_data = {
                "job_id": job_id,
                "token_name": token_name,
                "token_symbol": token_symbol,
                "acronym": acronym,
                "wallets_found": len(early_bidders),
                "token_id": token_id,
            }
            requests.post(
                "http://localhost:5003/notify/analysis_complete",
                json=notification_data,
                timeout=1,
            )
            log_info("WebSocket notification sent", event="analysis_complete")
        except Exception as notify_error:
            log_error("Failed to send WebSocket notification", error=str(notify_error))

    except Exception as e:
        error_msg = str(e)
        metrics_collector.job_failed(job_id, error_msg)
        log_analysis_failed(job_id, error_msg)
        update_analysis_job(job_id, {"status": "failed", "error": error_msg})


@router.post("/analyze/token", status_code=202, response_model=QueueTokenResponse)
async def analyze_token(request: AnalyzeTokenRequest):
    """Analyze a token to find early bidders (queues job)"""
    if not is_valid_solana_address(request.address):
        raise HTTPException(status_code=400, detail="Invalid Solana address format")

    settings = request.api_settings or AnalysisSettings(**CURRENT_API_SETTINGS)
    min_usd = request.min_usd if request.min_usd is not None else settings.minUsdFilter

    job_id = str(uuid.uuid4())[:8]
    job_data = {
        "job_id": job_id,
        "token_address": request.address,
        "status": "queued",
        "min_usd": min_usd,
        "time_window_hours": request.time_window_hours,
        "transaction_limit": settings.transactionLimit,
        "max_wallets": settings.walletCount,
        "max_credits": settings.maxCreditsPerAnalysis,
        "created_at": datetime.now().isoformat(),
        "result": None,
        "error": None,
    }
    set_analysis_job(job_id, job_data)

    # Track metrics
    metrics_collector.job_queued(job_id)
    log_info(
        "Token analysis queued",
        token_address=sanitize_address(request.address),
        min_usd=min_usd,
        max_wallets=settings.walletCount,
    )

    # Submit to thread pool
    ANALYSIS_EXECUTOR.submit(
        run_token_analysis_sync,
        job_id,
        request.address,
        min_usd,
        request.time_window_hours,
        settings.transactionLimit,
        settings.maxCreditsPerAnalysis,
        settings.walletCount,
    )

    return {
        "status": "queued",
        "job_id": job_id,
        "token_address": request.address,
        "api_settings": {
            "min_usd": min_usd,
            "transaction_limit": settings.transactionLimit,
            "max_wallets": settings.walletCount,
            "time_window_hours": request.time_window_hours,
        },
        "results_url": f"/analysis/{job_id}",
    }


@router.get("/analysis/{job_id}", response_model=AnalysisJob)
async def get_analysis(job_id: str):
    """Get analysis job status and results"""
    job = get_analysis_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    job_copy = job.copy()

    # If completed, load result from file if not in memory
    if job_copy["status"] == "completed" and job_copy.get("result") is None:
        try:
            if "result_file" in job_copy:
                result_file = os.path.join("analysis_results", job_copy["result_file"])
                if os.path.exists(result_file):
                    with open(result_file, "r") as f:
                        job_copy["result"] = json.load(f)
        except Exception as e:
            job_copy["status"] = "failed"
            job_copy["error"] = f"Could not load results: {str(e)}"

    return job_copy


@router.get("/analysis", response_model=AnalysisListResponse)
async def list_analyses(search: str = None, limit: int = 100):
    """List analysis jobs and completed tokens"""
    try:
        if search:
            tokens = db.search_tokens(search.strip())
        else:
            tokens = db.get_analyzed_tokens(limit=limit)

        jobs: List[Dict[str, Any]] = []
        for token in tokens:
            jobs.append(
                {
                    "job_id": str(token["id"]),
                    "status": "completed",
                    "token_address": token["token_address"],
                    "token_name": token.get("token_name"),
                    "token_symbol": token.get("token_symbol"),
                    "acronym": token.get("acronym"),
                    "wallets_found": token.get("wallets_found"),
                    "timestamp": token.get("analysis_timestamp"),
                    "credits_used": token.get("last_analysis_credits", 0),
                    "results_url": f"/analysis/{token['id']}",
                }
            )

        # Add in-progress jobs
        if not search:
            for job in get_all_analysis_jobs().values():
                if job.get("status") != "completed":
                    jobs.insert(0, job)

        return {"total": len(jobs), "jobs": jobs}
    except Exception as exc:
        log_error(f"Failed to list analyses: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/analysis/{job_id}/csv")
async def export_analysis_csv(job_id: str):
    """Export analysis results as CSV"""
    job = get_analysis_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job["status"] != "completed" or not job.get("result"):
        raise HTTPException(status_code=400, detail="Analysis not completed or no results")

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Wallet Address", "First Buy Time", "Total USD", "Transaction Count", "Average Buy USD"])

    for bidder in job["result"].get("early_bidders", []):
        writer.writerow(
            [
                bidder["wallet_address"],
                bidder.get("first_buy_time", ""),
                f"${bidder.get('total_usd', 0):.2f}",
                bidder.get("transaction_count", 0),
                f"${bidder.get('average_buy_usd', 0):.2f}",
            ]
        )

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=token_analysis_{job_id}.csv"},
    )


@router.get("/analysis/{job_id}/axiom")
async def download_axiom_export(job_id: str):
    """Download Axiom wallet tracker JSON"""
    job = get_analysis_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job["status"] != "completed" or not job.get("axiom_file"):
        raise HTTPException(status_code=400, detail="Analysis not completed or Axiom export not available")

    axiom_filepath = job["axiom_file"]
    if not os.path.exists(axiom_filepath):
        raise HTTPException(status_code=404, detail="Axiom export file not found")

    return FileResponse(axiom_filepath, media_type="application/json", filename=os.path.basename(axiom_filepath))
