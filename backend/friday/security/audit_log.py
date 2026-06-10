import sqlite3
import os
from datetime import datetime
from loguru import logger

class AuditLogger:
    def __init__(self, db_path: str = None):
        if db_path is None:
            self.db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "audit.db"))
        else:
            self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                agent_id TEXT,
                tool_name TEXT,
                permission_level TEXT,
                granted INTEGER,
                reason TEXT,
                correlation_id TEXT
            )
        """)
        conn.commit()
        conn.close()

    def _execute_query(self, query: str, params: tuple = ()) -> list:
        # Enforce append-only in code
        q_upper = query.upper()
        forbidden = ["DELETE", "UPDATE", "TRUNCATE", "DROP", "ALTER"]
        for word in forbidden:
            if word in q_upper:
                raise PermissionError(f"[AuditLogger] Forbidden operation '{word}' detected. The audit log is strictly append-only.")
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.commit()
        conn.close()
        return rows

    def log_tool_call(self, agent_id: str, tool_name: str, permission_level: str, granted: bool, reason: str, correlation_id: str) -> None:
        query = """
            INSERT INTO audit_log (timestamp, agent_id, tool_name, permission_level, granted, reason, correlation_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        ts = datetime.utcnow().isoformat() + "Z"
        self._execute_query(query, (ts, str(agent_id), tool_name, permission_level, 1 if granted else 0, reason, str(correlation_id)))
        logger.info(f"[AuditLogger] Logged tool call: tool={tool_name}, granted={granted}, reason={reason}")

    def get_records(self) -> list:
        query = "SELECT id, timestamp, agent_id, tool_name, permission_level, granted, reason, correlation_id FROM audit_log"
        rows = self._execute_query(query)
        records = []
        for r in rows:
            records.append({
                "id": r[0],
                "timestamp": r[1],
                "agent_id": r[2],
                "tool_name": r[3],
                "permission_level": r[4],
                "granted": bool(r[5]),
                "reason": r[6],
                "correlation_id": r[7]
            })
        return records

# Global AuditLogger instance
audit_logger = AuditLogger()
