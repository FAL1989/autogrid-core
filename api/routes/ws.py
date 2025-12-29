"""
WebSocket route for real-time updates.

Provides real-time updates for:
- Bot status changes
- Order updates
- Trade executions
- P&L changes
"""

import logging
from typing import Annotated

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, HTTPException, status

from api.core.ws_manager import ws_manager
from api.services.jwt import decode_token, TokenError

logger = logging.getLogger(__name__)

router = APIRouter()


async def authenticate_websocket(token: str) -> str:
    """
    Authenticate WebSocket connection using JWT token.

    Args:
        token: JWT access token

    Returns:
        user_id: Authenticated user ID

    Raises:
        HTTPException: If token is invalid
    """
    try:
        payload = decode_token(token)

        # Verify it's an access token
        if payload.get("type") != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
            )

        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
            )

        return user_id

    except TokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: Annotated[str, Query(description="JWT access token")],
) -> None:
    """
    WebSocket endpoint for real-time updates.

    Connect with: ws://localhost:8000/ws?token=<your_jwt_token>

    Message types received:
    - bot_status: Bot status changes (running, stopped, error)
    - order_update: Order creation, fill, cancellation
    - trade: Trade execution with realized P&L
    - pnl_update: P&L updates for a bot
    - error: Error notifications

    Message format:
    ```json
    {
        "type": "bot_status",
        "payload": {
            "bot_id": "uuid",
            "status": "running",
            "message": "optional message"
        },
        "timestamp": "2024-01-15T12:00:00Z"
    }
    ```

    Client can send ping messages to keep connection alive:
    ```json
    {"type": "ping"}
    ```

    Server responds with:
    ```json
    {"type": "pong", "timestamp": "2024-01-15T12:00:00Z"}
    ```
    """
    # Authenticate before accepting connection
    try:
        user_id = await authenticate_websocket(token)
    except HTTPException as e:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        logger.warning(f"WebSocket authentication failed: {e.detail}")
        return

    # Accept connection
    await ws_manager.connect(websocket, user_id)

    try:
        # Send connection confirmation
        await websocket.send_json({
            "type": "connected",
            "payload": {
                "user_id": user_id,
                "message": "WebSocket connection established",
            },
            "timestamp": ws_manager._get_timestamp(),
        })

        # Keep connection alive and handle incoming messages
        while True:
            try:
                data = await websocket.receive_json()

                # Handle ping/pong for keepalive
                if data.get("type") == "ping":
                    await websocket.send_json({
                        "type": "pong",
                        "timestamp": ws_manager._get_timestamp(),
                    })

                # Handle subscription requests (for future use)
                elif data.get("type") == "subscribe":
                    # Could be used to subscribe to specific bots
                    bot_id = data.get("bot_id")
                    if bot_id:
                        await websocket.send_json({
                            "type": "subscribed",
                            "payload": {"bot_id": bot_id},
                            "timestamp": ws_manager._get_timestamp(),
                        })

            except Exception as e:
                # Handle JSON decode errors gracefully
                if "JSON" in str(e):
                    logger.warning(f"Invalid JSON received from user {user_id}")
                    continue
                raise

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for user {user_id}")
    except Exception as e:
        logger.error(f"WebSocket error for user {user_id}: {e}")
    finally:
        ws_manager.disconnect(websocket, user_id)


@router.get("/ws/stats")
async def websocket_stats() -> dict:
    """
    Get WebSocket connection statistics.

    Returns:
        Connection statistics
    """
    return {
        "total_connections": ws_manager.get_connection_count(),
        "connected_users": ws_manager.get_user_count(),
    }
