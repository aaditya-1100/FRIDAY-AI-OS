import os
import shutil
import time
import pathlib
import re
from typing import Dict, Any, Optional
from loguru import logger
from friday.core.events import AgentType, TaskDispatch, TaskResult, TaskStatus
from friday.agents.base_agent import BaseAgent
from friday.security.permission_engine import permission_engine
from execution.action_executor import execute_action

def is_safe_folder_name(name: str) -> bool:
    if not name:
        return False
    # Reject absolute paths (starts with drive letter or / or \)
    if ":" in name or name.startswith("/") or name.startswith("\\"):
        return False
    if ".." in name:
        return False
    try:
        desktop_path = pathlib.Path.home() / "Desktop"
        home_path = pathlib.Path.home()
        resolved = (desktop_path / name).resolve()
        
        # Check resolved path is within Desktop or user home
        resolved_str = str(resolved).lower()
        desktop_str = str(desktop_path).lower()
        home_str = str(home_path).lower()
        if resolved_str.startswith(desktop_str) or resolved_str.startswith(home_str):
            return True
    except Exception:
        pass
    return False

class PCAgent(BaseAgent):
    _last_intent = None
    _last_params_hash = None
    _last_exec_time = 0.0

    def __init__(self):
        super().__init__(AgentType.PC_AGENT)

    async def startup(self) -> None:
        logger.info("[PCAgent] Startup complete.")

    async def shutdown(self) -> None:
        logger.info("[PCAgent] Shutdown complete.")

    def get_capabilities(self) -> list[str]:
        return [
            "WINDOW_CONTROL",
            "SYSTEM_STATUS",
            "TEMPORAL_CONTROL",
            "APP_CONTROL",
            "SCREENSHOT",
            "SCREEN_UNDERSTANDING",
            "CLIPBOARD_READ",
            "CLIPBOARD_WRITE",
            "APP_FOCUS",
            "WINDOW_LIST",
            "FILE_READ",
            "FILE_WRITE",
            "FILE_CREATE",
            "FILE_MOVE",
            "FILE_DELETE",
            "VOLUME_SET",
            "VOLUME_MUTE",
            "CREATE_FOLDER",
            "OPEN_FOLDER"
        ]

    async def handle_task(self, dispatch: TaskDispatch) -> TaskResult:
        intent = dispatch.intent
        parameters = dispatch.parameters or {}
        
        # Deduplication Guard
        param_tuple = tuple(sorted((k, str(v)) for k, v in parameters.items()))
        current_hash = hash((intent, param_tuple))
        now = time.time()
        if current_hash == PCAgent._last_params_hash and (now - PCAgent._last_exec_time) < 2.0:
            logger.warning(f"[PCAgent] Rejecting duplicate intent dispatch: {intent}")
            return TaskResult(
                task_id=dispatch.task_id,
                agent_id=self.agent_id,
                status=TaskStatus.FAILED,
                payload={"error": "duplicate intent rejected"},
                correlation_id=dispatch.correlation_id
            )
        PCAgent._last_intent = intent
        PCAgent._last_params_hash = current_hash
        PCAgent._last_exec_time = now

        # Build the exact dictionary that execute_action expects
        intent_data = {
            "intent": intent,
            **parameters
        }

        # 1. Permission enforcement check
        allowed = await permission_engine.check_permission(
            agent_trust_level=self.trust_level,
            tool_name=intent,
            agent_id=self.agent_id,
            correlation_id=dispatch.correlation_id,
            session_id=dispatch.session_id
        )
        if not allowed:
            logger.warning(f"[PCAgent] Permission denied for intent: {intent}")
            return TaskResult(
                task_id=dispatch.task_id,
                agent_id=self.agent_id,
                status=TaskStatus.FAILED,
                payload={"error": "Permission denied"},
                correlation_id=dispatch.correlation_id
            )

        try:
            # 2. Native Handlers
            if intent == "VOLUME_SET":
                try:
                    level_str = parameters.get("level") or parameters.get("value") or parameters.get("query") or "50"
                    digits = re.findall(r'\d+', str(level_str))
                    level = int(digits[0]) if digits else 50
                    level = max(0, min(100, level))
                    
                    from comtypes import CLSCTX_ALL
                    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
                    devices = AudioUtilities.GetSpeakers()
                    interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                    volume = interface.QueryInterface(IAudioEndpointVolume)
                    
                    scalar_val = float(level) / 100.0
                    volume.SetMasterVolumeLevelScalar(scalar_val, None)
                    
                    return TaskResult(
                        task_id=dispatch.task_id,
                        agent_id=self.agent_id,
                        status=TaskStatus.SUCCESS,
                        payload={"volume": level},
                        correlation_id=dispatch.correlation_id
                    )
                except Exception as e:
                    return TaskResult(
                        task_id=dispatch.task_id,
                        agent_id=self.agent_id,
                        status=TaskStatus.FAILED,
                        payload={"error": str(e)},
                        correlation_id=dispatch.correlation_id
                    )

            elif intent == "VOLUME_MUTE":
                try:
                    action = parameters.get("action") or parameters.get("command") or parameters.get("query") or "mute"
                    action_str = str(action).lower().strip()
                    is_mute = 1 if "unmute" not in action_str else 0
                    
                    from comtypes import CLSCTX_ALL
                    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
                    devices = AudioUtilities.GetSpeakers()
                    interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                    volume = interface.QueryInterface(IAudioEndpointVolume)
                    
                    volume.SetMute(is_mute, None)
                    
                    return TaskResult(
                        task_id=dispatch.task_id,
                        agent_id=self.agent_id,
                        status=TaskStatus.SUCCESS,
                        payload={"muted": bool(is_mute)},
                        correlation_id=dispatch.correlation_id
                    )
                except Exception as e:
                    return TaskResult(
                        task_id=dispatch.task_id,
                        agent_id=self.agent_id,
                        status=TaskStatus.FAILED,
                        payload={"error": str(e)},
                        correlation_id=dispatch.correlation_id
                    )

            elif intent == "CREATE_FOLDER":
                folder_name = parameters.get("folder") or parameters.get("name") or parameters.get("query") or ""
                if not is_safe_folder_name(folder_name):
                    return TaskResult(
                        task_id=dispatch.task_id,
                        agent_id=self.agent_id,
                        status=TaskStatus.FAILED,
                        payload={"error": "unsafe path rejected"},
                        correlation_id=dispatch.correlation_id
                    )
                
                full_path = pathlib.Path.home() / "Desktop" / folder_name
                os.makedirs(full_path, exist_ok=True)
                return TaskResult(
                    task_id=dispatch.task_id,
                    agent_id=self.agent_id,
                    status=TaskStatus.SUCCESS,
                    payload={"path": str(full_path)},
                    correlation_id=dispatch.correlation_id
                )

            elif intent == "OPEN_FOLDER":
                folder_name = (parameters.get("folder") or parameters.get("name") or parameters.get("query") or "").lower().strip()
                mapping = {
                    "downloads": pathlib.Path.home() / "Downloads",
                    "documents": pathlib.Path.home() / "Documents",
                    "pictures": pathlib.Path.home() / "Pictures",
                    "desktop": pathlib.Path.home() / "Desktop",
                    "home": pathlib.Path.home(),
                    "music": pathlib.Path.home() / "Music",
                    "videos": pathlib.Path.home() / "Videos"
                }
                resolved_path = None
                for key, path in mapping.items():
                    if key in folder_name:
                        resolved_path = path
                        break
                
                if resolved_path is None:
                    # Fallback to direct name as subfolder of home
                    resolved_path = pathlib.Path.home() / folder_name
                
                if not resolved_path.exists():
                    return TaskResult(
                        task_id=dispatch.task_id,
                        agent_id=self.agent_id,
                        status=TaskStatus.FAILED,
                        payload={"error": "folder not found"},
                        correlation_id=dispatch.correlation_id
                    )
                
                os.startfile(str(resolved_path))
                return TaskResult(
                    task_id=dispatch.task_id,
                    agent_id=self.agent_id,
                    status=TaskStatus.SUCCESS,
                    payload={"path": str(resolved_path)},
                    correlation_id=dispatch.correlation_id
                )

            elif intent == "CLIPBOARD_READ":
                import pyperclip
                val = pyperclip.paste()
                return TaskResult(
                    task_id=dispatch.task_id,
                    agent_id=self.agent_id,
                    status=TaskStatus.SUCCESS,
                    payload={"text": val},
                    correlation_id=dispatch.correlation_id
                )
            elif intent == "CLIPBOARD_WRITE":
                import pyperclip
                text_val = parameters.get("text") or parameters.get("content") or ""
                pyperclip.copy(text_val)
                return TaskResult(
                    task_id=dispatch.task_id,
                    agent_id=self.agent_id,
                    status=TaskStatus.SUCCESS,
                    payload={"success": True},
                    correlation_id=dispatch.correlation_id
                )
            elif intent == "APP_FOCUS":
                import pygetwindow
                app_name = parameters.get("app") or parameters.get("title") or ""
                windows = pygetwindow.getWindowsWithTitle(app_name)
                if windows:
                    windows[0].activate()
                    return TaskResult(
                        task_id=dispatch.task_id,
                        agent_id=self.agent_id,
                        status=TaskStatus.SUCCESS,
                        payload={"success": True},
                        correlation_id=dispatch.correlation_id
                    )
                else:
                    raise ValueError(f"No window found with title: {app_name}")
            elif intent == "WINDOW_LIST":
                import pygetwindow
                titles = [w.title for w in pygetwindow.getAllWindows() if w.title]
                return TaskResult(
                    task_id=dispatch.task_id,
                    agent_id=self.agent_id,
                    status=TaskStatus.SUCCESS,
                    payload={"windows": titles},
                    correlation_id=dispatch.correlation_id
                )
            elif intent in ("FILE_READ", "FILE_WRITE", "FILE_CREATE", "FILE_MOVE", "FILE_DELETE"):
                def is_safe_file_path(path_str: str) -> bool:
                    if not path_str:
                        return False
                    try:
                        abs_path = os.path.abspath(path_str)
                    except Exception:
                        return False
                    
                    if ".." in path_str or ".." in abs_path:
                        return False
                    
                    home_dir = os.path.abspath(os.path.expanduser("~"))
                    friday_dir = os.path.abspath("C:/FRIDAY")
                    friday_app_data = os.path.abspath("C:/Users/gpska/.gemini/antigravity")
                    
                    abs_path_lower = abs_path.lower()
                    home_lower = home_dir.lower()
                    friday_lower = friday_dir.lower()
                    app_data_lower = friday_app_data.lower()
                    
                    system_paths = [
                        "c:/windows", "c:/program files", "c:/program files (x86)",
                        "c:/system volume information", "c:/recovery", "c:/boot"
                    ]
                    for sys_p in system_paths:
                        if abs_path_lower.startswith(sys_p):
                            return False
                    if abs_path_lower.startswith(home_lower) or abs_path_lower.startswith(friday_lower) or abs_path_lower.startswith(app_data_lower):
                        return True
                    return False

                if intent == "FILE_READ":
                    path = parameters.get("path") or parameters.get("filepath")
                    if not is_safe_file_path(path):
                        raise PermissionError(f"Path is outside allowed directories or unsafe: {path}")
                    with open(path, "r", encoding="utf-8") as f:
                        content = f.read()
                    return TaskResult(
                        task_id=dispatch.task_id,
                        agent_id=self.agent_id,
                        status=TaskStatus.SUCCESS,
                        payload={"content": content},
                        correlation_id=dispatch.correlation_id
                    )
                elif intent in ("FILE_WRITE", "FILE_CREATE"):
                    path = parameters.get("path") or parameters.get("filepath")
                    content = parameters.get("content") or parameters.get("text") or ""
                    if not is_safe_file_path(path):
                        raise PermissionError(f"Path is outside allowed directories or unsafe: {path}")
                    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(content)
                    return TaskResult(
                        task_id=dispatch.task_id,
                        agent_id=self.agent_id,
                        status=TaskStatus.SUCCESS,
                        payload={"success": True},
                        correlation_id=dispatch.correlation_id
                    )
                elif intent == "FILE_MOVE":
                    src = parameters.get("src") or parameters.get("source")
                    dst = parameters.get("dst") or parameters.get("destination")
                    if not is_safe_file_path(src) or not is_safe_file_path(dst):
                        raise PermissionError(f"Source or destination path is outside allowed directories or unsafe")
                    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
                    shutil.move(src, dst)
                    return TaskResult(
                        task_id=dispatch.task_id,
                        agent_id=self.agent_id,
                        status=TaskStatus.SUCCESS,
                        payload={"success": True},
                        correlation_id=dispatch.correlation_id
                    )
                elif intent == "FILE_DELETE":
                    path = parameters.get("path") or parameters.get("filepath")
                    if not is_safe_file_path(path):
                        raise PermissionError(f"Path is outside allowed directories or unsafe: {path}")
                    if os.path.exists(path):
                        if os.path.isdir(path):
                            shutil.rmtree(path)
                        else:
                            os.remove(path)
                    return TaskResult(
                        task_id=dispatch.task_id,
                        agent_id=self.agent_id,
                        status=TaskStatus.SUCCESS,
                        payload={"success": True},
                        correlation_id=dispatch.correlation_id
                    )

            # 3. Fallback to existing action_executor
            logger.info(f"[PCAgent] Executing PC action via action_executor for intent: {intent}")
            result = await execute_action(intent_data)
            
            payload = {}
            if isinstance(result, dict):
                payload = result
            elif isinstance(result, str):
                payload = {"response": result}
            else:
                payload = {"result": result}
            
            status = TaskStatus.SUCCESS if result is not False else TaskStatus.FAILED
            
            return TaskResult(
                task_id=dispatch.task_id,
                agent_id=self.agent_id,
                status=status,
                payload=payload,
                correlation_id=dispatch.correlation_id
            )
        except Exception as e:
            logger.error(f"[PCAgent] Error executing action: {e}", exc_info=True)
            return TaskResult(
                task_id=dispatch.task_id,
                agent_id=self.agent_id,
                status=TaskStatus.FAILED,
                payload={"error": str(e)},
                correlation_id=dispatch.correlation_id
            )
