"""
WebSocket Connection Manager for AutoGrid

Manages WebSocket connections and broadcasts messages to users.
"""

import logging
from typing import Any
from collections import defaultdict

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Manages WebSocket connections per user.

    Supports multiple connections per user (e.g., multiple browser tabs).
    """

    def __init__(self) -> None:
        # Map of user_id to set of WebSocket connections
        self.active_connections: dict[str, set[WebSocket]] = defaultdict(set)

    async def connect(self, websocket: WebSocket, user_id: str) -> None:
        """Accept a new WebSocket connection for a user."""
        await websocket.accept()
        self.active_connections[user_id].add(websocket)
        logger.info(f"WebSocket connected for user {user_id}. Total connections: {len(self.active_connections[user_id])}")

    def disconnect(self, websocket: WebSocket, user_id: str) -> None:
        """Remove a WebSocket connection for a user."""
        if websocket in self.active_connections[user_id]:
            self.active_connections[user_id].discard(websocket)
            logger.info(f"WebSocket disconnected for user {user_id}. Remaining connections: {len(self.active_connections[user_id])}")

            # Clean up empty user entries
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]

    async def send_personal_message(self, message: dict[str, Any], user_id: str) -> None:
        """Send a message to a specific user (all their connections)."""
        if user_id in self.active_connections:
            disconnected = []
            for connection in self.active_connections[user_id]:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.warning(f"Failed to send message to user {user_id}: {e}")
                    disconnected.append(connection)

            # Clean up disconnected connections
            for conn in disconnected:
                self.disconnect(conn, user_id)

    async def broadcast_to_user(self, user_id: str, event_type: str, payload: dict[str, Any]) -> None:
        """
        Broadcast an event to all connections of a specific user.

        Args:
            user_id: The user ID to send to
            event_type: Type of event (e.g., 'bot_status', 'order_update', 'trade')
            payload: The event payload data
        """
        message = {
            "type": event_type,
            "payload": payload,
            "timestamp": self._get_timestamp(),
        }
        await self.send_personal_message(message, user_id)

    async def broadcast(self, event_type: str, payload: dict[str, Any]) -> None:
        """Broadcast a message to all connected users."""
        message = {
            "type": event_type,
            "payload": payload,
            "timestamp": self._get_timestamp(),
        }

        for user_id in list(self.active_connections.keys()):
            await self.send_personal_message(message, user_id)

    def get_connection_count(self) -> int:
        """Get total number of active connections."""
        return sum(len(connections) for connections in self.active_connections.values())

    def get_user_count(self) -> int:
        """Get number of connected users."""
        return len(self.active_connections)

    def is_user_connected(self, user_id: str) -> bool:
        """Check if a user has any active connections."""
        return user_id in self.active_connections and len(self.active_connections[user_id]) > 0

    @staticmethod
    def _get_timestamp() -> str:
        """Get current ISO timestamp."""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()


# Global connection manager instance
ws_manager = ConnectionManager()


# Helper functions for broadcasting events
async def broadcast_bot_status(user_id: str, bot_id: str, status: str, message: str | None = None) -> None:
    """Broadcast bot status change to user."""
    await ws_manager.broadcast_to_user(
        user_id,
        "bot_status",
        {
            "bot_id": bot_id,
            "status": status,
            "message": message,
        },
    )


async def broadcast_order_update(user_id: str, bot_id: str, order: dict[str, Any]) -> None:
    """Broadcast order update to user."""
    await ws_manager.broadcast_to_user(
        user_id,
        "order_update",
        {
            "bot_id": bot_id,
            "order": order,
        },
    )


async def broadcast_trade(user_id: str, bot_id: str, trade: dict[str, Any]) -> None:
    """Broadcast trade execution to user."""
    await ws_manager.broadcast_to_user(
        user_id,
        "trade",
        {
            "bot_id": bot_id,
            "trade": trade,
        },
    )


async def broadcast_pnl_update(user_id: str, bot_id: str, realized_pnl: float, unrealized_pnl: float) -> None:
    """Broadcast P&L update to user."""
    await ws_manager.broadcast_to_user(
        user_id,
        "pnl_update",
        {
            "bot_id": bot_id,
            "realized_pnl": realized_pnl,
            "unrealized_pnl": unrealized_pnl,
        },
    )


async def broadcast_error(user_id: str, bot_id: str | None, error: str) -> None:
    """Broadcast error to user."""
    await ws_manager.broadcast_to_user(
        user_id,
        "error",
        {
            "bot_id": bot_id,
            "error": error,
        },
    )
