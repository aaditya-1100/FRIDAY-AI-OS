import asyncio
from typing import Dict, Any, List
from loguru import logger
from friday.core.events import AgentType, TaskDispatch, TaskResult, TaskStatus, EventEnvelope, EventPriority
from friday.core.event_bus import event_bus
from friday.agents.base_agent import BaseAgent
from friday.memory.working import WorkingMemory
from friday.memory.session import SessionMemory
from friday.memory.episodic import EpisodicMemory
from friday.memory.semantic import SemanticMemory
from friday.memory.knowledge_graph import KnowledgeGraph
from friday.memory.pipeline import memory_pipeline
from friday.memory.consolidation import MemoryConsolidator

class MemoryAgent(BaseAgent):
    def __init__(self):
        super().__init__(AgentType.MEMORY_AGENT)
        self.working = WorkingMemory()
        self.session = SessionMemory()
        self.episodic = EpisodicMemory()
        self.semantic = SemanticMemory()
        self.graph = KnowledgeGraph()
        self.consolidator = MemoryConsolidator()

    async def startup(self) -> None:
        event_bus.subscribe("friday.memory.write", self.on_memory_write)
        logger.info("[MemoryAgent] Subscribed to friday.memory.write. Startup complete.")

    async def shutdown(self) -> None:
        event_bus.unsubscribe("friday.memory.write", self.on_memory_write)
        logger.info("[MemoryAgent] Unsubscribed from friday.memory.write. Shutdown complete.")

    async def on_memory_write(self, envelope: EventEnvelope) -> None:
        payload = envelope.payload
        logger.info(f"[MemoryAgent] Received memory.write event for correlation_id={envelope.correlation_id}")
        
        query = payload.get("raw_input") or payload.get("query") or ""
        intent = payload.get("intent") or "AI_QUERY"
        success = payload.get("success", True)
        
        novelty = payload.get("novelty", 0.6)
        goal_relevance = payload.get("goal_relevance", 0.6)
        emotional_weight = payload.get("emotional_weight", 0.0)
        recency = payload.get("recency", 1.0)
        metadata = payload.get("metadata", {})
        
        full_metadata = {
            "response": payload.get("response", ""),
            "confidence": payload.get("confidence", 1.0),
            "agent_results": payload.get("agent_results", []),
            "session_id": str(envelope.session_id),
            "correlation_id": str(envelope.correlation_id),
            "timestamp": payload.get("timestamp", "")
        }
        full_metadata.update(metadata)
        
        # Get app_id from system context
        from friday.system.context import system_context
        app_id = system_context.get_context().get("app_id", "general")
        
        # Run pipeline in threadpool (since it uses spacy and is CPU-bound)
        loop = asyncio.get_running_loop()
        res = await loop.run_in_executor(
            None,
            lambda: memory_pipeline.process_memory_formation(
                query=query,
                intent=intent,
                success=success,
                novelty=novelty,
                goal_relevance=goal_relevance,
                emotional_weight=emotional_weight,
                recency=recency,
                metadata=full_metadata,
                app_id=app_id
            )
        )
        
        logger.info(f"[MemoryAgent] Memory formation complete for correlation_id={envelope.correlation_id}. Status: {res.get('status')}")
        
        # Publish write_complete for observability
        complete_envelope = EventEnvelope(
            topic="friday.memory.write_complete",
            priority=EventPriority.P3,
            source="agent.memory",
            correlation_id=envelope.correlation_id,
            session_id=envelope.session_id,
            payload=res
        )
        await event_bus.publish(complete_envelope)

    def get_capabilities(self) -> list[str]:
        return ["WRITE_MEMORY", "READ_MEMORY", "CONSOLIDATE", "LOAD_SESSION_CONTEXT"]

    async def handle_task(self, dispatch: TaskDispatch) -> TaskResult:
        intent = dispatch.intent
        params = dispatch.parameters
        
        try:
            logger.info(f"[MemoryAgent] Executing memory action: {intent}")
            
            if intent == "WRITE_MEMORY":
                query = params.get("query", "")
                task_intent = params.get("task_intent", "")
                success = params.get("success", True)
                novelty = params.get("novelty", 0.5)
                goal_relevance = params.get("goal_relevance", 0.5)
                emotional_weight = params.get("emotional_weight", 0.0)
                recency = params.get("recency", 1.0)
                metadata = params.get("metadata", {})
                
                from friday.system.context import system_context
                app_id = system_context.get_context().get("app_id", "general")
                
                res = memory_pipeline.process_memory_formation(
                    query=query,
                    intent=task_intent,
                    success=success,
                    novelty=novelty,
                    goal_relevance=goal_relevance,
                    emotional_weight=emotional_weight,
                    recency=recency,
                    metadata=metadata,
                    app_id=app_id
                )
                
                return TaskResult(
                    task_id=dispatch.task_id,
                    agent_id=self.agent_id,
                    status=TaskStatus.SUCCESS,
                    payload=res,
                    correlation_id=dispatch.correlation_id
                )
                
            elif intent == "READ_MEMORY":
                store_type = params.get("store", "working")
                key = params.get("key", "")
                limit = params.get("limit", 10)
                
                if store_type == "working":
                    val = self.working.get(key)
                    payload = {"key": key, "value": val}
                elif store_type == "session":
                    val = self.session.get(key)
                    payload = {"key": key, "value": val}
                elif store_type == "episodic":
                    episodes = self.episodic.get_recent_episodes(limit=limit)
                    payload = {"episodes": episodes}
                else:
                    payload = {"error": f"Unknown store type: {store_type}"}
                    
                return TaskResult(
                    task_id=dispatch.task_id,
                    agent_id=self.agent_id,
                    status=TaskStatus.SUCCESS,
                    payload=payload,
                    correlation_id=dispatch.correlation_id
                )
                
            elif intent == "LOAD_SESSION_CONTEXT":
                recent = self.episodic.get_recent_episodes(limit=3)
                self.working.set("prior_episodes", recent)
                self.session.set("prior_episodes", recent)
                
                logger.info(f"[MemoryAgent] Loaded {len(recent)} prior episodes into session/working memory.")
                return TaskResult(
                    task_id=dispatch.task_id,
                    agent_id=self.agent_id,
                    status=TaskStatus.SUCCESS,
                    payload={"loaded_count": len(recent), "episodes": recent},
                    correlation_id=dispatch.correlation_id
                )
                
            elif intent == "CONSOLIDATE":
                await self.consolidator.consolidate()
                return TaskResult(
                    task_id=dispatch.task_id,
                    agent_id=self.agent_id,
                    status=TaskStatus.SUCCESS,
                    payload={"status": "Consolidation complete"},
                    correlation_id=dispatch.correlation_id
                )
                
            else:
                return TaskResult(
                    task_id=dispatch.task_id,
                    agent_id=self.agent_id,
                    status=TaskStatus.FAILED,
                    payload={"error": f"Unsupported intent: {intent}"},
                    correlation_id=dispatch.correlation_id
                )
                
        except Exception as e:
            logger.error(f"[MemoryAgent] Error executing memory task: {e}", exc_info=True)
            return TaskResult(
                task_id=dispatch.task_id,
                agent_id=self.agent_id,
                status=TaskStatus.FAILED,
                payload={"error": str(e)},
                correlation_id=dispatch.correlation_id
            )
