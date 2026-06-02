import os
import json

class PreferenceMemory:
    def __init__(self, file_path=None):
        if file_path is None:
            self.file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "memory", "preference.json")
        else:
            self.file_path = file_path
        self.preferences = {
            "default_city": "Kashipur, Uttarakhand, India",
            "favorite_apps": {},
            "home_coordinates": None,
            "custom_mappings": {}
        }
        self.load()

    def load(self):
        if os.path.exists(self.file_path) and os.path.getsize(self.file_path) > 0:
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    self.preferences.update(loaded)
            except Exception as e:
                print(f"[MEMORY ERROR] Failed to load preference memory: {e}")

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self.preferences, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[MEMORY ERROR] Failed to save preference memory: {e}")

    def set(self, key: str, value):
        self.preferences[key] = value
        self.save()

    def get(self, key: str, default=None):
        return self.preferences.get(key, default)

    def update_favorite_app(self, app_name: str):
        """Increment execution count for favorite app ranking."""
        app_name = app_name.lower().strip()
        favs = self.preferences.setdefault("favorite_apps", {})
        favs[app_name] = favs.get(app_name, 0) + 1
        self.save()

    def get_favorite_app(self) -> str:
        """Return the most frequently opened app."""
        favs = self.preferences.get("favorite_apps", {})
        if not favs:
            return None
        return max(favs, key=favs.get)

    def clear(self):
        self.preferences = {
            "default_city": "Kashipur, Uttarakhand, India",
            "favorite_apps": {},
            "home_coordinates": None,
            "custom_mappings": {}
        }
        self.save()
