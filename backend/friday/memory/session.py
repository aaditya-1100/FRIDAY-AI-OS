import json
import sqlite3
import os
import asyncio
from typing import Any, Optional
from loguru import logger

_redis_client_instance = None
_redis_active = None
_sqlite_initialized = False

class SessionMemory:
    def __init__(self, host: str = "127.0.0.1", port: int = 6379, db: int = 0):
        self.redis_host = host
        self.redis_port = port
        self.redis_db = db
        
        base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "session_fallback.db"))
        worker_id = os.environ.get("PYTEST_XDIST_WORKER")
        if worker_id:
            self.sqlite_path = f"{os.path.splitext(base_path)[0]}_{worker_id}.db"
        else:
            self.sqlite_path = base_path
        os.makedirs(os.path.dirname(self.sqlite_path), exist_ok=True)

    async def _ensure_initialized(self) -> None:
        global _redis_active, _sqlite_initialized
        if _redis_active is not None and _sqlite_initialized:
            return
        await asyncio.to_thread(self._sync_init)

    def _sync_init(self) -> None:
        global _redis_client_instance, _redis_active, _sqlite_initialized
        if _redis_active is None:
            try:
                import redis
                client = redis.Redis(
                    host=self.redis_host, 
                    port=self.redis_port, 
                    db=self.redis_db, 
                    decode_responses=True, 
                    socket_timeout=0.1,
                    socket_connect_timeout=0.1,
                    retry_on_timeout=False
                )
                client.ping()
                _redis_client_instance = client
                _redis_active = True
                logger.info("Session store: Redis active")
            except Exception as e:
                logger.info(f"Session store: SQLite fallback active")
                _redis_client_instance = None
                _redis_active = False
        
        if not _sqlite_initialized:
            self._init_sqlite()
            _sqlite_initialized = True

    @property
    def redis_client(self):
        global _redis_client_instance
        return _redis_client_instance

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

    async def set(self, key: str, value: Any, ex: Optional[int] = None, app_id: Optional[str] = None) -> None:
        await self._ensure_initialized()
        
        def _sync_set():
            nonlocal app_id
            if app_id is None:
                try:
                    from friday.system.context import system_context
                    app_id = system_context.get_context().get("app_id", "general")
                except Exception:
                    app_id = "general"
            ns_key = self._namespace_key(key, app_id)
            val_str = json.dumps(value)
            if self.redis_client:
                try:
                    self.redis_client.set(ns_key, val_str, ex=ex)
                    return
                except Exception as e:
                    logger.warning(f"[SessionMemory] Redis write failed, falling back to SQLite: {e}")
            
            conn = sqlite3.connect(self.sqlite_path)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO session_store (key, value, app_id)
                VALUES (?, ?, ?)
            """, (ns_key, val_str, app_id))
            conn.commit()
            conn.close()

        await asyncio.to_thread(_sync_set)

    async def get(self, key: str, default: Any = None, app_id: Optional[str] = None) -> Any:
        await self._ensure_initialized()
        
        def _sync_get():
            nonlocal app_id
            if app_id is None:
                try:
                    from friday.system.context import system_context
                    app_id = system_context.get_context().get("app_id", "general")
                except Exception:
                    app_id = "general"
            ns_key = self._namespace_key(key, app_id)
            if self.redis_client:
                try:
                    val_str = self.redis_client.get(ns_key)
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
            """, (ns_key, app_id))
            row = cursor.fetchone()
            conn.close()
            if row:
                return json.loads(row[0])
            return default

        return await asyncio.to_thread(_sync_get)

    async def delete(self, key: str, app_id: Optional[str] = None) -> None:
        await self._ensure_initialized()
        
        def _sync_delete():
            ns_key = self._namespace_key(key, app_id)
            if self.redis_client:
                try:
                    self.redis_client.delete(ns_key)
                    return
                except Exception as e:
                    logger.warning(f"[SessionMemory] Redis delete failed, falling back to SQLite: {e}")
            
            conn = sqlite3.connect(self.sqlite_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM session_store WHERE key = ?", (ns_key,))
            conn.commit()
            conn.close()

        await asyncio.to_thread(_sync_delete)

    async def clear(self) -> None:
        await self._ensure_initialized()
        
        def _sync_clear():
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

        await asyncio.to_thread(_sync_clear)
