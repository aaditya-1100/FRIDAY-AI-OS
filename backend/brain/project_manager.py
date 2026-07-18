import os
import json
import time

class ProjectManager:
    def __init__(self, file_path=None):
        if file_path is None:
            from config.paths import get_data_path
            self.file_path = get_data_path("projects", "project_registry.json")
        else:
            self.file_path = file_path
        
        self.registry = {
            "active_project": {},
            "registered_projects": []
        }
        self.load()

    def load(self) -> None:
        """Loads project registry from disk."""
        if os.path.exists(self.file_path) and os.path.getsize(self.file_path) > 0:
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    self.registry = json.load(f)
            except Exception as e:
                print(f"[PROJECTS ERROR] Failed to load registry: {e}")
                self.registry = {
                    "active_project": {},
                    "registered_projects": []
                }
        else:
            self.registry = {
                "active_project": {},
                "registered_projects": []
            }

    def save(self) -> None:
        """Saves project registry to disk."""
        try:
            os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self.registry, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[PROJECTS ERROR] Failed to save registry: {e}")

    def get_active_project(self) -> dict:
        """Returns the active project metadata."""
        return self.registry.get("active_project", {})

    def set_active_project(self, project_name: str, workspace_path: str, repo_path: str, active_goal: str, project_type: str) -> bool:
        """
        Sets the active project metadata and performs write-read verification.
        Returns True if committed and verified successfully, otherwise False.
        """
        project_data = {
            "project_name": project_name,
            "workspace_path": workspace_path,
            "repo_path": repo_path,
            "active_goal": active_goal,
            "project_type": project_type,
            "last_active_timestamp": time.time()
        }
        
        # 1. Commit Write
        self.registry["active_project"] = project_data
        
        # Check if project already in registered_projects
        exists = False
        for p in self.registry.get("registered_projects", []):
            if p.get("project_name") == project_name:
                exists = True
                p["workspace_path"] = workspace_path
                p["repo_path"] = repo_path
                p["project_type"] = project_type
                break
        
        if not exists:
            if "registered_projects" not in self.registry:
                self.registry["registered_projects"] = []
            self.registry["registered_projects"].append({
                "project_name": project_name,
                "workspace_path": workspace_path,
                "repo_path": repo_path,
                "project_type": project_type
            })
            
        self.save()
        
        # 2. Reload and Verify
        self.load()
        active = self.get_active_project()
        
        verified = (
            active.get("project_name") == project_name and
            active.get("workspace_path") == workspace_path and
            active.get("repo_path") == repo_path and
            active.get("active_goal") == active_goal and
            active.get("project_type") == project_type
        )
        
        return verified
