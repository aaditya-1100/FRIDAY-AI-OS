import os
import json

class SemanticMemory:
    def __init__(self, file_path=None):
        if file_path is None:
            self.file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "memory", "semantic.json")
        else:
            self.file_path = file_path
        self.knowledge = {}
        self.load()

    def load(self):
        if os.path.exists(self.file_path) and os.path.getsize(self.file_path) > 0:
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    self.knowledge = json.load(f)
            except Exception as e:
                print(f"[MEMORY ERROR] Failed to load semantic memory: {e}")
                self.knowledge = {}

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self.knowledge, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[MEMORY ERROR] Failed to save semantic memory: {e}")

    def add_fact(self, key: str, value: str):
        """Add a key-value semantic fact (e.g. user home directory path, default location)."""
        self.knowledge[key.lower().strip()] = value
        self.save()

    def get_fact(self, key: str, default=None) -> str:
        return self.knowledge.get(key.lower().strip(), default)

    def clear(self):
        self.knowledge = {}
        self.save()
