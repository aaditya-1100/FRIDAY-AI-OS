import asyncio
from typing import Dict, Any, List
from loguru import logger
from friday.core.events import AgentType, TaskDispatch, TaskResult, TaskStatus
from friday.agents.base_agent import BaseAgent
from friday.memory.semantic import SemanticMemory
from friday.memory.knowledge_graph import KnowledgeGraph

class KnowledgeAgent(BaseAgent):
    def __init__(self):
        super().__init__(AgentType.KNOWLEDGE_AGENT)
        self.semantic = SemanticMemory()
        self.graph = KnowledgeGraph()

    async def startup(self) -> None:
        logger.info("[KnowledgeAgent] Startup complete.")

    async def shutdown(self) -> None:
        logger.info("[KnowledgeAgent] Shutdown complete.")

    def get_capabilities(self) -> list[str]:
        return ["RETRIEVE_SEMANTIC", "QUERY_GRAPH", "ADD_FACT", "ADD_RELATION"]

    async def handle_task(self, dispatch: TaskDispatch) -> TaskResult:
        intent = dispatch.intent
        params = dispatch.parameters
        
        try:
            logger.info(f"[KnowledgeAgent] Executing knowledge action: {intent}")
            
            if intent == "RETRIEVE_SEMANTIC":
                query = params.get("query", "")
                limit = params.get("limit", 3)
                hits = self.semantic.search(query, limit=limit)
                return TaskResult(
                    task_id=dispatch.task_id,
                    agent_id=self.agent_id,
                    status=TaskStatus.SUCCESS,
                    payload={"hits": hits},
                    correlation_id=dispatch.correlation_id
                )
                
            elif intent == "QUERY_GRAPH":
                entity = params.get("entity", "")
                relations = self.graph.get_relations(entity)
                
                formatted = []
                for s, r, t, w in relations:
                    formatted.append({
                        "source": s,
                        "relation": r,
                        "target": t,
                        "weight": w
                    })
                    
                return TaskResult(
                    task_id=dispatch.task_id,
                    agent_id=self.agent_id,
                    status=TaskStatus.SUCCESS,
                    payload={"relations": formatted},
                    correlation_id=dispatch.correlation_id
                )
                
            elif intent == "ADD_FACT":
                text = params.get("text", "")
                metadata = params.get("metadata", {})
                self.semantic.add_fact(text, metadata=metadata)
                return TaskResult(
                    task_id=dispatch.task_id,
                    agent_id=self.agent_id,
                    status=TaskStatus.SUCCESS,
                    payload={"status": "Fact added successfully"},
                    correlation_id=dispatch.correlation_id
                )
                
            elif intent == "ADD_RELATION":
                source = params.get("source", "")
                relation = params.get("relation", "")
                target = params.get("target", "")
                weight = params.get("weight", 1.0)
                
                self.graph.add_relation(source, relation, target, weight=weight)
                return TaskResult(
                    task_id=dispatch.task_id,
                    agent_id=self.agent_id,
                    status=TaskStatus.SUCCESS,
                    payload={"status": "Relation added successfully"},
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
            logger.error(f"[KnowledgeAgent] Error executing knowledge task: {e}", exc_info=True)
            return TaskResult(
                task_id=dispatch.task_id,
                agent_id=self.agent_id,
                status=TaskStatus.FAILED,
                payload={"error": str(e)},
                correlation_id=dispatch.correlation_id
            )
