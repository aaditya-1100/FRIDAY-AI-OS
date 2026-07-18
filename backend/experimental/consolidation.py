import asyncio
from loguru import logger
from friday.memory.episodic import EpisodicMemory
from friday.memory.semantic import SemanticMemory
from friday.memory.knowledge_graph import KnowledgeGraph

class MemoryConsolidator:
    def __init__(self):
        self.episodic_store = EpisodicMemory()
        self.semantic_store = SemanticMemory()
        self.graph_store = KnowledgeGraph()

    async def consolidate(self) -> None:
        logger.info("[Consolidation] Starting post-session memory consolidation...")
        try:
            episodes = self.episodic_store.get_recent_episodes(limit=20)
            if not episodes:
                logger.info("[Consolidation] No episodes found to consolidate.")
                return
            
            total = len(episodes)
            success_count = sum(1 for ep in episodes if ep.get("success"))
            intents = set(ep.get("intent") for ep in episodes if ep.get("intent"))
            
            summary_fact = (
                f"During the last session, the user performed {total} commands with a "
                f"{success_count/total * 100:.1f}% success rate. "
                f"Intents executed: {', '.join(intents)}."
            )
            
            self.semantic_store.add_fact(
                summary_fact, 
                metadata={"type": "consolidation_summary", "count": total}
            )
            
            logger.info(f"[Consolidation] Consolidation complete. Fact added: '{summary_fact}'")
        except Exception as e:
            logger.error(f"[Consolidation] Error during consolidation: {e}", exc_info=True)
