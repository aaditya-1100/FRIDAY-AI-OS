import sqlite3
import json
import os
from datetime import datetime
from typing import List, Dict, Any, Optional

class EpisodicMemory:
    def __init__(self, db_path: str = None):
        if db_path is None:
            base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "episodic.db"))
            worker_id = os.environ.get("PYTEST_XDIST_WORKER")
            if worker_id:
                self.db_path = f"{os.path.splitext(base_path)[0]}_{worker_id}.db"
            else:
                self.db_path = base_path
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
                metadata TEXT,
                app_id TEXT DEFAULT 'general'
            )
        """)
        try:
            cursor.execute("ALTER TABLE episodes ADD COLUMN app_id TEXT DEFAULT 'general'")
        except sqlite3.OperationalError:
            pass
        conn.commit()
        conn.close()

    def add_episode(self, query: str, intent: str, success: bool, salience_score: float, metadata: Dict[str, Any] = None, app_id: str = "general") -> int:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        meta_str = json.dumps(metadata or {})
        ts = datetime.utcnow().isoformat() + "Z"
        cursor.execute("""
            INSERT INTO episodes (timestamp, query, intent, success, salience_score, metadata, app_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (ts, query, intent, 1 if success else 0, salience_score, meta_str, app_id))
        episode_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return episode_id

    def get_recent_episodes(self, limit: int = 100, app_id: Optional[str] = None) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        if app_id:
            cursor.execute("""
                SELECT id, timestamp, query, intent, success, salience_score, metadata, app_id
                FROM episodes
                WHERE app_id = ?
                ORDER BY id DESC
                LIMIT ?
            """, (app_id, limit))
        else:
            cursor.execute("""
                SELECT id, timestamp, query, intent, success, salience_score, metadata, app_id
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
                "recency": 1.0,  # Ensure compatibility
                "salience_score": r[5],
                "metadata": json.loads(r[6]),
                "app_id": r[7]
            })
        return episodes

    def get_recent(self, limit: int = 100, app_id: Optional[str] = None) -> List[Dict[str, Any]]:
        return self.get_recent_episodes(limit=limit, app_id=app_id)

    def clear(self) -> None:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM episodes")
        conn.commit()
        conn.close()

