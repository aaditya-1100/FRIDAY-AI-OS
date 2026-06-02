import os
import json
from datetime import datetime

class EpisodicMemory:
    def __init__(self, file_path=None):
        if file_path is None:
            self.file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "memory", "episodic.json")
        else:
            self.file_path = file_path
        self.events = []
        self.load()

    def load(self):
        if os.path.exists(self.file_path) and os.path.getsize(self.file_path) > 0:
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    self.events = json.load(f)
            except Exception as e:
                print(f"[MEMORY ERROR] Failed to load episodic memory: {e}")
                self.events = []

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self.events, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[MEMORY ERROR] Failed to save episodic memory: {e}")

    def log_event(self, query: str, intent: str, success: bool, metadata: dict = None):
        """Log a user event/command and system action."""
        event = {
            "timestamp": datetime.now().isoformat(),
            "query": query,
            "intent": intent,
            "success": success,
            "metadata": metadata or {}
        }
        self.events.append(event)
        # Keep last 100 events to prevent memory bloat
        if len(self.events) > 100:
            self.events = self.events[-100:]
        self.save()

    def get_last_event(self, success_only=True):
        """Get the most recent event."""
        if not self.events:
            return None
        if success_only:
            for event in reversed(self.events):
                if event.get("success"):
                    return event
            return None
        return self.events[-1]

    def clear(self):
        self.events = []
        self.save()
