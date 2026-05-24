import os
import winreg
from pathlib import Path
import re

from config.site_registry import get_workspace_url, infer_url
from system.chrome_opener import open_url_in_chrome


# =========================================
# CENTRALIZED WINDOWS SETTINGS URI MAP
# =========================================

SETTINGS_MAP = {
    "settings": "ms-settings:",
    "settings app": "ms-settings:",
    "bluetooth settings": "ms-settings:bluetooth",
    "wifi settings": "ms-settings:network-wifi",
    "display settings": "ms-settings:display",
    "sound settings": "ms-settings:sound",
    "storage settings": "ms-settings:storagesense",
    "battery settings": "ms-settings:batterysaver",
    "windows update": "ms-settings:windowsupdate",
    "apps settings": "ms-settings:appsfeatures",
    "startup apps": "ms-settings:startupapps",
    "lock screen settings": "ms-settings:lockscreen",
    "personalization settings": "ms-settings:personalization",
}

# =========================================
# LEGACY NATIVE SHELL SHORTCUTS
# =========================================

APP_MAP = {
    "calculator": "calc",
    "chrome": "chrome",
    "task manager": "taskmgr",
    "notepad": "notepad",
    "spotify": "spotify",
    "spotify app": "spotify",
    "snipping tool": "explorer ms-screenclip:",
    "cmd": "cmd",
    "command prompt": "cmd",
    "powershell": "powershell",
    "paint": "mspaint",
    "mspaint": "mspaint",
    "control panel": "control",
    "wordpad": "write",
}

# =========================================
# SPECIAL FOLDERS
# =========================================

SPECIAL_FOLDERS = {
    "downloads": str(Path.home() / "Downloads"),
    "documents": str(Path.home() / "Documents"),
    "desktop": str(Path.home() / "Desktop"),
    "pictures": str(Path.home() / "Pictures"),
    "videos": str(Path.home() / "Videos"),
    "music": str(Path.home() / "Music"),
}

# =========================================
# DEEP SEARCH DIR CONFIG
# =========================================

SEARCH_PATHS = [
    Path.home() / "Documents",
    Path.home() / "Desktop",
    Path.home() / "Downloads",
    Path.home() / "Pictures",
    Path.home() / "Videos"
]


# =========================================
# DYNAMIC WINDOWS APP DISCOVERY ENGINE
# =========================================

_APP_DISCOVERY_INDEX = {}

