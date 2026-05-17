"""
Helpers used by older execution paths. Website/app opens use system.app_control.open_app
(single Chrome + registry policy).
"""

import os

# Canonical open implementation
from system.app_control import open_app  # noqa: F401

# =========================================
# CREATE FOLDER
# =========================================

def create_folder(path):

    try:

        os.makedirs(

            path,

            exist_ok=True
        )

        return True

    except OSError:

        return False

# =========================================
# CREATE FILE
# =========================================

def create_file(path):

    try:

        with open(path, "w"):

            pass

        return True

    except OSError:

        return False

# =========================================
# SCREENSHOT
# =========================================

def take_screenshot():

    os.system(
        "explorer ms-screenclip:"
    )

    return True

# =========================================
# SCREEN RECORDING
# =========================================

def start_screen_recording():

    os.system(
        "start ms-screenclip:"
    )

    return True
