import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional
from uuid import UUID
from loguru import logger
from friday.core.events import AgentType, AgentStatus, EventEnvelope
from friday.core.event_bus import event_bus

class AgentRecord:
    def __init__(self, agent_id: UUID, agent_type: AgentType, capabilities: List[str]):
        self.agent_id: UUID = agent_id
        self.agent_type: AgentType = agent_type
        self.capabilities: List[str] = capabilities
        self.status: AgentStatus = AgentStatus.IDLE
        self.last_heartbeat: datetime = datetime.utcnow()

class AgentRegistry:
    def __init__(self):
        self.agents: Dict[str, AgentRecord] = {}

    def start(self):
        """Subscribe to agent monitoring events on the event bus."""
        event_bus.subscribe("friday.system.agent_online", self._on_agent_online)
        event_bus.subscribe("friday.system.agent_offline", self._on_agent_offline)
        event_bus.subscribe("friday.system.heartbeat", self._on_heartbeat)
        logger.info("[AGENT_REGISTRY] Subscribed to agent monitoring events.")

    async def _on_agent_online(self, envelope: EventEnvelope):
        payload = envelope.payload
        agent_id_str = payload.get("agent_id")
        agent_type_str = payload.get("agent_type")
        capabilities = payload.get("capabilities", [])

        if agent_id_str and agent_type_str:
            agent_id = UUID(agent_id_str)
            agent_type = AgentType(agent_type_str)
            record = AgentRecord(agent_id, agent_type, capabilities)
            self.agents[agent_id_str] = record
            logger.info(f"[REGISTRY] Agent registered: {agent_type.value} ({agent_id_str})")

    async def _on_agent_offline(self, envelope: EventEnvelope):
        payload = envelope.payload
        agent_id_str = payload.get("agent_id")
        if agent_id_str in self.agents:
            del self.agents[agent_id_str]
            logger.info(f"[REGISTRY] Agent deregistered: {agent_id_str}")

    async def _on_heartbeat(self, envelope: EventEnvelope):
        payload = envelope.payload
        agent_id_str = payload.get("agent_id")
        status_str = payload.get("status", "IDLE")
        
        if agent_id_str in self.agents:
            record = self.agents[agent_id_str]
            record.status = AgentStatus(status_str)
            record.last_heartbeat = datetime.utcnow()
            logger.debug(f"[REGISTRY] Heartbeat received from {record.agent_type.value} ({agent_id_str}): Status={status_str}")

    def verify_heartbeats(self) -> List[AgentRecord]:
        """
        Check for missed heartbeats (older than 65s, representing 2 ticks).
        Marks expired agents as FAILED and returns them for respawning.
        """
        now = datetime.utcnow()
        failed_agents = []
        for agent_id_str, record in list(self.agents.items()):
            delta = (now - record.last_heartbeat).total_seconds()
            if delta > 65.0 and record.status != AgentStatus.FAILED:
                record.status = AgentStatus.FAILED
                failed_agents.append(record)
                logger.warning(
                    f"[REGISTRY] Agent {record.agent_type.value} ({agent_id_str}) missed "
                    f"heartbeats for {delta:.1f}s. Marked as FAILED."
                )
        return failed_agents

# Global singleton agent registry
agent_registry = AgentRegistry()
