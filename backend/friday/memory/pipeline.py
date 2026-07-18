from typing import Dict, Any, List, Optional
from loguru import logger
from friday.memory.episodic import EpisodicMemory
from friday.memory.semantic import SemanticMemory

class MemoryPipeline:
    def __init__(self):
        self.episodic_store = EpisodicMemory()
        self.semantic_store = SemanticMemory()

    def calculate_salience(self, novelty: float, goal_relevance: float, emotional_weight: float, recency: float) -> float:
        """
        Salience formula:
        score = (0.3 * novelty) + (0.3 * goal_relevance) + (0.2 * emotional_weight) + (0.2 * recency)
        """
        score = (0.3 * novelty) + (0.3 * goal_relevance) + (0.2 * emotional_weight) + (0.2 * recency)
        return float(score)

    def extract_entities(self, text: str) -> List[Dict[str, str]]:
        return []

    def extract_relations(self, text: str) -> List[Dict[str, str]]:
        return []

    def process_memory_formation(
        self,
        query: str,
        intent: str,
        success: bool,
        novelty: float = 0.5,
        goal_relevance: float = 0.5,
        emotional_weight: float = 0.0,
        recency: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None,
        app_id: str = "general"
    ) -> Dict[str, Any]:
        entities = []
        relations = []

        score = self.calculate_salience(novelty, goal_relevance, emotional_weight, recency)
        logger.info(f"[MemoryPipeline] Processing memory for '{query}' (intent={intent}). Calculated salience: {score:.3f}")
        
        if score < 0.25:
            logger.info(f"[MemoryPipeline] Salience {score:.3f} is below threshold (0.25). Discarding memory storage.")
            return {
                "salience_score": score,
                "status": "discarded",
                "entities": entities,
                "relations": relations
            }
        
        full_metadata = metadata or {}
        full_metadata.update({
            "entities": entities,
            "relations": relations,
            "novelty": novelty,
            "goal_relevance": goal_relevance,
            "emotional_weight": emotional_weight,
            "recency": recency
        })

        # Save to stores
        episode_id = self.episodic_store.add_episode(query, intent, success, score, full_metadata, app_id=app_id)
        
        # Save semantic fact
        semantic_text = f"User query: {query}. Intent detected: {intent}."
        self.semantic_store.add_fact(semantic_text, metadata={"episode_id": episode_id, "intent": intent, "success": success}, app_id=app_id)

        return {
            "salience_score": score,
            "status": "stored",
            "episode_id": episode_id,
            "entities": entities,
            "relations": relations
        }

# Global Memory Pipeline instance
memory_pipeline = MemoryPipeline()
