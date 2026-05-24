import ctypes
import sys

# Virtual-Key Codes
VK_MEDIA_NEXT_TRACK = 0xB5
VK_MEDIA_PREV_TRACK = 0xB6
VK_MEDIA_PLAY_PAUSE = 0xB3
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF

KEYEVENTF_KEYUP = 0x0002

def send_key(vk_code: int) -> bool:
    if sys.platform != "win32":
        print(f"[SPOTIFY] Windows-only native key control. Simulating vk_code {vk_code} is skipped.")
        return False
    try:
        # Press
        ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)
        # Release
        ctypes.windll.user32.keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)
        return True
    except Exception as e:
        print(f"[SPOTIFY] Error sending keybd_event: {e}")
        return False

def play_pause() -> bool:
    print("[SPOTIFY] Action: Play/Pause")
    return send_key(VK_MEDIA_PLAY_PAUSE)

def next_track() -> bool:
    print("[SPOTIFY] Action: Next Track")
    return send_key(VK_MEDIA_NEXT_TRACK)

def prev_track() -> bool:
    print("[SPOTIFY] Action: Previous Track")
    return send_key(VK_MEDIA_PREV_TRACK)

def volume_up() -> bool:
    print("[SPOTIFY] Action: Volume Up")
    # Send multiple volume ups for a noticeable difference
    success = True
    for _ in range(5):
        success = send_key(VK_VOLUME_UP) and success
    return success

def volume_down() -> bool:
    print("[SPOTIFY] Action: Volume Down")
    # Send multiple volume downs for a noticeable difference
    success = True
    for _ in range(5):
        success = send_key(VK_VOLUME_DOWN) and success
    return success

def control_spotify(command: str) -> str:
    cmd = command.lower().strip()
    if "play" in cmd or "pause" in cmd or "resume" in cmd:
        play_pause()
        return "Toggled play/pause on Spotify."
    elif "next" in cmd or "skip" in cmd:
        next_track()
        return "Skipped to the next track."
    elif "previous" in cmd or "back" in cmd:
        prev_track()
        return "Played the previous track."
    elif "up" in cmd or "louder" in cmd or "increase" in cmd:
        volume_up()
        return "Increased system volume."
    elif "down" in cmd or "quieter" in cmd or "decrease" in cmd:
        volume_down()
        return "Decreased system volume."
    else:
        return "Unsupported Spotify control command."
