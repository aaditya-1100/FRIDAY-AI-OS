import spacy
from typing import Dict, Any, List, Optional
from loguru import logger
from friday.memory.episodic import EpisodicMemory
from friday.memory.semantic import SemanticMemory
from friday.memory.knowledge_graph import KnowledgeGraph

class MemoryPipeline:
    def __init__(self):
        from brain.spacy_loader import get_spacy_model
        self.nlp = get_spacy_model()
        if self.nlp is None:
            logger.info("[MemoryPipeline] spaCy en_core_web_sm not found, downloading...")
            try:
                from spacy import cli as spacy_cli
                spacy_cli.download("en_core_web_sm")
                import spacy
                # Load and cache in the unified spacy_loader
                import brain.spacy_loader as sl
                sl._nlp_model = spacy.load("en_core_web_sm")
                self.nlp = sl._nlp_model
                logger.info("[MemoryPipeline] Loaded spaCy en_core_web_sm successfully after download.")
            except Exception as e:
                logger.error(f"[MemoryPipeline] Failed to download/load spaCy model: {e}")
                self.nlp = None

        self.episodic_store = EpisodicMemory()
        self.semantic_store = SemanticMemory()
        self.graph_store = KnowledgeGraph()

    def calculate_salience(self, novelty: float, goal_relevance: float, emotional_weight: float, recency: float) -> float:
        """
        Salience formula:
        score = (0.3 * novelty) + (0.3 * goal_relevance) + (0.2 * emotional_weight) + (0.2 * recency)
        """
        score = (0.3 * novelty) + (0.3 * goal_relevance) + (0.2 * emotional_weight) + (0.2 * recency)
        return float(score)

    def extract_entities(self, text: str) -> List[Dict[str, str]]:
        if not self.nlp:
            return []
        doc = self.nlp(text)
        entities = []
        for ent in doc.ents:
            entities.append({
                "text": ent.text,
                "label": ent.label_
            })
        return entities

    def extract_relations(self, text: str) -> List[Dict[str, str]]:
        if not self.nlp:
            return []
        doc = self.nlp(text)
        relations = []
        for token in doc:
            if token.dep_ == "ROOT" and token.pos_ in ("VERB", "AUX"):
                subj = None
                obj = None
                relation_text = token.text
                for child in token.children:
                    if child.dep_ in ("nsubj", "nsubjpass"):
                        subj = child.text
                    elif child.dep_ in ("dobj", "pobj", "attr", "oprd", "acomp"):
                        obj = child.text
                    elif child.dep_ == "prep":
                        for grandchild in child.children:
                            if grandchild.dep_ == "pobj":
                                obj = grandchild.text
                                relation_text = f"{token.text} {child.text}"
                if subj and obj:
                    relations.append({
                        "source": subj,
                        "relation": relation_text,
                        "target": obj
                    })
        return relations

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
        # Extract entities and relations (always run regardless of salience)
        entities = self.extract_entities(query)
        relations = self.extract_relations(query)

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

        # Save relation to knowledge graph
        for rel in relations:
            self.graph_store.add_relation(rel["source"], rel["relation"], rel["target"], weight=score)

        return {
            "salience_score": score,
            "status": "stored",
            "episode_id": episode_id,
            "entities": entities,
            "relations": relations
        }

# Global Memory Pipeline instance
memory_pipeline = MemoryPipeline()
