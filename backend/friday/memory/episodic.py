import sqlite3
import json
import os
from datetime import datetime
from typing import List, Dict, Any

class EpisodicMemory:
    def __init__(self, db_path: str = None):
        if db_path is None:
            self.db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "episodic.db"))
        else:
            self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS episodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                query TEXT,
                intent TEXT,
                success INTEGER,
                salience_score REAL,
                metadata TEXT
            )
        """)
        conn.commit()
        conn.close()

    def add_episode(self, query: str, intent: str, success: bool, salience_score: float, metadata: Dict[str, Any] = None) -> int:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        meta_str = json.dumps(metadata or {})
        ts = datetime.utcnow().isoformat() + "Z"
        cursor.execute("""
            INSERT INTO episodes (timestamp, query, intent, success, salience_score, metadata)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (ts, query, intent, 1 if success else 0, salience_score, meta_str))
        episode_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return episode_id

    def get_recent_episodes(self, limit: int = 100) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, timestamp, query, intent, success, salience_score, metadata
            FROM episodes
            ORDER BY id DESC
            LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()
        conn.close()
        
        episodes = []
        for r in rows:
            episodes.append({
                "id": r[0],
                "timestamp": r[1],
                "query": r[2],
                "intent": r[3],
                "success": bool(r[4]),
                "salience_score": r[5],
                "metadata": json.loads(r[6])
            })
        return episodes

    def get_recent(self, limit: int = 100) -> List[Dict[str, Any]]:
        return self.get_recent_episodes(limit=limit)

    def clear(self) -> None:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM episodes")
        conn.commit()
        conn.close()

