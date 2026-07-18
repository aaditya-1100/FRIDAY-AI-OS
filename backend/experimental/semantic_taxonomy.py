"""
semantic_taxonomy.py — FRIDAY Dynamic Semantic Taxonomy Layer
==============================================================
Manages configuration-driven hierarchical interest categories, synonym translations,
and negative constraint propagation utilizing directed acyclic graph (DAG) DFS traversal.
"""

import os
import json

class SemanticTaxonomy:
    """
    SemanticTaxonomy: Dynamic, versioned interest DAG manager.
    Loads category structures from JSON, enabling dynamic descendant suppression.
    """
    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)), 
                "data", 
                "semantic_taxonomy.json"
            )
        self.config_path = config_path
        self.version = "1.0"
        self.nodes = {}
        self.synonym_map = {}
        self.load()

    def load(self) -> None:
        """Loads versioned JSON node connections and compiles the synonym index."""
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Taxonomy config not found at: {self.config_path}")
            
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.version = data.get("version", "1.0")
                self.nodes = data.get("nodes", {})
                
            # Compile synonym lookup maps
            self.synonym_map = {}
            for canonical, metadata in self.nodes.items():
                # Node itself is its own canonical mapping
                self.synonym_map[canonical.lower()] = canonical.lower()
                # Add listed synonyms
                for syn in metadata.get("synonyms", []):
                    self.synonym_map[syn.lower()] = canonical.lower()
                    
            print(f"[TAXONOMY] Version {self.version} loaded successfully. Nodes count: {len(self.nodes)}.")
        except Exception as e:
            print(f"[TAXONOMY ERROR] Failed to load taxonomy JSON: {e}")
            raise e

    def translate_synonym(self, term: str) -> str:
        """Translates a raw text query term to its canonical taxonomy node."""
        term_clean = term.lower().strip()
        return self.synonym_map.get(term_clean, term_clean)

    def get_descendants(self, root_name: str) -> set[str]:
        """
        Executes a Breadth-First Search (BFS) to gather all canonical descendant sub-nodes.
        E.g. "technology" -> {"technology", "ai", "robotics", "automation", "programming", "python", "rust", ...}
        """
        canonical_root = self.translate_synonym(root_name)
        descendants = {canonical_root}
        queue = [canonical_root]
        
        while queue:
            curr = queue.pop(0)
            if curr in self.nodes:
                for child in self.nodes[curr].get("children", []):
                    canonical_child = self.translate_synonym(child)
                    if canonical_child not in descendants:
                        descendants.add(canonical_child)
                        queue.append(canonical_child)
                        
        return descendants

    def check_suppression(self, interest: str, negated_constraints: list[str]) -> bool:
        """
        Returns True if the interest is a descendant of any negated domain constraints.
        E.g. interest="AI systems", negated_constraints=["technology"] -> returns True
        """
        canonical_interest = self.translate_synonym(interest)
        
        for negated in negated_constraints:
            suppression_set = self.get_descendants(negated)
            if canonical_interest in suppression_set:
                return True
                
        return False
