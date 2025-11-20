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
from meridinate.routers import analysis, metrics, settings_debug, tags, tokens, wallets, watchlist, webhooks
from meridinate.utils.models import AnalysisCompleteNotification, AnalysisStartNotification

# Import WebSocket manager and notification endpoints
from meridinate.websocket import get_connection_manager

# Import rate limiting middleware
from meridinate.middleware.rate_limit import setup_rate_limiting
from meridinate.settings import RATE_LIMIT_ENABLED

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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
        allow_origins=["http://localhost:3000"],
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
    app.include_router(watchlist.router, tags=["Watchlist"])
    app.include_router(tokens.router, tags=["Tokens"])
    app.include_router(analysis.router, tags=["Analysis"])
    app.include_router(wallets.router, tags=["Wallets"])
    app.include_router(tags.router, tags=["Tags"])
    app.include_router(webhooks.router, tags=["Webhooks"])

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
        print("=" * 80)
        print("Performance Features:")
        print("  - Cached requests: <10ms (instant on 2nd load)")
        print("  - 304 responses: ~2ms (ETags + If-None-Match)")
        print("  - Concurrent balance refresh: 10x faster than sequential")
        print("  - Heavy load: handles 100+ concurrent requests")
        print("  - WebSocket notifications: real-time analysis updates")
        print("=" * 80)

    return app


# Create application instance
app = create_app()


# For development/testing
if __name__ == "__main__":
    import uvicorn

    # Use import string for reload to work properly
    uvicorn.run("meridinate.main:app", host="0.0.0.0", port=5003, reload=True)
