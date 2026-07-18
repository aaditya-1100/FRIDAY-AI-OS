import os
import shutil
import time
import pathlib
import re
from loguru import logger
from friday.core.events import AgentType, TaskDispatch, TaskResult, TaskStatus
from friday.agents.base_agent import BaseAgent
from friday.security.permission_engine import permission_engine
import subprocess

# ── Circular import REMOVED: execute_action no longer imported ──────────────


def toggle_bluetooth(state: str) -> bool:
    """
    Toggles Bluetooth status using the WinRT API via PowerShell script execution.
    state: "On" or "Off".
    """
    try:
        target_state = "On" if state.lower() in ("on", "enable") else "Off"
        ps_script = f"""
Param([string]$State = "{target_state}")
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | ? {{ $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' }})[0]
Function Await($WinRtTask, $ResultType) {{
    $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    $netTask.Result
}}
[Windows.Devices.Radios.Radio,Windows.System.Devices,ContentType=WindowsRuntime] | Out-Null
[Windows.Devices.Radios.RadioAccessStatus,Windows.System.Devices,ContentType=WindowsRuntime] | Out-Null
$status = Await ([Windows.Devices.Radios.Radio]::RequestAccessAsync()) ([Windows.Devices.Radios.RadioAccessStatus])
$radios = Await ([Windows.Devices.Radios.Radio]::GetRadiosAsync()) ([System.Collections.Generic.IReadOnlyList[Windows.Devices.Radios.Radio]])
$bt = $radios | ? {{ $_.Kind -eq 'Bluetooth' }}
if ($bt) {{
    [Windows.Devices.Radios.RadioState,Windows.System.Devices,ContentType=WindowsRuntime] | Out-Null
    $targetState = if ($State -eq "On") {{ [Windows.Devices.Radios.RadioState]::On }} else {{ [Windows.Devices.Radios.RadioState]::Off }}
    $res = Await ($bt.SetStateAsync($targetState)) ([Windows.Devices.Radios.RadioAccessStatus])
    Write-Output "SUCCESS"
}} else {{
    Write-Output "Bluetooth radio not found."
}}
"""
        cmd = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode == 0 and "SUCCESS" in res.stdout:
            return True
        else:
            logger.error(f"Bluetooth toggle failed: {res.stdout} {res.stderr}")
            return False
    except Exception as e:
        logger.error(f"Bluetooth toggle exception: {e}")
        return False


def set_screen_brightness(level: int) -> bool:
    try:
        import sys
        if sys.platform != "win32":
            raise NotImplementedError("Only Windows is supported.")
        import wmi
        try:
            c = wmi.WMI(namespace="root\\WMI")
        except Exception as wmi_e:
            raise Exception(f"WMI namespace unavailable: {repr(wmi_e)}")
        methods = c.WmiMonitorBrightnessMethods()
        if not methods:
            raise Exception("No monitor brightness methods found (external/unsupported monitor).")
        for method in methods:
            method.WmiSetBrightness(level, 1)
        return True
    except Exception as e:
        logger.warning("Failed to set brightness via wmi package: {}", repr(e))
        try:
            cmd = [
                "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                f"(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods).WmiSetBrightness(1, {level})"
            ]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode == 0:
                return True
            else:
                raise Exception(repr(res.stderr or res.stdout))
        except Exception as e2:
            logger.error("Failed to set brightness via PowerShell fallback: {}", repr(e2))
            return False


def is_safe_folder_name(name: str) -> bool:
    if not name:
        return False
    if ":" in name or name.startswith("/") or name.startswith("\\"):
        return False
    if ".." in name:
        return False
    try:
        desktop_path = pathlib.Path.home() / "Desktop"
        home_path = pathlib.Path.home()
        resolved = (desktop_path / name).resolve()
        resolved_str = str(resolved).lower()
        desktop_str = str(desktop_path).lower()
        home_str = str(home_path).lower()
        if resolved_str.startswith(desktop_str) or resolved_str.startswith(home_str):
            return True
    except Exception:
        pass
    return False


