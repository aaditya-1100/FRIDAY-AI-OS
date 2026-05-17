"""
voice/speak.py — TTS synthesis + playback.

Modes:
  web_mode=False  → pygame plays audio locally (CLI / desktop)
  web_mode=True   → base64 audio sent to browser via WebSocket

Cancel contract:
  _sync_play checks _cancelled every 50ms so it exits immediately
  when cancel_speak() is called from another thread.
"""
import asyncio
import edge_tts
import tempfile
import os
import pygame
import time
import threading

VOICE = "en-IN-NeerjaNeural"

# Cancellation flag — set by cancel_play() from any thread
_play_cancelled = threading.Event()


def cancel_play() -> None:
    """Stop any active pygame playback immediately."""
    _play_cancelled.set()
    try:
        if pygame.mixer.get_init():
            pygame.mixer.music.stop()
    except Exception:
        pass


def _sync_play(temp_path: str) -> None:
    _play_cancelled.clear()
    try:
        if not pygame.mixer.get_init():
            pygame.mixer.init(frequency=22050, size=-16, channels=1, buffer=512)
        pygame.mixer.music.load(temp_path)
        pygame.mixer.music.play()
        # Poll until done OR cancelled
        while pygame.mixer.music.get_busy():
            if _play_cancelled.is_set():
                pygame.mixer.music.stop()
                break
            time.sleep(0.05)
    finally:
        try:
            pygame.mixer.music.stop()
        except Exception:
            pass
        try:
            pygame.mixer.music.unload()
        except Exception:
            pass
        try:
            pygame.mixer.quit()
        except Exception:
            pass


async def speak(text: str, web_mode: bool = False) -> None:

    if not text:
        return
    text = str(text).strip()
    if not text:
        return

    temp_path = None

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
            temp_path = tmp.name

        # Retry up to 3 times for transient TTS network failures
        last_err = None
        for attempt in range(3):
            try:
                communicate = edge_tts.Communicate(text=text, voice=VOICE)
                # 15-second timeout per attempt
                await asyncio.wait_for(communicate.save(temp_path), timeout=15.0)
                last_err = None
                break
            except asyncio.CancelledError:
                raise   # let the pipeline handle shutdown
            except Exception as e:
                last_err = e
                print(f"[TTS ATTEMPT {attempt + 1}/3 FAILED] {e}")
                if attempt < 2:
                    await asyncio.sleep(0.4)

        if last_err:
            print(f"[TTS ERROR] All 3 attempts failed: {last_err}")
            return

        if web_mode:
            import base64
            from core.realtime_emit import emit_json
            with open(temp_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
            await emit_json({"type": "audio", "audioBase64": b64})
        else:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, _sync_play, temp_path)

    except asyncio.CancelledError:
        # Ensure pygame stops if we are cancelled mid-play
        cancel_play()
        raise
    except Exception as e:
        print(f"[TTS ERROR] {e}")

    finally:
        # Windows may hold a file lock briefly after mixer.quit() — retry
        if temp_path and os.path.exists(temp_path):
            for _ in range(6):
                try:
                    os.remove(temp_path)
                    break
                except OSError:
                    time.sleep(0.1)