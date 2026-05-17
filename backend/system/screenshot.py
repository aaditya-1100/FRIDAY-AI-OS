import pyautogui

from pathlib import Path
from datetime import datetime


# =========================================
# SCREENSHOT FUNCTION
# Saves to C:\Users\gpska\OneDrive\Pictures
# =========================================

SCREENSHOTS_DIR = Path("C:/Users/gpska/OneDrive/Pictures")


def take_screenshot():

    try:
        # Use OneDrive Pictures folder; fall back to ~/Pictures if it doesn't exist
        save_dir = SCREENSHOTS_DIR if SCREENSHOTS_DIR.exists() else Path.home() / "Pictures"
        save_dir.mkdir(parents=True, exist_ok=True)

        filename = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        file_path = save_dir / filename

        screenshot = pyautogui.screenshot()
        screenshot.save(file_path)

        print(f"[SCREENSHOT] Saved: {file_path}")

        # Return ai_response so pipeline speaks the result
        return {
            "type": "ai_response",
            "response": f"Screenshot saved to {save_dir.name} folder sir."
        }

    except Exception as e:

        print(f"[SCREENSHOT ERROR] {e}")
        return False