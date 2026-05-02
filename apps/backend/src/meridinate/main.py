"""
Meridinate - FastAPI Application Factory

Main entry point for the modular FastAPI application.
Registers all routers and configures middleware.
"""

import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import ORJSONResponse

# Import routers
from meridinate.routers import analysis, ingest, leaderboard, metrics, quick_dd, settings_debug, stats, swab, tags, tokens, wallets, watchlist, webhooks
from meridinate.utils.models import AnalysisCompleteNotification, AnalysisStartNotification

# Import WebSocket manager and notification endpoints
from meridinate.websocket import get_connection_manager

# Import rate limiting middleware
from meridinate.middleware.rate_limit import setup_rate_limiting
from meridinate.settings import RATE_LIMIT_ENABLED, API_PORT, FRONTEND_URL

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# Uvicorn access-log noise filter
# ============================================================================
#
# The frontend polls a handful of status endpoints every 2-3 seconds. Without
# filtering, those drown out actually-useful log lines (errors, agent dialogue,
# scan progress) at the rate of ~1000 lines/min per open tab.
#
# This filter drops 2xx access logs for known polling routes, while keeping:
#   - All 4xx/5xx on those same routes (so errors are visible)
#   - All requests to any other route
#
# Net result: ~30 lines/min instead of ~1000, with full visibility on anything
# unusual. Reversible by removing the addFilter call below.

_NOISY_POLLING_ROUTES = (
    "/api/ingest/scan-progress",
    "/api/wallet-shadow/status",
    "/api/wallet-shadow/feed",
    "/api/wallet-shadow/open-positions",
    "/api/wallet-shadow/token-heat",
    "/api/wallet-shadow/alerts",
    "/api/wallet-shadow/convergences",
    "/api/wallet-shadow/signal-wallets",
    "/api/stats/credits/today",
    "/api/stats/credits/operation-log",
    "/api/stats/status-bar",
    "/api/tokens/latest",
    "/api/intel/status",
    "/api/intel/recommendations",
)


class _PollingNoiseFilter(logging.Filter):
    """Drop 2xx access-log lines for known high-frequency polling endpoints."""

    def filter(self, record: logging.LogRecord) -> bool:
        # Uvicorn access record format: args = (client_addr, method, path, http_version, status_code)
        # Keep the line if we can't parse it — never silently swallow unknown formats.
        try:
            args = record.args
            if not isinstance(args, tuple) or len(args) < 5:
                return True
            path = args[2] if isinstance(args[2], str) else ""
            status = args[4]
            status_code = int(status) if not isinstance(status, int) else status
        except (ValueError, IndexError, TypeError):
            return True

        # Always keep errors so problems on noisy routes are still visible.
        if status_code >= 400:
            return True

        # Drop if the path starts with any noisy route (handles query strings + path params).
        for noisy in _NOISY_POLLING_ROUTES:
            if path.startswith(noisy):
                return False
        return True


logging.getLogger("uvicorn.access").addFilter(_PollingNoiseFilter())


