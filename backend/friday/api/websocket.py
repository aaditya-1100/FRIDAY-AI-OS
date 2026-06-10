import asyncio
from typing import Set
from fastapi import WebSocket
from loguru import logger
from friday.core.event_bus import event_bus
from friday.core.events import EventEnvelope

class FSMWebSocketManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    def start(self):
        """Subscribe to FSM state change events on the event bus."""
        event_bus.subscribe("friday.core.state_change", self._on_state_change)
        event_bus.subscribe("friday.tool.confirm_required", self._on_confirm_required)
        logger.info("[FSM_WS_MANAGER] Subscribed to friday.core.state_change and friday.tool.confirm_required events.")

    def register_client(self, websocket: WebSocket):
        self.active_connections.add(websocket)
        logger.debug(f"[FSM_WS_MANAGER] Client registered. Total active: {len(self.active_connections)}")

    def unregister_client(self, websocket: WebSocket):
        self.active_connections.discard(websocket)
        logger.debug(f"[FSM_WS_MANAGER] Client unregistered. Total active: {len(self.active_connections)}")

    async def _on_confirm_required(self, envelope: EventEnvelope):
        payload = envelope.payload
        corr_id = str(envelope.correlation_id)
        
        # Format timestamp to ISO8601
        if hasattr(envelope.timestamp, "isoformat"):
            timestamp = envelope.timestamp.isoformat()
            if not timestamp.endswith("Z"):
                timestamp += "Z"
        else:
            timestamp = str(envelope.timestamp)

        msg = {
            "type": "confirm_required",
            "tool_name": payload.get("tool_name"),
            "agent_id": payload.get("agent_id"),
            "reason": payload.get("reason"),
            "correlation_id": corr_id,
            "timestamp": timestamp
        }

        logger.info(f"[FSM_WS_MANAGER] Broadcasting confirm_required to frontend: {msg}")
        await self.broadcast(msg)

    async def _on_state_change(self, envelope: EventEnvelope):
        payload = envelope.payload
        new_state = payload.get("new_state")
        corr_id = str(envelope.correlation_id)
        
        # Format timestamp to ISO8601
        if hasattr(envelope.timestamp, "isoformat"):
            timestamp = envelope.timestamp.isoformat()
            if not timestamp.endswith("Z"):
                timestamp += "Z"
        else:
            timestamp = str(envelope.timestamp)

        if not new_state:
            return

        msg = {
            "type": "fsm_state_change",
            "state": new_state,
            "correlation_id": corr_id,
            "timestamp": timestamp
        }

        logger.info(f"[FSM_WS_MANAGER] Broadcasting state change to frontend: {new_state} (correlation_id={corr_id})")
        await self.broadcast(msg)

    async def broadcast(self, message: dict):
        """Broadcast a message to all active FSM clients."""
        dead_connections = []
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.warning(f"[FSM_WS_MANAGER] Error sending message to connection: {e}")
                dead_connections.append(connection)

        for conn in dead_connections:
            self.active_connections.discard(conn)

fsm_ws_manager = FSMWebSocketManager()
