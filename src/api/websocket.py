"""
WebSocket connection manager for real-time job updates.
"""

from fastapi import WebSocket, WebSocketDisconnect
from typing import Set
import json
import logging

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self.active: Set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.add(ws)
        logger.info(f"WS connected. {len(self.active)} active")

    def disconnect(self, ws: WebSocket):
        self.active.discard(ws)
        logger.info(f"WS disconnected. {len(self.active)} active")

    async def broadcast(self, event: str, data: dict):
        """Broadcast an event to all connected WebSocket clients."""
        msg = json.dumps({"event": event, "data": data})
        dead = set()
        for ws in self.active:
            try:
                await ws.send_text(msg)
            except Exception:
                dead.add(ws)
        self.active -= dead


manager = ConnectionManager()
