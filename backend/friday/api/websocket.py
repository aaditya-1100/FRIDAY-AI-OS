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
        event_bus.subscribe("friday.system.activity", self._on_activity)
        event_bus.subscribe("friday.core.proactive_trigger", self._on_proactive_trigger)
        event_bus.subscribe("friday.system.context_update", self._on_context_update)
        logger.info("[FSM_WS_MANAGER] Subscribed to FSM, activity, proactive and context events.")

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

        working_memory = payload.get("working_memory") or {}
        plan_type = working_memory.get("plan_type")
        active_agent = None
        if plan_type == "SINGLE":
            active_agent = working_memory.get("agent_type")
        elif plan_type == "MULTI":
            actions = working_memory.get("parsed_intent", {}).get("actions", [])
            if actions and isinstance(actions, list):
                from friday.core.routing_table import INTENT_TO_AGENT
                first_action = actions[0]
                sub_intent = first_action.get("intent")
                active_agent = INTENT_TO_AGENT.get(sub_intent, "PC_AGENT")

        msg = {
            "type": "fsm_state_change",
            "state": new_state,
            "correlation_id": corr_id,
            "timestamp": timestamp,
            "active_agent": active_agent
        }

        logger.info(f"[FSM_WS_MANAGER] Broadcasting state change to frontend: {new_state} (correlation_id={corr_id}) with active_agent={active_agent}")
        asyncio.create_task(self.broadcast(msg))

    async def _on_activity(self, envelope: EventEnvelope):
        payload = envelope.payload
        if hasattr(envelope.timestamp, "isoformat"):
            timestamp = envelope.timestamp.isoformat()
            if not timestamp.endswith("Z"):
                timestamp += "Z"
        else:
            timestamp = str(envelope.timestamp)

        msg = {
            "type": "activity",
            "payload": payload,
            "correlation_id": str(envelope.correlation_id),
            "timestamp": timestamp
        }
        await self.broadcast(msg)

    async def _on_proactive_trigger(self, envelope: EventEnvelope):
        payload = envelope.payload
        if hasattr(envelope.timestamp, "isoformat"):
            timestamp = envelope.timestamp.isoformat()
            if not timestamp.endswith("Z"):
                timestamp += "Z"
        else:
            timestamp = str(envelope.timestamp)

        msg = {
            "type": "proactive_trigger",
            "message": payload.get("message"),
            "rule": payload.get("rule"),
            "payload": payload,
            "correlation_id": str(envelope.correlation_id),
            "timestamp": timestamp
        }
        logger.info(f"[FSM_WS_MANAGER] Broadcasting proactive_trigger to frontend: {msg}")
        await self.broadcast(msg)

    async def _on_context_update(self, envelope: EventEnvelope):
        payload = envelope.payload
        if hasattr(envelope.timestamp, "isoformat"):
            timestamp = envelope.timestamp.isoformat()
            if not timestamp.endswith("Z"):
                timestamp += "Z"
        else:
            timestamp = str(envelope.timestamp)

        msg = {
            "type": "context_update",
            "payload": payload,
            "correlation_id": str(envelope.correlation_id),
            "timestamp": timestamp
        }
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
