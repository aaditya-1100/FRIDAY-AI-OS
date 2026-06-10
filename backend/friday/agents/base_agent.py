import abc
import asyncio
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4
from loguru import logger
from friday.core.events import AgentType, AgentStatus, EventPriority, TaskDispatch, TaskResult, EventEnvelope, TaskStatus, AgentTrustLevel
from friday.core.event_bus import event_bus
from friday.security.capability_registry import AGENT_TRUST_MAP

class BaseAgent(abc.ABC):
    def __init__(self, agent_type: AgentType, trust_level: Optional[AgentTrustLevel] = None):
        self.agent_id: UUID = uuid4()
        self.agent_type: AgentType = agent_type
        self.trust_level: AgentTrustLevel = trust_level or AGENT_TRUST_MAP.get(agent_type, AgentTrustLevel.STANDARD)
        self.status: AgentStatus = AgentStatus.IDLE
        self._task_queue: asyncio.Queue = asyncio.Queue()
        self._running: bool = False
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._receive_task: Optional[asyncio.Task] = None

    @abc.abstractmethod
    async def startup(self) -> None:
        """Initialize connections, register capabilities on event bus."""
        pass

    @abc.abstractmethod
    async def shutdown(self) -> None:
        """Clean up, publish AGENT_OFFLINE event."""
        pass

    @abc.abstractmethod
    async def handle_task(self, dispatch: TaskDispatch) -> TaskResult:
        """Core task execution."""
        pass

    @abc.abstractmethod
    def get_capabilities(self) -> list[str]:
        """Return declared capability strings."""
        pass

    async def start(self):
        """Enforces lifecycle start. Spawns agent, runs startup, publishes ONLINE, enters loop."""
        self._running = True
        await self.startup()
        
        # Subscribe to dispatch topic: friday.agent.{agent_type.lower()}.dispatch
        dispatch_topic = f"friday.agent.{self.agent_type.value.lower()}.dispatch"
        event_bus.subscribe(dispatch_topic, self._on_dispatch_event)

        # Publish AGENT_ONLINE event
        await self._publish_agent_online()

        # Start heartbeat and receive tasks
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        self._receive_task = asyncio.create_task(self._receive_loop())
        logger.info(f"[AGENT] {self.agent_type.value} (id={self.agent_id}) started successfully.")

    async def stop(self):
        """Enforces lifecycle stop. Cleans up subscription, heartbeats, calls shutdown."""
        if not self._running:
            return
        self._running = False
        
        # Unsubscribe
        dispatch_topic = f"friday.agent.{self.agent_type.value.lower()}.dispatch"
        event_bus.unsubscribe(dispatch_topic, self._on_dispatch_event)

        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        if self._receive_task:
            self._receive_task.cancel()

        await self.shutdown()
        await self._publish_agent_offline()
        logger.info(f"[AGENT] {self.agent_type.value} (id={self.agent_id}) stopped.")

    async def _on_dispatch_event(self, envelope: EventEnvelope):
        """Callback when dispatch event is received."""
        try:
            # Check if this dispatch is for terminate/shutdown
            if envelope.payload.get("command") == "TERMINATE":
                logger.info(f"[AGENT] Received TERMINATE command. Stopping...")
                await self.stop()
                return

            dispatch = TaskDispatch(**envelope.payload)
            await self._task_queue.put(dispatch)
        except Exception as e:
            logger.error(f"[AGENT] Error parsing TaskDispatch payload: {e}")

    async def _receive_loop(self):
        """Task queue consumer loop."""
        while self._running:
            try:
                dispatch = await self._task_queue.get()
                self.status = AgentStatus.BUSY
                start_time = asyncio.get_event_loop().time()
                
                try:
                    logger.info(f"[AGENT] {self.agent_type.value} executing intent: '{dispatch.intent}' (task_id={dispatch.task_id})")
                    # Enforce timeout if specified
                    timeout_seconds = dispatch.timeout_ms / 1000.0
                    result = await asyncio.wait_for(self.handle_task(dispatch), timeout=timeout_seconds)
                except asyncio.TimeoutError:
                    logger.warning(f"[AGENT] Task {dispatch.task_id} timed out.")
                    result = TaskResult(
                        task_id=dispatch.task_id,
                        agent_id=self.agent_id,
                        status=TaskStatus.TIMEOUT,
                        payload={"error": "Task execution timed out"},
                        correlation_id=dispatch.correlation_id
                    )
                except Exception as e:
                    logger.error(f"[AGENT] Exception in handle_task: {e}", exc_info=True)
                    self.status = AgentStatus.FAILED
                    result = TaskResult(
                        task_id=dispatch.task_id,
                        agent_id=self.agent_id,
                        status=TaskStatus.FAILED,
                        payload={"error": str(e)},
                        correlation_id=dispatch.correlation_id
                    )

                end_time = asyncio.get_event_loop().time()
                result.latency_ms = int((end_time - start_time) * 1000)

                # Reset status back to IDLE unless it failed
                if self.status != AgentStatus.FAILED:
                    self.status = AgentStatus.IDLE

                # Publish result
                result_topic = f"friday.agent.{self.agent_type.value.lower()}.result"
                envelope = EventEnvelope(
                    topic=result_topic,
                    priority=EventPriority.P2,
                    source=f"agent.{self.agent_type.value.lower()}",
                    correlation_id=dispatch.correlation_id,
                    session_id=dispatch.session_id,
                    payload=result.model_dump()
                )
                await event_bus.publish(envelope)
                self._task_queue.task_done()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[AGENT_RECEIVE_LOOP_ERROR] {e}")

    async def _heartbeat_loop(self):
        """Publishes heartbeat every 30 seconds."""
        while self._running:
            try:
                await asyncio.sleep(30)
                envelope = EventEnvelope(
                    topic="friday.system.heartbeat",
                    priority=EventPriority.P3,
                    source=f"agent.{self.agent_type.value.lower()}",
                    correlation_id=uuid4(),
                    session_id=uuid4(),
                    payload={
                        "agent_id": str(self.agent_id),
                        "agent_type": self.agent_type.value,
                        "status": self.status.value,
                        "timestamp": datetime.utcnow().isoformat() + "Z"
                    }
                )
                await event_bus.publish(envelope)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[AGENT_HEARTBEAT_ERROR] {e}")

    async def _publish_agent_online(self):
        envelope = EventEnvelope(
            topic="friday.system.agent_online",
            priority=EventPriority.P2,
            source=f"agent.{self.agent_type.value.lower()}",
            correlation_id=uuid4(),
            session_id=uuid4(),
            payload={
                "agent_id": str(self.agent_id),
                "agent_type": self.agent_type.value,
                "capabilities": self.get_capabilities()
            }
        )
        await event_bus.publish(envelope)

    async def _publish_agent_offline(self):
        envelope = EventEnvelope(
            topic="friday.system.agent_offline",
            priority=EventPriority.P2,
            source=f"agent.{self.agent_type.value.lower()}",
            correlation_id=uuid4(),
            session_id=uuid4(),
            payload={
                "agent_id": str(self.agent_id),
                "agent_type": self.agent_type.value
            }
        )
        await event_bus.publish(envelope)
