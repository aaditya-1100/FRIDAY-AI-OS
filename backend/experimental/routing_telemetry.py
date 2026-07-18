"""
routing_telemetry.py — FRIDAY Centralized Telemetry and Validation Infrastructure
=============================================================================
Manages thread-safe logging and historical profiling for:
  - Routing Decisions & Margins
  - Trigger Arbitration Matrices
  - Unified Turn Confidence & Relevance Masks
  - User Feedback & Correction Loops
"""

import os
import sqlite3
import time
import json
import uuid
import threading
from typing import Dict, Any, List, Optional

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "routing_telemetry.db"
)

# Ensure data directory exists
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

class TelemetryEngine:
    """
    Centralized, thread-safe SQLite-backed Telemetry Engine.
    Handles parallel commits using a connection pool lock and asynchronous execution concepts.
    """
    def __init__(self):
        self._lock = threading.Lock()
        self._initialize_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(DB_PATH, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _initialize_db(self) -> None:
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # 1. Routing & Telemetry Main Table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS routing_telemetry (
                id TEXT PRIMARY KEY,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                query TEXT NOT NULL,
                system_state TEXT NOT NULL,
                winner TEXT NOT NULL,
                runner_up TEXT NOT NULL,
                winning_score REAL NOT NULL,
                runner_up_score REAL NOT NULL,
                margin REAL NOT NULL,
                is_tiebreak_invoked INTEGER NOT NULL, -- 0 = False, 1 = True
                confidence_score REAL NOT NULL,
                execution_latency_ms INTEGER NOT NULL,
                correction_received INTEGER DEFAULT 0, -- 0 = False, 1 = True
                correction_latency_sec REAL,
                feedback_signal INTEGER DEFAULT 0 -- (-1 = Corrected, +1 = Successful)
            )
            """)
            
            # 2. Trigger Arbitration Matrix Logs (for deep diagnostics)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS trigger_telemetry (
                id TEXT PRIMARY KEY,
                routing_id TEXT NOT NULL,
                trigger_name TEXT NOT NULL,
                semantic_intent_score REAL NOT NULL,
                capability_confidence REAL NOT NULL,
                historical_reliability REAL NOT NULL,
                priority_weight REAL NOT NULL,
                final_score REAL NOT NULL,
                FOREIGN KEY(routing_id) REFERENCES routing_telemetry(id)
            )
            """)
            
            # 3. Pipeline Confidence Metric Logs
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS confidence_telemetry (
                id TEXT PRIMARY KEY,
                routing_id TEXT NOT NULL,
                asr_score REAL NOT NULL,
                intent_score REAL NOT NULL,
                domain_score REAL NOT NULL,
                routing_score REAL NOT NULL,
                memory_score REAL NOT NULL,
                execution_score REAL NOT NULL,
                relevance_masks TEXT NOT NULL, -- JSON-serialized dict
                weights TEXT NOT NULL,         -- JSON-serialized dict
                final_unified_score REAL NOT NULL,
                FOREIGN KEY(routing_id) REFERENCES routing_telemetry(id)
            )
            """)
            
            # 4. Voice / TTS Telemetry table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS voice_telemetry (
                id TEXT PRIMARY KEY,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                response_id TEXT NOT NULL,
                text TEXT NOT NULL,
                requested_voice TEXT NOT NULL,
                provider_switched_from TEXT,
                provider_switched_to TEXT NOT NULL,
                reason TEXT NOT NULL,
                latency_ms INTEGER
            )
            """)
            
            conn.commit()
            conn.close()

    def log_turn(
        self,
        query: str,
        system_state: str,
        winner: str,
        runner_up: str,
        winning_score: float,
        runner_up_score: float,
        margin: float,
        is_tiebreak_invoked: bool,
        confidence_score: float,
        latency_ms: int,
        trigger_matrix: List[Dict[str, Any]],
        confidence_breakdown: Dict[str, Any]
    ) -> str:
        """Commits a complete turn payload atomically across all telemetry tables."""
        routing_id = str(uuid.uuid4())
        
        # Serialize dictionaries to JSON strings
        masks_str = json.dumps(confidence_breakdown.get("relevance_masks", {}))
        weights_str = json.dumps(confidence_breakdown.get("weights", {}))
        
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            try:
                # 1. Insert Routing Telemetry
                cursor.execute("""
                INSERT INTO routing_telemetry (
                    id, query, system_state, winner, runner_up, winning_score,
                    runner_up_score, margin, is_tiebreak_invoked, confidence_score, execution_latency_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    routing_id, query, system_state, winner, runner_up, winning_score,
                    runner_up_score, margin, 1 if is_tiebreak_invoked else 0, confidence_score, latency_ms
                ))
                
                # 2. Insert Trigger Matrix
                for t in trigger_matrix:
                    t_id = str(uuid.uuid4())
                    cursor.execute("""
                    INSERT INTO trigger_telemetry (
                        id, routing_id, trigger_name, semantic_intent_score,
                        capability_confidence, historical_reliability, priority_weight, final_score
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        t_id, routing_id, t["name"], t["semantic_intent_score"],
                        t["capability_confidence"], t["historical_reliability"],
                        t["priority_weight"], t["final_score"]
                    ))
                    
                # 3. Insert Confidence breakdown
                cursor.execute("""
                INSERT INTO confidence_telemetry (
                    id, routing_id, asr_score, intent_score, domain_score,
                    routing_score, memory_score, execution_score, relevance_masks, weights, final_unified_score
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    str(uuid.uuid4()), routing_id,
                    confidence_breakdown.get("asr", 1.0),
                    confidence_breakdown.get("intent", 1.0),
                    confidence_breakdown.get("domain", 1.0),
                    confidence_breakdown.get("routing", 1.0),
                    confidence_breakdown.get("memory", 1.0),
                    confidence_breakdown.get("execution", 1.0),
                    masks_str, weights_str, confidence_score
                ))
                
                conn.commit()
                print(f"[TELEMETRY] Turn successfully logged with ID: {routing_id}")
            except Exception as e:
                conn.rollback()
                print(f"[TELEMETRY ERROR] Commit failed: {e}")
            finally:
                conn.close()
                
        return routing_id

    def register_correction(self, routing_id: str, latency_sec: float) -> None:
        """Updates a logged turn to register a subsequent correction/fumble."""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            try:
                cursor.execute("""
                UPDATE routing_telemetry
                SET correction_received = 1,
                    correction_latency_sec = ?,
                    feedback_signal = -1
                WHERE id = ?
                """, (latency_sec, routing_id))
                conn.commit()
                print(f"[TELEMETRY] Registered negative correction for turn: {routing_id}")
            except Exception as e:
                print(f"[TELEMETRY ERROR] Failed to register correction: {e}")
            finally:
                conn.close()

    def register_success(self, routing_id: str) -> None:
        """Updates a logged turn to register a verified successful execution."""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            try:
                cursor.execute("""
                UPDATE routing_telemetry
                SET feedback_signal = 1
                WHERE id = ?
                """, (routing_id,))
                conn.commit()
                print(f"[TELEMETRY] Registered explicit success for turn: {routing_id}")
            except Exception as e:
                print(f"[TELEMETRY ERROR] Failed to register success: {e}")
            finally:
                conn.close()

    def get_kpis(self) -> Dict[str, Any]:
        """Calculates system-wide key performance indicators over recent history."""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            try:
                # 1. Total count
                cursor.execute("SELECT COUNT(*) FROM routing_telemetry")
                total = cursor.fetchone()[0]
                if total == 0:
                    return {"total_turns": 0, "correction_rate": 0.0, "avg_margin": 0.0, "latency_p95_ms": 0}
                
                # 2. Correction rate
                cursor.execute("SELECT SUM(correction_received) FROM routing_telemetry")
                corrections = cursor.fetchone()[0] or 0
                cr = float(corrections / total)
                
                # 3. Average margin
                cursor.execute("SELECT AVG(margin) FROM routing_telemetry")
                avg_margin = cursor.fetchone()[0] or 0.0
                
                # 4. Latency p95
                cursor.execute("SELECT execution_latency_ms FROM routing_telemetry ORDER BY execution_latency_ms ASC")
                latencies = [row[0] for row in cursor.fetchall()]
                p95_idx = int(len(latencies) * 0.95)
                p95_lat = latencies[p95_idx] if latencies else 0
                
                return {
                    "total_turns": total,
                    "correction_rate": cr,
                    "avg_margin": avg_margin,
                    "latency_p95_ms": p95_lat
                }
            except Exception as e:
                print(f"[TELEMETRY ERROR] Failed to fetch KPIs: {e}")
                return {}
            finally:
                conn.close()

    def log_voice_switch(
        self,
        response_id: str,
        text: str,
        requested_voice: str,
        switched_from: Optional[str],
        switched_to: str,
        reason: str,
        latency_ms: Optional[int] = None
    ) -> None:
        """Commits a voice provider switch event to the telemetry database."""
        voice_id = str(uuid.uuid4())
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            try:
                cursor.execute("""
                INSERT INTO voice_telemetry (
                    id, response_id, text, requested_voice,
                    provider_switched_from, provider_switched_to, reason, latency_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    voice_id, response_id, text, requested_voice,
                    switched_from, switched_to, reason, latency_ms
                ))
                conn.commit()
                print(f"[TELEMETRY] Voice switch successfully logged: {switched_from} -> {switched_to} for {response_id}")
            except Exception as e:
                print(f"[TELEMETRY ERROR] Voice switch log failed: {e}")
            finally:
                conn.close()

# Central thread-safe Telemetry Engine instance
telemetry_engine = TelemetryEngine()
