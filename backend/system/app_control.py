import os

from pathlib import Path

from config.site_registry import get_workspace_url
from system.chrome_opener import open_url_in_chrome


# =========================================
# WINDOWS SETTINGS URI SHORTCUTS (not Chrome)
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
# NATIVE SHELL SHORTCUTS (not Chrome)
# =========================================

APP_MAP = {

    "calculator": "calc",

    "chrome": "start chrome",

    "task manager": "taskmgr",

    "notepad": "notepad",

    "spotify app": "spotify",

    "snipping tool": "explorer ms-screenclip:",
}

# =========================================
# SPECIAL FOLDERS
# =========================================

SPECIAL_FOLDERS = {

    "downloads":
    str(Path.home() / "Downloads"),

    "documents":
    str(Path.home() / "Documents"),

    "desktop":
    str(Path.home() / "Desktop"),

    "pictures":
    str(Path.home() / "Pictures"),

    "videos":
    str(Path.home() / "Videos"),

    "music":
    str(Path.home() / "Music")
}


# =========================================
# SEARCH USER FOLDERS
# =========================================

SEARCH_PATHS = [

    Path.home() / "Documents",

    Path.home() / "Desktop",

    Path.home() / "Downloads",

    Path.home() / "Pictures",

    Path.home() / "Videos"
]


def find_folder(folder_name: str):

    folder_name = folder_name.lower()

    for base_path in SEARCH_PATHS:

        try:

            for root, dirs, files in os.walk(base_path):

                for d in dirs:

                    if folder_name in d.lower():

                        return os.path.join(
                            root,
                            d
                        )

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

        # =====================================
        # REGISTERED WORKSPACE SITES (Chrome)
        # =====================================

        site_url = get_workspace_url(app_name)

        if site_url:

            return open_url_in_chrome(site_url)

        # =====================================
        # SETTINGS URI
        # =====================================

        if app_name in SETTINGS_MAP:

            os.system(f"start {SETTINGS_MAP[app_name]}")

            return True

        # =====================================
        # NATIVE APP SHORTCUTS
        # =====================================

        app_cmd = APP_MAP.get(app_name)

        if app_cmd:

            os.system(app_cmd)

            return True

        # =====================================
        # SPECIAL FOLDERS
        # =====================================

        if app_name in SPECIAL_FOLDERS:

            os.startfile(
                SPECIAL_FOLDERS[app_name]
            )

            return True

        # =====================================
        # SEARCH CUSTOM FOLDER
        # =====================================

        folder_path = find_folder(
            app_name
        )

        if folder_path:

            os.startfile(folder_path)

            return True

        # =====================================
        # GENERIC WINDOWS OPEN
        # =====================================

        try:

            os.startfile(app_name)

            return True

        except OSError:
            pass

        # =====================================
        # FAILED
        # =====================================

        print(
            f"[APP CONTROL] Could not open: {app_name}"
        )

        return False

    except Exception as e:

        print(f"[APP CONTROL ERROR] {e}")

        return False
