import os
import sqlite3
import asyncio
from loguru import logger

class UserProfile:
    def __init__(self):
        base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "user_profile.db"))
        worker_id = os.environ.get("PYTEST_XDIST_WORKER")
        if worker_id:
            self.sqlite_path = f"{os.path.splitext(base_path)[0]}_{worker_id}.db"
        else:
            self.sqlite_path = base_path
            
        os.makedirs(os.path.dirname(self.sqlite_path), exist_ok=True)
        self.stats = {}  # In-memory cache: {stat_key: {stat_subkey: count}}
        self._pending_tasks = []
        self._init_sqlite()
        self.load()

    def _init_sqlite(self):
        try:
            conn = sqlite3.connect(self.sqlite_path)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_stats (
                    stat_key TEXT,
                    stat_subkey TEXT,
                    count INTEGER,
                    PRIMARY KEY (stat_key, stat_subkey)
                )
            """)
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"[UserProfile] Failed to initialize SQLite database: {e}")

    def load(self):
        """Load stats from SQLite database into memory cache."""
        self.stats = {
            "hour": {},
            "app": {},
            "intent": {},
            "entity": {}
        }
        try:
            conn = sqlite3.connect(self.sqlite_path)
            cursor = conn.cursor()
            cursor.execute("SELECT stat_key, stat_subkey, count FROM user_stats")
            rows = cursor.fetchall()
            for key, subkey, count in rows:
                if key not in self.stats:
                    self.stats[key] = {}
                self.stats[key][subkey] = count
            conn.close()
            logger.info(f"[UserProfile] Loaded stats from SQLite. Keys count: {[f'{k}:{len(v)}' for k,v in self.stats.items()]}")
        except Exception as e:
            logger.error(f"[UserProfile] Failed to load stats: {e}")

    def _extract_app_name(self, active_window: str) -> str:
        if not active_window:
            return ""
        known_apps = ["VS Code", "Visual Studio Code", "Notepad", "Excel", "Word", "PyCharm", "Chrome", "Firefox", "Edge", "Explorer"]
        title_lower = active_window.lower()
        for app in known_apps:
            if app.lower() in title_lower:
                if app == "Visual Studio Code":
                    return "VS Code"
                return app
        return active_window

    def _sync_update(self, intent: str, entities: list, active_window: str, hour: int):
        app_name = self._extract_app_name(active_window)
        try:
            conn = sqlite3.connect(self.sqlite_path)
            cursor = conn.cursor()

            def incr(key, subkey):
                if not subkey:
                    return
                # Increment in-memory
                if key not in self.stats:
                    self.stats[key] = {}
                self.stats[key][subkey] = self.stats[key].get(subkey, 0) + 1

                # Increment in SQLite
                cursor.execute(
                    "INSERT INTO user_stats (stat_key, stat_subkey, count) VALUES (?, ?, 1) "
                    "ON CONFLICT(stat_key, stat_subkey) DO UPDATE SET count = count + 1",
                    (key, subkey)
                )

            incr("hour", str(hour))
            if app_name:
                incr("app", app_name)
            if intent:
                incr("intent", intent)
            for entity in entities:
                if entity:
                    incr("entity", entity)

            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"[UserProfile] Failed to sync write profile update: {e}")

    async def record_turn(self, intent: str, entities: list, active_window: str, hour: int) -> None:
        """Asynchronously triggers the sync write task in a thread pool."""
        task = asyncio.create_task(
            asyncio.to_thread(self._sync_update, intent, entities, active_window, hour)
        )
        self._pending_tasks.append(task)
        # Prune done tasks
        self._pending_tasks = [t for t in self._pending_tasks if not t.done()]

    def get_top_n(self, stat_key: str, n: int) -> list:
        sub_stats = self.stats.get(stat_key, {})
        return sorted(sub_stats.items(), key=lambda item: item[1], reverse=True)[:n]

    def get_active_hours(self) -> dict:
        return self.stats.get("hour", {})

    async def flush(self) -> None:
        """Ensure all pending SQLite tasks are completed."""
        if self._pending_tasks:
            logger.info(f"[UserProfile] Flushing {len(self._pending_tasks)} pending writes...")
            await asyncio.gather(*self._pending_tasks, return_exceptions=True)
            self._pending_tasks.clear()
            logger.info("[UserProfile] Flush complete.")


user_profile = UserProfile()