def scan_installed_apps():
    """
    Builds a dynamic index mapping lowercase program/shortcut names to their executable
    or shortcut (.lnk) file paths in Windows. Extremely resilient and fast.
    """
    global _APP_DISCOVERY_INDEX
    _APP_DISCOVERY_INDEX = {}

    # 1. Registry App Paths Scanning
    for hkey in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"
            with winreg.OpenKey(hkey, key_path) as key:
                num_subkeys = winreg.QueryInfoKey(key)[0]
                for i in range(num_subkeys):
                    try:
                        subkey_name = winreg.EnumKey(key, i)
                        with winreg.OpenKey(key, subkey_name) as subkey:
                            try:
                                exe_path = winreg.QueryValue(subkey, "")
                                if exe_path:
                                    # Resolve env vars and strip outer quotes
                                    exe_path = os.path.expandvars(exe_path).strip(' "')
                                    if os.path.exists(exe_path):
                                        name = subkey_name.lower().replace(".exe", "").strip()
                                        _APP_DISCOVERY_INDEX[name] = exe_path
                            except OSError:
                                pass
                    except OSError:
                        pass
        except OSError:
            pass

    # 2. Start Menu Program Directories Scanning (.lnk / .url shortcuts)
    start_menu_paths = []
    # User Start Menu
    appdata = os.getenv("APPDATA")
    if appdata:
        start_menu_paths.append(Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    # System Start Menu
    allusers = os.getenv("ALLUSERSPROFILE")
    if allusers:
        start_menu_paths.append(Path(allusers) / "Microsoft" / "Windows" / "Start Menu" / "Programs")

    # 3. Desktop Folders Scanning
    userprofile = os.getenv("USERPROFILE")
    if userprofile:
        start_menu_paths.append(Path(userprofile) / "Desktop")
    public_desktop = Path("C:/Users/Public/Desktop")
    if public_desktop.exists():
        start_menu_paths.append(public_desktop)

    # Walk directories recursively to locate shortcut/executable paths
    for base_dir in start_menu_paths:
        if not base_dir.exists():
            continue
        try:
            for root, dirs, files in os.walk(str(base_dir)):
                for f in files:
                    if f.lower().endswith((".lnk", ".url", ".exe")):
                        full_path = os.path.join(root, f)
                        base_name = f.rsplit(".", 1)[0].lower().strip()
                        if base_name and base_name not in _APP_DISCOVERY_INDEX:
                            _APP_DISCOVERY_INDEX[base_name] = full_path
        except Exception as e:
            print(f"[APP DISCOVERY WARNING] Failed walking {base_dir}: {e}")

    # Add popular user mappings for convenience
    _APP_DISCOVERY_INDEX["vscode"] = _APP_DISCOVERY_INDEX.get("visual studio code", "")
    _APP_DISCOVERY_INDEX["code"] = _APP_DISCOVERY_INDEX.get("visual studio code", "")

    print(f"[APP DISCOVERY] Windows Native App Discovery Engine indexed {len(_APP_DISCOVERY_INDEX)} programs.")


# Trigger dynamic scan on module loading
try:
    scan_installed_apps()
except Exception as e:
    print(f"[APP DISCOVERY ERROR] Startup scanning failed: {e}")


def find_folder(folder_name: str):
    folder_name = folder_name.lower().strip()
    for base_path in SEARCH_PATHS:
        try:
            for root, dirs, files in os.walk(base_path):
                for d in dirs:
                    if folder_name == d.lower() or folder_name in d.lower():
                        return os.path.join(root, d)
        except OSError:
            continue
    return None


# =========================================
# OPEN APP / WEBSITE / FOLDER
# =========================================

def open_app(app_name: str):
    try:
        app_name = (
            app_name
            .lower()
            .strip()
        )
        if not app_name:
            return False

        print(f"[APP CONTROL] Resolving native vs web intent for target: '{app_name}'")

        # ── 1. NATIVE FILE EXPLORER ──────────────────────────────────────────
        if app_name in ("explorer", "file explorer", "windows explorer", "my computer"):
            print("[APP CONTROL] Launching explorer.exe natively")
            os.system("start explorer.exe")
            return True

        # ── 2. PHYSICAL DRIVE PATTERNS (e.g. "c drive", "d drive", "c:") ─────
        drive_match = re.match(r"^([a-z])\s*(?:drive|:)?$", app_name)
        if drive_match:
            drive_letter = drive_match.group(1).upper()
            drive_path = f"{drive_letter}:\\"
            if os.path.exists(drive_path):
                print(f"[APP CONTROL] Opening physical drive: {drive_path}")
                os.startfile(drive_path)
                return True

        # ── 3. DIRECT LOCAL DIRECTORY / FILE PATH ────────────────────────────
        if os.path.exists(app_name):
            print(f"[APP CONTROL] Path exists locally. Opening native file/directory: '{app_name}'")
            os.startfile(app_name)
            return True

        # ── 4. SPECIAL SYSTEM DIRECTORIES ─────────────────────────────────────
        if app_name in SPECIAL_FOLDERS:
            folder_path = SPECIAL_FOLDERS[app_name]
            if os.path.exists(folder_path):
                print(f"[APP CONTROL] Opening special folder: '{app_name}' -> '{folder_path}'")
                os.startfile(folder_path)
                return True

        # ── 5. DYNAMIC WINDOWS APP DISCOVERY ENGINE (Registry & Start Menu) ──
        # Perform dynamic mapping against our indexed shortcuts/programs
        target_path = _APP_DISCOVERY_INDEX.get(app_name)
        # Check standard synonyms (e.g. "spotify app" -> "spotify")
        if not target_path and app_name.endswith(" app"):
            target_path = _APP_DISCOVERY_INDEX.get(app_name.replace(" app", "").strip())

        if target_path and os.path.exists(target_path):
            print(f"[APP CONTROL] Dynamic discovery matched '{app_name}' to '{target_path}'. Launching.")
            os.startfile(target_path)
            return True

        # Fuzzy search substring match if no exact match (e.g. "open visual studio" matches "visual studio code")
        for key, val in _APP_DISCOVERY_INDEX.items():
            if val and os.path.exists(val) and (app_name in key or key in app_name) and len(app_name) >= 4:
                print(f"[APP CONTROL] Dynamic discovery fuzzy-matched '{app_name}' to '{key}' -> '{val}'. Launching.")
                os.startfile(val)
                return True

        # ── 6. DEEP SEARCH FOLDERS ───────────────────────────────────────────
        folder_path = find_folder(app_name)
        if folder_path:
            print(f"[APP CONTROL] Folder found via search path. Opening: '{folder_path}'")
            os.startfile(folder_path)
            return True

        # ── 7. SETTINGS URI ──────────────────────────────────────────────────
        if app_name in SETTINGS_MAP:
            uri = SETTINGS_MAP[app_name]
            print(f"[APP CONTROL] Launching Windows Settings URI: '{uri}'")
            os.system(f"start {uri}")
            return True

        # ── 8. NATIVE SYSTEM SHORTCUTS (Legacy commands) ──────────────────────
        app_cmd = APP_MAP.get(app_name)
        if app_cmd:
            print(f"[APP CONTROL] Launching native legacy command: '{app_cmd}'")
            os.system(f"start {app_cmd}")
            return True

        # ── 9. OS-LEVEL GENERIC SHELL OPEN ────────────────────────────────────
        try:
            print(f"[APP CONTROL] Attempting generic shell launch for: '{app_name}'")
            os.startfile(app_name)
            return True
        except OSError:
            pass

        # ── 10. REGISTERED WORKSPACE WEBSITES (Chrome) ──────────────────────────
        site_url = get_workspace_url(app_name)
        if site_url:
            print(f"[APP CONTROL] Launching registered website: '{app_name}' -> '{site_url}'")
            return open_url_in_chrome(site_url)

        # ── 11. WEB INFERENCE FALLBACK ──────────────────────────────────────────
        inferred = infer_url(app_name)
        print(f"[APP CONTROL] All local options exhausted. Inferred URL: '{app_name}' -> '{inferred}'")
        return open_url_in_chrome(inferred)

    except Exception as e:
        print(f"[APP CONTROL ERROR] {e}")
        return False
