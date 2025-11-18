"""
Metrics router - exposes operational metrics

Provides /metrics endpoint in Prometheus format for monitoring
"""

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from app.observability import metrics_collector

router = APIRouter()


@router.get("/metrics", response_class=PlainTextResponse)
async def get_metrics():
    """
    Get application metrics in Prometheus format

    Returns metrics including:
    - Application uptime
    - Job queue depth by status
    - Average processing and queue times
    - Job success rate
    - WebSocket connection stats
    - HTTP request stats
    """
    return metrics_collector.get_prometheus_metrics()


@router.get("/metrics/health")
async def get_health():
    """
    Get health check status

    Returns basic health information including queue depth
    and success rate
    """
    queue_depth = metrics_collector.get_queue_depth()
    success_rate = metrics_collector.get_success_rate()
    ws_stats = metrics_collector.get_websocket_stats()

    return {"status": "healthy", "queue": queue_depth, "success_rate": success_rate, "websocket": ws_stats}
