import time
import os
import sys
import psutil
import asyncio
import uuid
from typing import Dict, Any, List, Optional

class RuntimeOrchestrator:
    """
    FRIDAY Enterprise Runtime Orchestrator.
    Serves as the centralized, thread-safe, single source of truth for FRIDAY's
    entire async runtime lifecycle, API state, task execution threads, and system health.
    Provides cancellation events and resource tracking.
    """
    def __init__(self):
        self.active_tasks: Dict[str, Dict[str, Any]] = {}  # task_id -> {name, start_time, status}
        self.active_llm: str = "groq"  # Only GROQ used now
        self.websocket_state: str = "DISCONNECTED"
        self.audio_ownership: Optional[str] = None # Tracks active speaking session
        self.listening: bool = True
        self.retrieval_active: bool = False
        self.maps_active: bool = False
        self.screen_analysis_active: bool = False
        self.interruption_count: int = 0
        self.queued_actions: List[Dict[str, Any]] = []
        self.current_generation_id: int = 0
        import threading
        self._generation_lock = threading.Lock()
        
        # Async Cancellation Tokens
        self._cancellation_tokens: Dict[str, asyncio.Event] = {}

    def increment_generation(self) -> int:
        """Increments the current active global generation ID and returns the new value."""
        with self._generation_lock:
            self.current_generation_id += 1
            print(f"[ORCHESTRATOR] Generation incremented to: {self.current_generation_id}")
            return self.current_generation_id

    # ── TASK LIFE CYCLE ORCHESTRATION ─────────────────────────────────────────
    def register_task(self, name: str) -> str:
        """Registers a newly spawned async background task with a unique ID."""
        task_id = str(uuid.uuid4())
        self.active_tasks[task_id] = {
            "name": name,
            "start_time": time.time(),
            "status": "RUNNING"
        }
        # Backward compatibility with state_manager
        try:
            from core.state_manager import track_task_start
            track_task_start(f"{name}_{task_id[:8]}")
        except Exception:
            pass
        print(f"[ORCHESTRATOR] Registered task '{name}' (ID: {task_id})")
        return task_id

    def deregister_task(self, task_id: str) -> None:
        """Deregisters a finished task from active orchestration tracking."""
        if task_id in self.active_tasks:
            task = self.active_tasks.pop(task_id)
            duration = time.time() - task["start_time"]
            # Backward compatibility
            try:
                from core.state_manager import track_task_end
                track_task_end(f"{task['name']}_{task_id[:8]}")
            except Exception:
                pass
            print(f"[ORCHESTRATOR] Deregistered task '{task['name']}' (ID: {task_id}) | Duration: {duration:.2f}s")

    # ── CANCELLATION TOKENS ───────────────────────────────────────────────────
    def get_cancellation_token(self, name: str) -> asyncio.Event:
        """Retrieves or creates a central async cancellation token event."""
        if name not in self._cancellation_tokens:
            self._cancellation_tokens[name] = asyncio.Event()
        return self._cancellation_tokens[name]

    def trigger_cancellation(self, name: str) -> None:
        """Triggers a cancellation token event, signaling all listeners to abort."""
        if name in self._cancellation_tokens:
            self._cancellation_tokens[name].set()
            print(f"[ORCHESTRATOR] Sent active abort/cancellation signal to: '{name}'")
            # Immediately recreate a fresh unset event for subsequent tasks
            self._cancellation_tokens[name] = asyncio.Event()

    # ── STATE & MODES SETTERS ────────────────────────────────────────────────
    def set_active_llm(self, llm_name: str) -> None:
        self.active_llm = llm_name

    def set_audio_ownership(self, session_id: Optional[str]) -> None:
        self.audio_ownership = session_id
        try:
            from core.state_manager import set_audio_state
            set_audio_state(playing=bool(session_id), session_id=session_id)
        except Exception:
            pass

    def set_websocket_state(self, state: str) -> None:
        self.websocket_state = state
        try:
            from core.state_manager import set_websocket_state
            set_websocket_state(state)
        except Exception:
            pass

    def register_interruption(self) -> None:
        self.interruption_count += 1
        try:
            from core.state_manager import register_interruption
            register_interruption()
        except Exception:
            pass

    def queue_action(self, action: Dict[str, Any]) -> None:
        self.queued_actions.append(action)
        try:
            from core.state_manager import queue_action
            queue_action(action)
        except Exception:
            pass

    def clear_queued_actions(self) -> None:
        self.queued_actions.clear()
        try:
            from core.state_manager import clear_queued_actions
            clear_queued_actions()
        except Exception:
            pass

    # ── SEMANTIC & SYSTEM TELEMETRY HEALTH CHECK ──────────────────────────────
    def run_health_telemetry(self) -> Dict[str, Any]:
        """Gathers system process telemetry and resources tracking."""
        try:
            proc = psutil.Process(os.getpid())
            mem_info = proc.memory_info()
            cpu_percent = proc.cpu_percent(interval=None)
            return {
                "ok": True,
                "pid": os.getpid(),
                "cpu_usage_percent": cpu_percent,
                "ram_usage_bytes": mem_info.rss,
                "active_tasks_count": len(self.active_tasks),
                "websocket_state": self.websocket_state,
                "audio_ownership": self.audio_ownership,
                "timestamp": time.time()
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

# Global thread-safe RuntimeOrchestrator instance
orchestrator = RuntimeOrchestrator()
