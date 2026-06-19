import json
import sqlite3
import os
from typing import Any, Optional
from loguru import logger

class SessionMemory:
    def __init__(self, host: str = "127.0.0.1", port: int = 6379, db: int = 0):
        self.redis_client = None
        base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "session_fallback.db"))
        worker_id = os.environ.get("PYTEST_XDIST_WORKER")
        if worker_id:
            self.sqlite_path = f"{os.path.splitext(base_path)[0]}_{worker_id}.db"
        else:
            self.sqlite_path = base_path
        os.makedirs(os.path.dirname(self.sqlite_path), exist_ok=True)
        
        try:
            import redis
            self.redis_client = redis.Redis(
                host=host, 
                port=port, 
                db=db, 
                decode_responses=True, 
                socket_timeout=0.1,
                socket_connect_timeout=0.1
            )
            self.redis_client.ping()
            logger.info("Session store: Redis active")
        except Exception as e:
            logger.info("Session store: SQLite fallback active")
            self.redis_client = None

            
        self._init_sqlite()

    def _init_sqlite(self):
        conn = sqlite3.connect(self.sqlite_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS session_store (
                key TEXT PRIMARY KEY,
                value TEXT,
                app_id TEXT DEFAULT 'general'
            )
        """)
        try:
            cursor.execute("ALTER TABLE session_store ADD COLUMN app_id TEXT DEFAULT 'general'")
        except sqlite3.OperationalError:
            pass
        conn.commit()
        conn.close()

    def _namespace_key(self, key: str, app_id: Optional[str] = None) -> str:
        if key == "conversation_history":
            if app_id is None:
                try:
                    from friday.system.context import system_context
                    app_id = system_context.get_context().get("app_id", "general")
                except Exception:
                    app_id = "general"
            return f"conversation_history_{app_id}"
        return key

    def set(self, key: str, value: Any, ex: Optional[int] = None, app_id: Optional[str] = None) -> None:
        if app_id is None:
            try:
                from friday.system.context import system_context
                app_id = system_context.get_context().get("app_id", "general")
            except Exception:
                app_id = "general"
        key = self._namespace_key(key, app_id)
        val_str = json.dumps(value)
        if self.redis_client:
            try:
                self.redis_client.set(key, val_str, ex=ex)
                return
            except Exception as e:
                logger.warning(f"[SessionMemory] Redis write failed, falling back to SQLite: {e}")
        
        conn = sqlite3.connect(self.sqlite_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO session_store (key, value, app_id)
            VALUES (?, ?, ?)
        """, (key, val_str, app_id))
        conn.commit()
        conn.close()

    def get(self, key: str, default: Any = None, app_id: Optional[str] = None) -> Any:
        if app_id is None:
            try:
                from friday.system.context import system_context
                app_id = system_context.get_context().get("app_id", "general")
            except Exception:
                app_id = "general"
        key = self._namespace_key(key, app_id)
        if self.redis_client:
            try:
                val_str = self.redis_client.get(key)
                if val_str is not None:
                    return json.loads(val_str)
                return default
            except Exception as e:
                logger.warning(f"[SessionMemory] Redis read failed, falling back to SQLite: {e}")
        
        conn = sqlite3.connect(self.sqlite_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT value FROM session_store 
            WHERE key = ? AND (app_id = ? OR app_id = 'global')
        """, (key, app_id))
        row = cursor.fetchone()
        conn.close()
        if row:
            return json.loads(row[0])
        return default

    def delete(self, key: str, app_id: Optional[str] = None) -> None:
        key = self._namespace_key(key, app_id)
        if self.redis_client:
            try:
                self.redis_client.delete(key)
                return
            except Exception as e:
                logger.warning(f"[SessionMemory] Redis delete failed, falling back to SQLite: {e}")
        
        conn = sqlite3.connect(self.sqlite_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM session_store WHERE key = ?", (key,))
        conn.commit()
        conn.close()

    def clear(self) -> None:
        if self.redis_client:
            try:
                self.redis_client.flushdb()
                return
            except Exception as e:
                logger.warning(f"[SessionMemory] Redis flush failed, falling back to SQLite: {e}")
        
        conn = sqlite3.connect(self.sqlite_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM session_store")
        conn.commit()
        conn.close()
