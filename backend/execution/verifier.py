import os
import psutil
import time

def verify_app_running(exe_name: str) -> bool:
    """Check if a process with a given name is running in Windows."""
    name_lower = exe_name.lower()
    try:
        for proc in psutil.process_iter(['name']):
            try:
                pname = proc.info['name']
                if pname and name_lower in pname.lower():
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
    except Exception as e:
        print(f"[VERIFIER ERROR] psutil process scan failed: {e}")
    return False

def verify_action(intent_data: dict, success: bool) -> bool:
    """
    Verify if an action actually succeeded on the OS layer.
    Checks:
      - OPEN: If target is a directory/path, verify os.path.exists. If it is an app, verify running process.
      - CLARIFICATION: Always returns True (speech output is verbal).
      - Otherwise: return the success boolean directly.
    """
    if not success:
        return False

    intent = intent_data.get("intent")
    
    if intent == "OPEN":
        target = (intent_data.get("target") or "").lower().strip()
        
        # 1. Drive check / Explorer targets
        if target in ("explorer", "file explorer", "windows explorer", "my computer") or target.endswith("drive") or len(target) == 1 or target.endswith(":"):
            # Drives are opened via explorer.exe
            time.sleep(1.0) # short delay for OS window spin up
            return verify_app_running("explorer.exe")
            
        # 2. Direct File / Directory path check
        if os.path.exists(target):
            return True
            
        # 3. Native App maps
        _EXE_MAP = {
            "calculator": "calc.exe",
            "chrome": "chrome.exe",
            "task manager": "taskmgr.exe",
            "notepad": "notepad.exe",
            "spotify": "spotify.exe",
            "cmd": "cmd.exe",
            "powershell": "powershell.exe",
            "paint": "mspaint.exe",
            "mspaint": "mspaint.exe",
            "control panel": "control.exe",
            "wordpad": "wordpad.exe"
        }
        for name, exe in _EXE_MAP.items():
            if name in target:
                # Allow a short delay for OS process creation
                time.sleep(1.2)
                return verify_app_running(exe)
                
        # Default fallback for URLs or unlisted tools
        return True

    if intent == "CLARIFICATION":
        return True

    return success
