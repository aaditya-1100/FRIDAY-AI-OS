"""
voice/speak.py — Robust TTS synthesis + playback with multi-provider fallback.

Providers:
  1. Edge-TTS (Primary: en-IN-NeerjaNeural, high quality)
  2. gTTS (Secondary Online: Google Indian Accent, extremely stable)
  3. pyttsx3 (Tertiary Offline: Windows SAPI5 local TTS engine)

Modes:
  web_mode=False  → pygame plays audio locally (CLI / desktop)
  web_mode=True   → base64 audio sent to browser via WebSocket
"""
import asyncio
import edge_tts
import tempfile
import os
import time
import threading

VOICE = "en-IN-NeerjaNeural"

# Cancellation flag — set by cancel_play() from any thread
_play_cancelled = threading.Event()


def cancel_play() -> None:
    """Stop any active pygame playback immediately."""
    _play_cancelled.set()
    try:
        import pygame
        if pygame.mixer.get_init():
            pygame.mixer.music.stop()
    except Exception:
        pass


def _sync_play(temp_path: str) -> None:
    if _play_cancelled.is_set():
        return  # cancelled before we even began — skip playback entirely
    _play_cancelled.clear()
    try:
        import pygame
        if not pygame.mixer.get_init():
            pygame.mixer.init(frequency=22050, size=-16, channels=1, buffer=512)
        pygame.mixer.music.load(temp_path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            if _play_cancelled.is_set():
                pygame.mixer.music.stop()
                break
            time.sleep(0.05)
    finally:
        try:
            import pygame
            pygame.mixer.music.stop()
        except Exception:
            pass
        try:
            import pygame
            pygame.mixer.music.unload()
        except Exception:
            pass


def _run_sapi_tts(text: str, path: str) -> None:
    """Synchronous helper to run pyttsx3 SAPI5 TTS in executor thread."""
    import pyttsx3
    engine = pyttsx3.init()
    rate = engine.getProperty('rate')
    engine.setProperty('rate', int(rate * 1.15))
    engine.save_to_file(text, path)
    engine.runAndWait()


async def speak(text: str, web_mode: bool = False) -> None:
    if not text:
        return
    text = str(text).strip()
    if not text:
        return

    temp_path = None
    provider_used = None

    try:
        # ─── PROVIDER 1: Edge-TTS (Primary) ───────────────────────────────────
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
                temp_path = tmp.name

            print(f"[TTS] Attempting Edge-TTS: {text[:40]}...")
            communicate = edge_tts.Communicate(text=text, voice=VOICE)
            # Fast timeout (4.0s) to fail over quickly to gTTS if Bing blocks/throttles
            await asyncio.wait_for(communicate.save(temp_path), timeout=4.0)
            provider_used = "Edge-TTS"
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[TTS] Edge-TTS failed: {e}. Trying gTTS...")
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass
            temp_path = None

        # ─── PROVIDER 2: gTTS (Secondary Online Fallback) ─────────────────────
        if provider_used is None:
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
                    temp_path = tmp.name

                print(f"[TTS] Attempting gTTS: {text[:40]}...")
                from gtts import gTTS
                loop = asyncio.get_running_loop()
                tts_obj = gTTS(text=text, lang="en", tld="co.in")
                # Run the blocking gTTS API save in executor
                await asyncio.wait_for(
                    loop.run_in_executor(None, tts_obj.save, temp_path),
                    timeout=5.0
                )
                provider_used = "gTTS"
            except asyncio.CancelledError:
                raise
            except Exception as e:
                print(f"[TTS] gTTS failed: {e}. Trying pyttsx3 offline fallback...")
                if temp_path and os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass
                temp_path = None

        # ─── PROVIDER 3: pyttsx3 (Tertiary Offline Fallback) ──────────────────
        if provider_used is None:
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
                    temp_path = tmp.name

                print(f"[TTS] Attempting pyttsx3 offline (SAPI5): {text[:40]}...")
                loop = asyncio.get_running_loop()
                await asyncio.wait_for(
                    loop.run_in_executor(None, _run_sapi_tts, text, temp_path),
                    timeout=6.0
                )
                provider_used = "pyttsx3"
            except asyncio.CancelledError:
                raise
            except Exception as e:
                print(f"[TTS FATAL] All TTS providers failed: {e}")
                if temp_path and os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass
                return

        print(f"[TTS SUCCESS] Generated speech using {provider_used}")

        from core.state_manager import AssistantState, get_state
        if get_state() != AssistantState.SPEAKING:
            print("[TTS] Playback cancelled by user/state change. Aborting.")
            return

        if web_mode:
            import base64
            from core.realtime_emit import emit_json
            with open(temp_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
            if get_state() == AssistantState.SPEAKING:
                await emit_json({"type": "audio", "audioBase64": b64})
            else:
                print("[TTS] Speak was cancelled during base64 encoding. Aborting.")
        else:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, _sync_play, temp_path)

    except asyncio.CancelledError:
        cancel_play()
        raise
    except Exception as e:
        print(f"[TTS ERROR] {e}")
    finally:
        if temp_path and os.path.exists(temp_path):
            for _ in range(6):
                try:
                    os.remove(temp_path)
                    break
                except OSError:
                    time.sleep(0.1)