def create_app() -> FastAPI:
    """
    FastAPI application factory

    Returns:
        Configured FastAPI application
    """
    app = FastAPI(
        title="Meridinate API",
        description="High-performance async API for Solana token analysis (Modular)",
        version="2.0.0",
        default_response_class=ORJSONResponse,
    )

    # CORS Configuration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[FRONTEND_URL],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # GZip Compression Middleware (reduces payload size by 70-90%)
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    # Setup rate limiting (if enabled)
    if RATE_LIMIT_ENABLED:
        setup_rate_limiting(app)

    # Register routers
    app.include_router(settings_debug.router, tags=["Settings & Health"])
    app.include_router(metrics.router, tags=["Metrics"])
    app.include_router(stats.router, tags=["Stats"])
    app.include_router(watchlist.router, tags=["Watchlist"])
    app.include_router(tokens.router, tags=["Tokens"])
    app.include_router(analysis.router, tags=["Analysis"])
    app.include_router(wallets.router, tags=["Wallets"])
    app.include_router(tags.router, tags=["Tags"])
    app.include_router(webhooks.router, tags=["Webhooks"])
    app.include_router(swab.router, tags=["Position Tracker"])
    app.include_router(ingest.router, tags=["Ingest"])
    app.include_router(quick_dd.router, tags=["Quick DD"])
    app.include_router(leaderboard.router, tags=["Leaderboard"])

    from meridinate.routers import starred, intel, recommendations, bot_probe, wallet_shadow, rug_analysis
    app.include_router(starred.router, tags=["Starred"])
    app.include_router(intel.router, tags=["Intel"])
    app.include_router(rug_analysis.router, tags=["Rug Analysis"])
    app.include_router(recommendations.router, tags=["Intel Recommendations"])
    app.include_router(bot_probe.router, tags=["Bot Probe"])
    app.include_router(wallet_shadow.router, tags=["Wallet Shadow"])

    # WebSocket endpoint
    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        """WebSocket endpoint for real-time notifications"""
        from meridinate.observability import metrics_collector

        manager = get_connection_manager()
        await manager.connect(websocket)
        metrics_collector.websocket_connected()

        try:
            # Keep connection alive and handle any incoming messages
            while True:
                data = await websocket.receive_text()
                metrics_collector.websocket_message_received()
                # Echo back for heartbeat/testing
                await websocket.send_json({"type": "pong", "data": data})
                metrics_collector.websocket_message_sent()
        except WebSocketDisconnect:
            manager.disconnect(websocket)
            metrics_collector.websocket_disconnected()
        except Exception as e:
            logger.error(f"[WebSocket] Error: {e}")
            manager.disconnect(websocket)
            metrics_collector.websocket_disconnected()

    # WebSocket notification endpoints (HTTP triggers)
    @app.post("/notify/analysis_complete")
    async def notify_analysis_complete(notification: AnalysisCompleteNotification):
        """HTTP endpoint to trigger analysis complete notifications"""
        logger.info(f"[Notify] Analysis complete: {notification.token_name} ({notification.wallets_found} wallets)")

        message = {"event": "analysis_complete", "data": notification.dict()}

        manager = get_connection_manager()
        await manager.broadcast(message)

        return {"status": "broadcasted", "connections": manager.get_connection_count()}

    @app.post("/notify/analysis_start")
    async def notify_analysis_start(notification: AnalysisStartNotification):
        """HTTP endpoint to trigger analysis start notifications"""
        logger.info(f"[Notify] Analysis started: {notification.token_name}")

        message = {"event": "analysis_start", "data": notification.dict()}

        manager = get_connection_manager()
        await manager.broadcast(message)

        return {"status": "broadcasted", "connections": manager.get_connection_count()}

    # Startup event
    @app.on_event("startup")
    async def startup_event():
        print("=" * 80)
        print("Meridinate - FastAPI Service (Modular Architecture)")
        print("=" * 80)
        print("[OK] Service started on port 5003")
        print("[OK] Modular architecture with separate routers and services")
        print("[OK] WebSocket support for real-time notifications (/ws)")
        print("[OK] Response caching with ETags (30s TTL + 304 responses)")
        print("[OK] Request deduplication (prevents duplicate concurrent queries)")
        print("[OK] GZip compression (70-90% payload reduction)")
        print("[OK] Async database queries with aiosqlite")
        print("[OK] Fast JSON serialization (orjson - 5-10x faster)")
        if RATE_LIMIT_ENABLED:
            print("[OK] Rate limiting enabled (slowapi + Redis)")

        # Start Position tracker scheduler
        from meridinate.scheduler import start_scheduler
        start_scheduler()
        print("[OK] Position tracker scheduler initialized")

        # Build leaderboard cache on startup (warm cache)
        try:
            from meridinate.services.leaderboard_cache import rebuild_leaderboard_cache
            cache_result = rebuild_leaderboard_cache()
            print(f"[OK] Leaderboard cache warmed: {cache_result['wallets_cached']} wallets in {cache_result['duration_ms']}ms")
        except Exception as e:
            print(f"[WARN] Leaderboard cache warm failed: {e}")

        # Log ingest pipeline status
        from meridinate.settings import CURRENT_INGEST_SETTINGS
        ingest_status = "enabled" if CURRENT_INGEST_SETTINGS.get("discovery_enabled") else "disabled"
        print(f"[OK] Ingest pipeline initialized ({ingest_status})")

        print("=" * 80)
        print("Performance Features:")
        print("  - Cached requests: <10ms (instant on 2nd load)")
        print("  - 304 responses: ~2ms (ETags + If-None-Match)")
        print("  - Concurrent balance refresh: 10x faster than sequential")
        print("  - Heavy load: handles 100+ concurrent requests")
        print("  - WebSocket notifications: real-time analysis updates")
        print("  - Position tracker: scheduled wallet monitoring")
        print("=" * 80)

    # Shutdown event
    @app.on_event("shutdown")
    async def shutdown_event():
        from meridinate.scheduler import stop_scheduler
        stop_scheduler()
        print("[OK] Position tracker scheduler stopped")

        # Stop real-time listener and follow-up tracker (saves in-progress data)
        try:
            from meridinate.services.realtime_listener import get_realtime_listener
            listener = get_realtime_listener()
            if listener.is_running:
                await listener.stop()
                print("[OK] Real-time listener stopped")
        except Exception:
            pass

        try:
            from meridinate.services.followup_tracker import get_followup_tracker
            tracker = get_followup_tracker()
            if tracker.is_running:
                await tracker.stop()
                print("[OK] Follow-up tracker stopped (trajectories saved)")
        except Exception:
            pass

    return app


# Create application instance
app = create_app()


# For development/testing
if __name__ == "__main__":
    import os
    import uvicorn

    # reload=True spawns a file watcher and re-imports the entire app on any
    # source change — that's a 50-200% CPU spike per save AND keeps a second
    # Python process alive permanently. Default OFF for production-style runs.
    # Opt in via env var only when actively iterating on backend code.
    reload_enabled = os.getenv("MERIDINATE_RELOAD", "").lower() in ("1", "true", "yes")
    uvicorn.run("meridinate.main:app", host="0.0.0.0", port=API_PORT, reload=reload_enabled)
