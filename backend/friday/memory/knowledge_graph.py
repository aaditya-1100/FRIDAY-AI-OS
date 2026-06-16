import sqlite3
import os
import networkx as nx
from typing import List, Dict, Any, Tuple
from loguru import logger

class KnowledgeGraph:
    def __init__(self, db_path: str = None):
        if db_path is None:
            base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "knowledge_graph.db"))
            worker_id = os.environ.get("PYTEST_XDIST_WORKER")
            if worker_id:
                self.db_path = f"{os.path.splitext(base_path)[0]}_{worker_id}.db"
            else:
                self.db_path = base_path
        else:
            self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        self.graph = nx.DiGraph()
        self._init_db()
        self.load()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS edges (
                source TEXT,
                relation TEXT,
                target TEXT,
                weight REAL,
                PRIMARY KEY (source, relation, target)
            )
        """)
        conn.commit()
        conn.close()

    def load(self) -> None:
        try:
            self.graph.clear()
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT source, relation, target, weight FROM edges")
            rows = cursor.fetchall()
            conn.close()
            
            for src, rel, tgt, w in rows:
                self.graph.add_edge(src, tgt, relation=rel, weight=w)
            logger.info(f"[KnowledgeGraph] Loaded {len(rows)} relations from SQLite.")
        except Exception as e:
            logger.error(f"[KnowledgeGraph] Failed to load graph: {e}")

    def save(self) -> None:
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM edges")
            
            edges_to_insert = []
            for u, v, data in self.graph.edges(data=True):
                rel = data.get("relation", "related_to")
                w = data.get("weight", 1.0)
                edges_to_insert.append((u, rel, v, w))
                
            cursor.executemany("""
                INSERT OR REPLACE INTO edges (source, relation, target, weight)
                VALUES (?, ?, ?, ?)
            """, edges_to_insert)
            conn.commit()
            conn.close()
            logger.info(f"[KnowledgeGraph] Saved {len(edges_to_insert)} relations to SQLite.")
        except Exception as e:
            logger.error(f"[KnowledgeGraph] Failed to save graph: {e}")

    def add_relation(self, source: str, relation: str, target: str, weight: float = 1.0) -> None:
        s = source.strip()
        t = target.strip()
        r = relation.strip()
        self.graph.add_edge(s, t, relation=r, weight=weight)
        self.save()

    def get_relations(self, entity: str) -> List[Tuple[str, str, str, float]]:
        ent = entity.strip()
        relations = []
        if self.graph.has_node(ent):
            for neighbor in self.graph.successors(ent):
                edge_data = self.graph.get_edge_data(ent, neighbor)
                rel = edge_data.get("relation", "related_to")
                w = edge_data.get("weight", 1.0)
                relations.append((ent, rel, neighbor, w))
            for parent in self.graph.predecessors(ent):
                edge_data = self.graph.get_edge_data(parent, ent)
                rel = edge_data.get("relation", "related_to")
                w = edge_data.get("weight", 1.0)
                relations.append((parent, rel, ent, w))
        return relations

    def clear(self) -> None:
        self.graph.clear()
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM edges")
        conn.commit()
        conn.close()
        logger.info("[KnowledgeGraph] Cleared graph store.")
prov = 1
