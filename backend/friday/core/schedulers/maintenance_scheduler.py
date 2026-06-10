import asyncio
from datetime import datetime
from loguru import logger
from uuid import uuid4
from friday.core.events import EventEnvelope, EventPriority
from friday.core.event_bus import event_bus
from friday.memory.consolidation import MemoryConsolidator

class MaintenanceScheduler:
    def __init__(self):
        self._running = False
        self._health_task = None
        self.consolidator = MemoryConsolidator()

    def start(self):
        self._running = True
        self._health_task = asyncio.create_task(self._health_loop())
        event_bus.subscribe("friday.system.session_end", self._on_session_end)
        logger.info("[MaintenanceScheduler] Started background maintenance tasks.")

    def stop(self):
        self._running = False
        if self._health_task:
            self._health_task.cancel()
        event_bus.unsubscribe("friday.system.session_end", self._on_session_end)
        logger.info("[MaintenanceScheduler] Stopped maintenance tasks.")

    async def _health_loop(self):
        while self._running:
            try:
                await asyncio.sleep(60)
                logger.info("[MaintenanceScheduler] Emitting 60s health tick.")
                
                envelope = EventEnvelope(
                    topic="friday.system.health_tick",
                    priority=EventPriority.P3,
                    source="system.maintenance_scheduler",
                    correlation_id=uuid4(),
                    session_id=uuid4(),
                    payload={
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                        "status": "HEALTHY"
                    }
                )
                await event_bus.publish(envelope)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[MaintenanceScheduler] Health loop error: {e}")

    async def _on_session_end(self, envelope: EventEnvelope):
        logger.info("[MaintenanceScheduler] Received session end event. Triggering memory consolidation.")
        try:
            asyncio.create_task(self.consolidator.consolidate())
        except Exception as e:
            logger.error(f"[MaintenanceScheduler] Consolidation trigger error: {e}")

maintenance_scheduler = MaintenanceScheduler()