def _is_safe_file_path(path_str: str) -> bool:
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
    system_paths = [
        "c:/windows", "c:/program files", "c:/program files (x86)",
        "c:/system volume information", "c:/recovery", "c:/boot"
    ]
    for sys_p in system_paths:
        if abs_path_lower.startswith(sys_p):
            return False
    if (abs_path_lower.startswith(home_dir.lower()) or
            abs_path_lower.startswith(friday_dir.lower()) or
            abs_path_lower.startswith(friday_app_data.lower())):
        return True
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
            "OPEN", "WINDOW_CONTROL", "SCREENSHOT",
            "SYSTEM_STATUS", "SYSTEM_STATUS_FULL",
            "BLUETOOTH_TOGGLE", "BRIGHTNESS_CONTROL",
            "DELETE_PATH", "CLEAN_TEMP",
            "SET_REMINDER", "SET_TIMER", "SET_ALARM", "STOPWATCH_CONTROL",
            "SET_SCHEDULED_TASK", "SET_RECURRING_REMINDER",
            "LIST_REMINDERS", "CANCEL_REMINDER",
            "VOLUME_SET", "VOLUME_MUTE",
            "CREATE_FOLDER", "OPEN_FOLDER",
            "CLIPBOARD_READ", "CLIPBOARD_WRITE",
            "APP_FOCUS", "WINDOW_LIST",
            "FILE_READ", "FILE_WRITE", "FILE_CREATE", "FILE_MOVE", "FILE_DELETE",
            "CHECK_DISK_SPACE", "CHECK_SYSTEM_INFO", "PING_HOST",
            "LIST_DIRECTORY", "LIST_PROCESSES"
        ]

    def _make_result(self, dispatch: TaskDispatch, status: TaskStatus, payload: dict) -> TaskResult:
        return TaskResult(
            task_id=dispatch.task_id,
            agent_id=self.agent_id,
            status=status,
            payload=payload,
            correlation_id=dispatch.correlation_id
        )

    def _ok(self, dispatch, payload=None):
        return self._make_result(dispatch, TaskStatus.SUCCESS, payload or {})

    def _fail(self, dispatch, error: str):
        return self._make_result(dispatch, TaskStatus.FAILED, {"error": error})

    async def handle_task(self, dispatch: TaskDispatch) -> TaskResult:
        intent = dispatch.intent
        parameters = dispatch.parameters or {}

        # Deduplication Guard
        param_tuple = tuple(sorted((k, str(v)) for k, v in parameters.items()))
        current_hash = hash((intent, param_tuple))
        now = time.time()
        if current_hash == PCAgent._last_params_hash and (now - PCAgent._last_exec_time) < 2.0:
            logger.warning(f"[PCAgent] Rejecting duplicate intent dispatch: {intent}")
            return self._fail(dispatch, "duplicate intent rejected")
        PCAgent._last_intent = intent
        PCAgent._last_params_hash = current_hash
        PCAgent._last_exec_time = now

        # Permission enforcement check
        allowed = await permission_engine.check_permission(
            agent_trust_level=self.trust_level,
            tool_name=intent,
            agent_id=self.agent_id,
            correlation_id=dispatch.correlation_id,
            session_id=dispatch.session_id
        )
        if not allowed:
            logger.warning(f"[PCAgent] Permission denied for intent: {intent}")
            return self._fail(dispatch, "Permission denied")

        try:
            # ── OPEN ─────────────────────────────────────────────────────────
            if intent == "OPEN":
                from system.app_control import open_app
                target = parameters.get("target") or parameters.get("app") or parameters.get("query") or ""
                success = open_app(target)
                if success:
                    return self._ok(dispatch, {"response": f"Opening {target}, sir.", "target": target})
                return self._fail(dispatch, f"Could not open application: {target}")

            # ── WINDOW_CONTROL ────────────────────────────────────────────────
            elif intent == "WINDOW_CONTROL":
                from execution.window_control import (
                    close_active_window, minimize_active_window,
                    maximize_active_window, focus_window, close_active_tab
                )
                from execution.system_control import shutdown_pc, restart_pc, sleep_pc, lock_pc
                import asyncio
                command = parameters.get("command", "close")
                target = parameters.get("target", "")
                loop = asyncio.get_running_loop()

                if command == "minimize":
                    success = minimize_active_window()
                    resp = "Minimizing the active window, sir." if success else "I could not minimize the window, sir."
                    return self._ok(dispatch, {"response": resp}) if success else self._fail(dispatch, resp)
                elif command == "maximize":
                    success = maximize_active_window()
                    resp = "Maximizing the active window, sir." if success else "I could not maximize the window, sir."
                    return self._ok(dispatch, {"response": resp}) if success else self._fail(dispatch, resp)
                elif command == "shutdown":
                    loop.call_later(2.0, shutdown_pc)
                    return self._ok(dispatch, {"response": "Shutting down the computer, sir. Goodbye."})
                elif command == "restart":
                    loop.call_later(2.0, restart_pc)
                    return self._ok(dispatch, {"response": "Restarting the computer now, sir."})
                elif command == "sleep":
                    loop.call_later(2.0, sleep_pc)
                    return self._ok(dispatch, {"response": "Putting the system to sleep, sir."})
                elif command == "lock":
                    lock_pc()
                    return self._ok(dispatch, {"response": "Locking the workstation, sir."})
                elif command in ("focus", "switch", "activate"):
                    if target:
                        success = focus_window(target)
                        resp = f"Switched to {target}, sir." if success else f"I could not find an active window for {target}, sir."
                        return self._ok(dispatch, {"response": resp}) if success else self._fail(dispatch, resp)
                    return self._fail(dispatch, "Which application would you like to switch to, sir?")
                elif command == "close_tab" or (target and target.lower() in ("tab", "active tab", "current tab")):
                    success = close_active_tab()
                    resp = "Closing the active tab, sir." if success else "I could not close the active tab, sir."
                    return self._ok(dispatch, {"response": resp}) if success else self._fail(dispatch, resp)
                else:  # close
                    import pygetwindow as gw
                    import re
                    target_lower = target.lower().strip() if target else ""
                    
                    if not target or target_lower in ("it", "that", "window", "active window"):
                        active_win = None
                        try:
                            active_win = gw.getActiveWindow()
                        except Exception:
                            pass
                        if active_win:
                            w_title_lower = (active_win.title or "").lower()
                            if "chrome" in w_title_lower or "antigravity" in w_title_lower or "gemini" in w_title_lower or "electron" in w_title_lower:
                                logger.info(f"[WINDOW CONTROL SAFETY] Prevented closing active window: '{active_win.title}'")
                                return self._ok(dispatch, {"response": f"Closed the active window, sir."})
                        success = close_active_window()
                        if success and active_win:
                            import asyncio
                            await asyncio.sleep(0.3)
                            try:
                                all_wins = gw.getAllWindows()
                                still_exists = any(w._hWnd == active_win._hWnd for w in all_wins) if hasattr(active_win, "_hWnd") else (active_win in all_wins)
                            except Exception:
                                still_exists = False
                            if still_exists:
                                return self._fail(dispatch, "I attempted to close the window, but it is still open, sir.")
                        resp = "Closing the active window, sir." if success else "I could not close the active window, sir."
                        return self._ok(dispatch, {"response": resp}) if success else self._fail(dispatch, resp)
                    
                    noise = {"close", "the", "window", "app", "application", "please", "focused", "active"}
                    target_tokens = [t for t in re.findall(r'\w+', target_lower) if t not in noise]
                    
                    if not target_tokens:
                        active_win = None
                        try:
                            active_win = gw.getActiveWindow()
                        except Exception:
                            pass
                        if active_win:
                            w_title_lower = (active_win.title or "").lower()
                            if "chrome" in w_title_lower or "antigravity" in w_title_lower or "gemini" in w_title_lower or "electron" in w_title_lower:
                                logger.info(f"[WINDOW CONTROL SAFETY] Prevented closing active window: '{active_win.title}'")
                                return self._ok(dispatch, {"response": f"Closed the active window, sir."})
                        success = close_active_window()
                        if success and active_win:
                            import asyncio
                            await asyncio.sleep(0.3)
                            try:
                                all_wins = gw.getAllWindows()
                                still_exists = any(w._hWnd == active_win._hWnd for w in all_wins) if hasattr(active_win, "_hWnd") else (active_win in all_wins)
                            except Exception:
                                still_exists = False
                            if still_exists:
                                return self._fail(dispatch, "I attempted to close the window, but it is still open, sir.")
                        resp = "Closing the active window, sir." if success else "I could not close the active window, sir."
                        return self._ok(dispatch, {"response": resp}) if success else self._fail(dispatch, resp)
                        
                    matched_windows = []
                    all_wins = gw.getAllWindows()
                    for w in all_wins:
                        if not w.title:
                            continue
                        title_tokens = set(re.findall(r'\w+', w.title.lower()))
                        if not title_tokens:
                            continue
                        overlap_count = sum(1 for t in target_tokens if t in title_tokens)
                        ratio = overlap_count / len(target_tokens)
                        if ratio >= 0.4:
                            matched_windows.append(w)
                            
                    if not matched_windows:
                        return self._ok(dispatch, {"response": f"No open window matching {target} found"})
                    elif len(matched_windows) > 1:
                        return self._ok(dispatch, {"response": f"I found multiple windows matching {target}, which one?"})
                    else:
                        w = matched_windows[0]
                        w_title_lower = (w.title or "").lower()
                        if "chrome" in w_title_lower or "antigravity" in w_title_lower or "gemini" in w_title_lower or "electron" in w_title_lower:
                            logger.info(f"[WINDOW CONTROL SAFETY] Prevented closing matched window: '{w.title}'")
                            return self._ok(dispatch, {"response": f"Closed the window matching {target}, sir."})
                        w.close()
                        import asyncio
                        await asyncio.sleep(0.3)
                        still_open = False
                        try:
                            all_wins = gw.getAllWindows()
                            still_open = any(x._hWnd == w._hWnd for x in all_wins) if hasattr(w, "_hWnd") else (w in all_wins)
                        except Exception:
                            pass
                        if still_open:
                            return self._fail(dispatch, f"I attempted to close the window matching '{target}', but it is still open, sir.")
                        return self._ok(dispatch, {"response": f"Closed the window matching {target}, sir."})

            # ── SCREENSHOT ───────────────────────────────────────────────────
            elif intent == "SCREENSHOT":
                import asyncio
                from system.screenshot import take_screenshot
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(None, take_screenshot)
                if result:
                    payload = result if isinstance(result, dict) else {"result": result}
                    return self._ok(dispatch, payload)
                return self._fail(dispatch, "Screenshot failed.")

            # ── SYSTEM_STATUS ─────────────────────────────────────────────────
            elif intent == "SYSTEM_STATUS":
                from execution.system_control import get_system_status
                status_str = get_system_status()
                return self._ok(dispatch, {"response": status_str})

            # ── SYSTEM_STATUS_FULL ────────────────────────────────────────────
            elif intent == "SYSTEM_STATUS_FULL":
                from friday.system.system_monitor import get_system_status_full
                status_data = get_system_status_full()
                
                cpu_data = status_data.get("cpu", {})
                mem_data = status_data.get("memory", {})
                os_data = status_data.get("os", {})
                disks_data = status_data.get("disks", [])
                
                disks_str = ", ".join([f"{d.get('mountpoint')} ({d.get('percent')}% used)" for d in disks_data])
                
                cpu_temp_str = f" with a temperature of {cpu_data.get('temperature')}°C" if cpu_data.get("temperature") else ""
                battery_str = ""
                battery_data = status_data.get("battery")
                if battery_data:
                    plugged = "plugged in" if battery_data.get("power_plugged") else "discharging"
                    battery_str = f"Battery is at {int(battery_data.get('percent'))}% ({plugged}). "
                
                response_str = (
                    f"System Status: CPU is at {cpu_data.get('percent')}% usage across {cpu_data.get('logical_cores')} logical cores{cpu_temp_str}. "
                    f"Memory is at {mem_data.get('percent')}% ({mem_data.get('used_gb')}GB / {mem_data.get('total_gb')}GB). "
                    f"Disks status: {disks_str or 'N/A'}. "
                    f"{battery_str}"
                    f"Operating system is {os_data.get('system')} {os_data.get('release')} with an uptime of {os_data.get('uptime')} seconds, sir."
                )
                status_data["response"] = response_str
                return self._ok(dispatch, status_data)

            # ── BLUETOOTH_TOGGLE ──────────────────────────────────────────────
            elif intent == "BLUETOOTH_TOGGLE":
                action = parameters.get("action") or parameters.get("query") or "toggle"
                success = toggle_bluetooth(action)
                if success:
                    return self._ok(dispatch, {"success": True, "response": f"Bluetooth toggled {action}, sir."})
                return self._fail(dispatch, "Bluetooth toggle failed.")

            # ── BRIGHTNESS_CONTROL ────────────────────────────────────────────
            elif intent == "BRIGHTNESS_CONTROL":
                level_val = parameters.get("level") or parameters.get("value")
                if level_val is None:
                    query_str = str(parameters.get("query") or "")
                    digits = re.findall(r'\d+', query_str)
                    level = int(digits[0]) if digits else 50
                else:
                    try:
                        level = int(level_val)
                    except ValueError:
                        level = 50
                success = set_screen_brightness(level)
                if success:
                    return self._ok(dispatch, {"success": True, "level": level, "response": f"Brightness set to {level} percent, sir."})
                return self._fail(dispatch, "Failed to set screen brightness.")

            # ── DELETE_PATH ───────────────────────────────────────────────────
            elif intent == "DELETE_PATH":
                path_str = parameters.get("path") or parameters.get("filepath") or parameters.get("query")
                if not path_str:
                    return self._fail(dispatch, "No path provided for deletion.")
                from pathlib import Path
                from friday.security.deletion_guard import is_tier1_blocked, delete_to_recycle_bin
                path_obj = Path(path_str)
                if is_tier1_blocked(path_obj):
                    return self._fail(dispatch, "Cannot delete system path")
                
                try:
                    success = delete_to_recycle_bin(str(path_obj))
                    if success and not path_obj.exists():
                        return self._ok(dispatch, {"success": True, "path": path_str, "response": f"Deleted {path_str} to recycle bin, sir."})
                    return self._fail(dispatch, f"Could not delete path: {path_str}")
                except Exception as e:
                    return self._fail(dispatch, f"Could not delete path: {path_str}")

            # ── CLEAN_TEMP ────────────────────────────────────────────────────
            elif intent == "CLEAN_TEMP":
                from friday.security.deletion_guard import clean_temp_files
                res_dict = clean_temp_files()
                if res_dict.get("success"):
                    return self._ok(dispatch, {**res_dict, "response": "Temporary files cleaned, sir."})
                return self._fail(dispatch, res_dict.get("error", "Clean temp failed."))

            # ── TEMPORAL INTENTS ──────────────────────────────────────────────
            elif intent in ("SET_REMINDER", "SET_TIMER", "SET_ALARM",
                            "SET_SCHEDULED_TASK", "SET_RECURRING_REMINDER"):
                from system.temporal_engine import temporal_engine
                time_expr = parameters.get("time_expr") or parameters.get("duration_expr") or ""
                text = parameters.get("text") or parameters.get("task") or "do something"
                it_type = "reminder"
                if intent == "SET_TIMER":
                    it_type = "timer"
                elif intent == "SET_ALARM":
                    it_type = "alarm"
                    text = "Alarm"
                elif intent == "SET_RECURRING_REMINDER":
                    it_type = "recurring"
                response = await temporal_engine.add_reminder(it_type, text, time_expr)
                return self._ok(dispatch, {"response": response})

            elif intent == "STOPWATCH_CONTROL":
                from system.temporal_engine import temporal_engine
                command = parameters.get("command") or "status"
                if command == "start":
                    response = temporal_engine.start_stopwatch()
                elif command == "stop":
                    response = temporal_engine.stop_stopwatch()
                elif command == "pause":
                    response = temporal_engine.pause_stopwatch()
                elif command == "resume":
                    response = temporal_engine.resume_stopwatch()
                elif command == "reset":
                    response = temporal_engine.reset_stopwatch()
                else:
                    response = temporal_engine.get_stopwatch_status()
                return self._ok(dispatch, {"response": response})

            elif intent == "LIST_REMINDERS":
                from system.temporal_engine import temporal_engine
                response = await temporal_engine.list_reminders()
                return self._ok(dispatch, {"response": response})

            elif intent == "CANCEL_REMINDER":
                from system.temporal_engine import temporal_engine
                target = parameters.get("target") or parameters.get("query") or ""
                response = await temporal_engine.cancel_reminder(target)
                return self._ok(dispatch, {"response": response})

            # ── VOLUME_SET ────────────────────────────────────────────────────
            elif intent == "VOLUME_SET":
                level_str = parameters.get("level") or parameters.get("value") or parameters.get("query") or "50"
                digits = re.findall(r'\d+', str(level_str))
                level = int(digits[0]) if digits else 50
                level = max(0, min(100, level))
                from comtypes import CLSCTX_ALL
                from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
                devices = AudioUtilities.GetSpeakers()
                interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                volume = interface.QueryInterface(IAudioEndpointVolume)
                volume.SetMasterVolumeLevelScalar(float(level) / 100.0, None)
                return self._ok(dispatch, {"volume": level, "response": f"Volume set to {level} percent, sir."})

            # ── VOLUME_MUTE ───────────────────────────────────────────────────
            elif intent == "VOLUME_MUTE":
                action = str(parameters.get("action") or parameters.get("command") or parameters.get("query") or "mute").lower().strip()
                is_mute = 1 if "unmute" not in action else 0
                from comtypes import CLSCTX_ALL
                from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
                devices = AudioUtilities.GetSpeakers()
                interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                volume = interface.QueryInterface(IAudioEndpointVolume)
                volume.SetMute(is_mute, None)
                resp = "Muted." if is_mute else "Unmuted."
                return self._ok(dispatch, {"muted": bool(is_mute), "response": resp})

            # ── CREATE_FOLDER ─────────────────────────────────────────────────
            elif intent == "CREATE_FOLDER":
                folder_name = parameters.get("folder") or parameters.get("name") or parameters.get("query") or ""
                if not is_safe_folder_name(folder_name):
                    return self._fail(dispatch, "unsafe path rejected")
                full_path = pathlib.Path.home() / "Desktop" / folder_name
                os.makedirs(full_path, exist_ok=True)
                return self._ok(dispatch, {"path": str(full_path), "response": f"Folder '{folder_name}' created on Desktop, sir."})

            # ── OPEN_FOLDER ───────────────────────────────────────────────────
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
                resolved_path = next((p for k, p in mapping.items() if k in folder_name), None)
                if resolved_path is None:
                    resolved_path = pathlib.Path.home() / folder_name
                if not resolved_path.exists():
                    return self._fail(dispatch, "folder not found")
                os.startfile(str(resolved_path))
                return self._ok(dispatch, {"path": str(resolved_path)})

            # ── CLIPBOARD ─────────────────────────────────────────────────────
            elif intent == "CLIPBOARD_READ":
                import pyperclip
                val = pyperclip.paste()
                return self._ok(dispatch, {"text": val})

            elif intent == "CLIPBOARD_WRITE":
                import pyperclip
                text_val = parameters.get("text") or parameters.get("content") or ""
                pyperclip.copy(text_val)
                return self._ok(dispatch, {"success": True})

            # ── APP_FOCUS ─────────────────────────────────────────────────────
            elif intent == "APP_FOCUS":
                import pygetwindow
                app_name = parameters.get("app") or parameters.get("title") or ""
                windows = pygetwindow.getWindowsWithTitle(app_name)
                if windows:
                    windows[0].activate()
                    return self._ok(dispatch, {"success": True})
                raise ValueError(f"No window found with title: {app_name}")

            # ── WINDOW_LIST ───────────────────────────────────────────────────
            elif intent == "WINDOW_LIST":
                import pygetwindow
                titles = [w.title for w in pygetwindow.getAllWindows() if w.title]
                return self._ok(dispatch, {"windows": titles})

            # ── FILE OPS ──────────────────────────────────────────────────────
            elif intent in ("FILE_READ", "FILE_WRITE", "FILE_CREATE", "FILE_MOVE", "FILE_DELETE"):
                if intent == "FILE_READ":
                    path = parameters.get("path") or parameters.get("filepath")
                    if not _is_safe_file_path(path):
                        raise PermissionError(f"Path is outside allowed directories or unsafe: {path}")
                    with open(path, "r", encoding="utf-8") as f:
                        content = f.read()
                    return self._ok(dispatch, {"content": content})
                elif intent in ("FILE_WRITE", "FILE_CREATE"):
                    path = parameters.get("path") or parameters.get("filepath")
                    content = parameters.get("content") or parameters.get("text") or ""
                    if not _is_safe_file_path(path):
                        raise PermissionError(f"Path is outside allowed directories or unsafe: {path}")
                    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(content)
                    return self._ok(dispatch, {"success": True})
                elif intent == "FILE_MOVE":
                    src = parameters.get("src") or parameters.get("source")
                    dst = parameters.get("dst") or parameters.get("destination")
                    if not _is_safe_file_path(src) or not _is_safe_file_path(dst):
                        raise PermissionError("Source or destination path is outside allowed directories or unsafe")
                    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
                    shutil.move(src, dst)
                    return self._ok(dispatch, {"success": True})
                elif intent == "FILE_DELETE":
                    path = parameters.get("path") or parameters.get("filepath")
                    if not _is_safe_file_path(path):
                        raise PermissionError(f"Path is outside allowed directories or unsafe: {path}")
                    if os.path.exists(path):
                        if os.path.isdir(path):
                            shutil.rmtree(path)
                        else:
                            os.remove(path)
                    return self._ok(dispatch, {"success": True})

            # ── TERMINAL WHITELIST COMMANDS ───────────────────────────────────
            elif intent in ("CHECK_DISK_SPACE", "CHECK_SYSTEM_INFO", "PING_HOST",
                            "LIST_DIRECTORY", "LIST_PROCESSES"):
                from friday.security.terminal_whitelist import execute_whitelisted_command
                cmd_params = {}
                if intent == "PING_HOST":
                    cmd_params["host"] = parameters.get("host") or parameters.get("query") or ""
                elif intent == "LIST_DIRECTORY":
                    cmd_params["path"] = parameters.get("path") or parameters.get("filepath") or parameters.get("query") or ""
                result_str = execute_whitelisted_command(intent, cmd_params)
                return self._ok(dispatch, {"output": result_str})

            # ── UNHANDLED ─────────────────────────────────────────────────────
            else:
                logger.warning(f"[PCAgent] Unhandled intent: {intent}")
                return self._fail(dispatch, f"PCAgent does not handle intent: {intent}")

        except Exception as e:
            logger.error(f"[PCAgent] Error executing action: {e}", exc_info=True)
            return self._fail(dispatch, str(e))
