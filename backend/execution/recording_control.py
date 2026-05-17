import os

import subprocess

from datetime import datetime

# =========================================
# SAVE DIRECTORY
# =========================================

RECORDING_DIR = (
    r"C:\Users\gpska\OneDrive\Pictures\screenshots"
)

os.makedirs(

    RECORDING_DIR,

    exist_ok=True
)

recording_process = None

# =========================================
# START RECORDING
# =========================================

def start_recording():

    global recording_process

    try:

        timestamp = datetime.now().strftime(

            "%Y%m%d_%H%M%S"
        )

        output = os.path.join(

            RECORDING_DIR,

            f"recording_{timestamp}.mp4"
        )

        command = [

            "ffmpeg",

            "-y",

            "-f",

            "gdigrab",

            "-framerate",

            "30",

            "-i",

            "desktop",

            output
        ]

        recording_process = subprocess.Popen(
            command
        )

        return True

    except Exception as e:

        print(
            "[RECORDING ERROR]",
            e
        )

        return False

# =========================================
# STOP RECORDING
# =========================================

def stop_recording():

    global recording_process

    try:

        if recording_process:

            recording_process.terminate()

            recording_process = None

            return True

    except Exception as e:

        print(
            "[STOP RECORDING ERROR]",
            e
        )

    return False
