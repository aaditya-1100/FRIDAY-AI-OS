import ctypes
import sys
import threading
from system.spotify_client import SpotifyClient

# Virtual-Key Codes for offline/stale hardware control fallback
VK_MEDIA_NEXT_TRACK = 0xB5
VK_MEDIA_PREV_TRACK = 0xB6
VK_MEDIA_PLAY_PAUSE = 0xB3
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF

KEYEVENTF_KEYUP = 0x0002

# Initialize dynamic authenticated client
_spotify_client = SpotifyClient()


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


def play_pause_hardware() -> bool:
    print("[SPOTIFY] Fallback Action: Play/Pause Key")
    return send_key(VK_MEDIA_PLAY_PAUSE)


def next_track_hardware() -> bool:
    print("[SPOTIFY] Fallback Action: Next Track Key")
    return send_key(VK_MEDIA_NEXT_TRACK)


def prev_track_hardware() -> bool:
    print("[SPOTIFY] Fallback Action: Previous Track Key")
    return send_key(VK_MEDIA_PREV_TRACK)


def volume_up() -> bool:
    print("[SPOTIFY] Action: Volume Up")
    success = True
    for _ in range(5):
        success = send_key(VK_VOLUME_UP) and success
    return success


def volume_down() -> bool:
    print("[SPOTIFY] Action: Volume Down")
    success = True
    for _ in range(5):
        success = send_key(VK_VOLUME_DOWN) and success
    return success


def control_spotify(command: str) -> str:
    """
    Direct control routing for Spotify commands.
    Checks authenticated Web API state first, falling back to local SAPI hardware key signals.
    """
    cmd = command.lower().strip()

    # 1. LINKING / AUTHENTICATION INTERCEPT
    if cmd in ("link", "authorize", "connect", "link spotify", "connect spotify", "authorize spotify"):
        if not _spotify_client.is_configured:
            return (
                "Sir, I do not see the SPOTIFY_CLIENT_ID variable "
                "configured in your environment or .env file. Please register a Spotify Developer Application "
                "and populate this variable first."
            )
        
        # Run authentication in a daemon thread so it doesn't block FastAPI / AI loop
        t = threading.Thread(target=_spotify_client.authenticate, daemon=True)
        t.start()
        return (
            "Right away, sir. I have opened the Spotify authorization portal in your default browser. "
            "Please log in and approve the connection, and I will establish direct direct controls."
        )

    # Check if client has OAuth credentials
    has_api = _spotify_client.is_configured and _spotify_client._token_info

    # 2. STATUS AWARENESS (Currently Playing)
    if "status" in cmd or "playing" in cmd or "song" in cmd:
        if not has_api:
            return "Spotify is controlled locally via hardware keys, sir. I cannot poll playback status without authentication."
        
        track_info = _spotify_client.get_currently_playing()
        if not track_info or not track_info.get("item"):
            return "No track is currently playing on your Spotify account, sir."
        
        item = track_info["item"]
        name = item.get("name")
        artists = ", ".join([a.get("name", "") for a in item.get("artists", [])])
        is_playing = track_info.get("is_playing", False)
        status_word = "currently playing" if is_playing else "currently paused on"
        return f"Spotify is {status_word} '{name}' by {artists}, sir."

    # 3. DIRECT ACTION ROUTINGS
    if "play" in cmd or "resume" in cmd:
        if has_api:
            # Try API play
            if _spotify_client.play():
                return "Resumed playback on Spotify."
        # Fallback
        play_pause_hardware()
        return "Resumed playback, sir."

    elif "pause" in cmd or "stop" in cmd:
        if has_api:
            if _spotify_client.pause():
                return "Paused Spotify playback."
        # Fallback
        play_pause_hardware()
        return "Paused playback, sir."

    elif "next" in cmd or "skip" in cmd:
        if has_api:
            if _spotify_client.next():
                return "Skipped to the next track."
        # Fallback
        next_track_hardware()
        return "Skipped to the next track."

    elif "previous" in cmd or "back" in cmd:
        if has_api:
            if _spotify_client.previous():
                return "Playing the previous track."
        # Fallback
        prev_track_hardware()
        return "Playing the previous track."

    elif "up" in cmd or "louder" in cmd or "increase" in cmd:
        if has_api:
            # Let's adjust volume dynamically if possible (e.g. increase by 10%)
            info = _spotify_client.get_currently_playing()
            # Note: Spotify API requires active device to adjust volume
            devices = _spotify_client.get_devices()
            active_device = next((d for d in devices if d.get("is_active")), None)
            if active_device:
                current_vol = active_device.get("volume_percent", 50)
                new_vol = min(100, current_vol + 15)
                if _spotify_client.set_volume(new_vol):
                    return f"Increased Spotify playback volume to {new_vol}%."
        
        # Fallback to system volume
        volume_up()
        return "Increased system volume."

    elif "down" in cmd or "quieter" in cmd or "decrease" in cmd:
        if has_api:
            devices = _spotify_client.get_devices()
            active_device = next((d for d in devices if d.get("is_active")), None)
            if active_device:
                current_vol = active_device.get("volume_percent", 50)
                new_vol = max(0, current_vol - 15)
                if _spotify_client.set_volume(new_vol):
                    return f"Decreased Spotify playback volume to {new_vol}%."
        
        # Fallback to system volume
        volume_down()
        return "Decreased system volume."

    else:
        return "Unsupported Spotify control command, sir."
