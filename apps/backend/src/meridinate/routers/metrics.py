"""
Metrics router - exposes operational metrics

Provides /metrics endpoint in Prometheus format for monitoring
"""

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from meridinate.middleware.rate_limit import METRICS_RATE_LIMIT, conditional_rate_limit
from meridinate.observability import metrics_collector

router = APIRouter()


@router.get("/metrics", response_class=PlainTextResponse)
@conditional_rate_limit(METRICS_RATE_LIMIT)
async def get_metrics(request: Request):
    """
    Get application metrics in Prometheus format

    Returns metrics including:
    - Application uptime
    - Job queue depth by status
    - Average processing and queue times
    - Job success rate
    - WebSocket connection stats
    - HTTP request stats
    - API usage (Helius, DexScreener, CoinGecko)
    - Cache hit/miss rates
    - Analysis phase timing breakdowns
    """
    return metrics_collector.get_prometheus_metrics()


@router.get("/metrics/health")
@conditional_rate_limit(METRICS_RATE_LIMIT)
async def get_health(request: Request):
    """
    Get health check status

    Returns basic health information including queue depth
    and success_rate
    """
    queue_depth = metrics_collector.get_queue_depth()
    success_rate = metrics_collector.get_success_rate()
    ws_stats = metrics_collector.get_websocket_stats()

    return {"status": "healthy", "queue": queue_depth, "success_rate": success_rate, "websocket": ws_stats}


@router.get("/metrics/stats")
@conditional_rate_limit(METRICS_RATE_LIMIT)
async def get_detailed_stats(request: Request):
    """
    Get detailed statistics in JSON format

    Returns comprehensive metrics including:
    - Queue and job statistics
    - API usage breakdown
    - Cache performance
    - Analysis phase timing
    - WebSocket stats
    """
    return {
        "queue": metrics_collector.get_queue_depth(),
        "processing": {
            "avg_processing_time": metrics_collector.get_average_processing_time(),
            "avg_queue_time": metrics_collector.get_average_queue_time(),
            "success_rate": metrics_collector.get_success_rate(),
        },
        "api_usage": metrics_collector.get_api_usage(),
        "cache": metrics_collector.get_cache_stats(),
        "analysis_phases": metrics_collector.get_analysis_phase_stats(),
        "websocket": metrics_collector.get_websocket_stats(),
        "http": metrics_collector.get_http_stats(),
    }
