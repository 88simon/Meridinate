"""
WebSocket connection management and real-time notifications

Handles WebSocket connections for real-time analysis updates
"""

import logging
from typing import Dict, List

from fastapi import WebSocket, WebSocketDisconnect

# Configure logging for WebSocket
logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections for real-time notifications"""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        """
        Accept and register a new WebSocket connection

        Args:
            websocket: WebSocket connection to register
        """
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"[WebSocket] Client connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        """
        Unregister a WebSocket connection

        Args:
            websocket: WebSocket connection to remove
        """
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"[WebSocket] Client disconnected. Total connections: {len(self.active_connections)}")

    async def broadcast(self, message: Dict):
        """
        Broadcast message to all connected clients

        Args:
            message: Dictionary message to broadcast (will be sent as JSON)
        """
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
                logger.info(f"[WebSocket] Sent message to client: {message.get('event')}")
            except Exception as e:
                logger.error(f"[WebSocket] Error sending to client: {e}")
                disconnected.append(connection)

        # Remove disconnected clients
        for connection in disconnected:
            self.disconnect(connection)

    def get_connection_count(self) -> int:
        """
        Get number of active WebSocket connections

        Returns:
            Number of active connections
        """
        return len(self.active_connections)


# Global connection manager instance (will be initialized in main.py)
manager: ConnectionManager = None


def get_connection_manager() -> ConnectionManager:
    """
    Get the global ConnectionManager instance

    Returns:
        ConnectionManager singleton
    """
    global manager
    if manager is None:
        manager = ConnectionManager()
    return manager


# Helper functions for common notification patterns


async def notify_analysis_start(job_id: str, token_name: str, token_symbol: str):
    """
    Send analysis start notification to all connected clients

    Args:
        job_id: Analysis job ID
        token_name: Token name
        token_symbol: Token symbol
    """
    mgr = get_connection_manager()
    message = {
        "event": "analysis_start",
        "data": {"job_id": job_id, "token_name": token_name, "token_symbol": token_symbol},
    }
    await mgr.broadcast(message)
    logger.info(f"[Notify] Analysis started: {token_name}")


async def notify_analysis_complete(
    job_id: str, token_name: str, token_symbol: str, acronym: str, wallets_found: int, token_id: int
):
    """
    Send analysis complete notification to all connected clients

    Args:
        job_id: Analysis job ID
        token_name: Token name
        token_symbol: Token symbol
        acronym: Generated acronym
        wallets_found: Number of wallets found
        token_id: Database ID of the token
    """
    mgr = get_connection_manager()
    message = {
        "event": "analysis_complete",
        "data": {
            "job_id": job_id,
            "token_name": token_name,
            "token_symbol": token_symbol,
            "acronym": acronym,
            "wallets_found": wallets_found,
            "token_id": token_id,
        },
    }
    await mgr.broadcast(message)
    logger.info(f"[Notify] Analysis complete: {token_name} ({wallets_found} wallets)")
