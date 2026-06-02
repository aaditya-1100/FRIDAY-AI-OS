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
import re
import traceback
from typing import Optional

VOICE = "en-IN-NeerjaNeural"
current_audio_duration = 20.0

# Global single active speech lock (Mutex) to prevent concurrent overlapping speech
_speak_lock = asyncio.Lock()

def force_unlock_speech(owner_id: Optional[str] = None) -> None:
    """Ownership-aware force release of the speech mutex lock."""
    try:
        if _speak_lock.locked():
            _speak_lock.release()
            print(f"[SPEAK_LOCK] Force unlocked speech lock by owner_id: {owner_id}")
    except Exception as e:
        print(f"[SPEAK_LOCK] Error force releasing speak lock: {e}")

# Cancellation flag — set by cancel_play() from any thread
_play_cancelled = threading.Event()
# Dedicated Response-ID tracked event system to prevent premature mic reactivations and speech truncations.
_playback_events: dict[str, asyncio.Event] = {}
_playback_completed_event: Optional[asyncio.Event] = None

def _ensure_playback_event() -> asyncio.Event:
    global _playback_completed_event
    if _playback_completed_event is None:
        _playback_completed_event = asyncio.Event()
    return _playback_completed_event


def register_playback_completed(response_id: Optional[str] = None):
    # Ensure we set the playback completed event on the correct event loop thread.
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.get_event_loop()

    def _create_and_set():
        if response_id:
            if response_id in _playback_events:
                print(f"[TRACE] [TTS_SPEAK] Received playback_completed from frontend for response_id: {response_id}")
                _playback_events[response_id].set()
            else:
                print(f"[TRACE] [TTS_SPEAK] Warning: Received playback_completed for expired or unknown response_id: {response_id}")
        else:
            print("[TRACE] [TTS_SPEAK] Received playback_completed from frontend without specific response_id. Setting global fallback.")
            ev = _ensure_playback_event()
            ev.set()

    try:
        loop.call_soon_threadsafe(_create_and_set)
    except Exception:
        # Fallback: set directly (usually running on correct loop)
        if response_id and response_id in _playback_events:
            _playback_events[response_id].set()
        else:
            ev = _ensure_playback_event()
            ev.set()


def cancel_play() -> None:
    """Stop any active pygame playback immediately and unblock active speak waiters."""
    _play_cancelled.set()
    # Unblock all waiting speak calls
    try:
        ev = _ensure_playback_event()
        ev.set()
    except Exception:
        pass
    for ev in list(_playback_events.values()):
        try:
            ev.set()
        except Exception:
            pass
    _playback_events.clear()
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
            print("[TTS LOCAL PLAYBACK] Initializing high-fidelity local pygame mixer (44100Hz stereo, buffer=4096)...")
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=4096)
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
    """Thread-safe SAPI5 offline fallback using dynamic thread-local COM apartments."""
    import pythoncom
    import pyttsx3
    
    print("[TTS pyttsx3 SAPI5] Background thread: calling CoInitialize...")
    pythoncom.CoInitialize()
    try:
        print("[TTS pyttsx3 SAPI5] Background thread: initializing pyttsx3...")
        engine = pyttsx3.init()
        voices = engine.getProperty('voices')
        selected_voice = None
        for voice in voices:
            name_lower = voice.name.lower()
            if "zira" in name_lower or "hazel" in name_lower or "female" in name_lower:
                selected_voice = voice.id
                break
        if not selected_voice:
            for voice in voices:
                if "david" not in voice.name.lower() and "male" not in voice.name.lower():
                    selected_voice = voice.id
                    break
        if selected_voice:
            engine.setProperty('voice', selected_voice)
            print(f"[TTS pyttsx3 SAPI5] Selected SAPI5 female voice: {selected_voice}")
        
        rate = engine.getProperty('rate')
        engine.setProperty('rate', int(rate * 1.15))
        
        print(f"[TTS pyttsx3 SAPI5] Background thread: saving synthesis to path: {path}")
        engine.save_to_file(text, path)
        engine.runAndWait()
        print("[TTS pyttsx3 SAPI5] Background thread: synthesis success!")
        del engine
    except Exception as e:
        print(f"[TTS pyttsx3 SAPI5 THREAD ERROR] Dynamic SAPI5 write failed: {e}")
        raise e
    finally:
        print("[TTS pyttsx3 SAPI5] Background thread: calling CoUninitialize...")
        pythoncom.CoUninitialize()

def normalize_speech_text(text: str) -> str:
    """
    Unified Speech Normalizer and shaper.
    Removes markdown code fences, inline code blocks, extra asterisks, hashes,
    and formats bullet lists into natural conversational pauses (commas).
    Guarantees a premium, uniform, and natural conversational cadence.
    """
    if not text:
        return ""
    
    # 1. Clean raw code blocks
    text = re.sub(r"```[\s\S]*?```", " [code block omitted] ", text)
    text = re.sub(r"`[^`]*?`", "", text) # Remove inline code

    # 2. Clean markdown structural headers
    text = re.sub(r"#+\s+", "", text)

    # 3. Form lists into smooth natural pauses (replacing bullet structures with commas)
    text = re.sub(r"^-\s+", ", ", text, flags=re.MULTILINE)
    text = re.sub(r"^\*\s+", ", ", text, flags=re.MULTILINE)
    text = re.sub(r"^\d+\.\s+", ", ", text, flags=re.MULTILINE)

    # 4. Strip markdown bold/italics markers
    text = text.replace("**", "").replace("__", "").replace("*", "").replace("_", "")
    
    # 5. Clean up duplicate structural formatting commas or periods
    text = re.sub(r",\s*,", ", ", text)
    text = re.sub(r"\.\s*\.", ". ", text)

    # 6. Clean up white spaces
    text = re.sub(r"\s+", " ", text).strip()

    # 7. Natural voice expansion of technical acronyms
    text = re.sub(r"\bSAPI5\b", "Sapi 5", text, flags=re.IGNORECASE)
    text = re.sub(r"\bTTS\b", "Text to speech", text, flags=re.IGNORECASE)
    text = re.sub(r"\bLLM\b", "Language model", text, flags=re.IGNORECASE)
    text = re.sub(r"\bLLMs\b", "Language models", text, flags=re.IGNORECASE)
    text = re.sub(r"\bWS\b", "Web socket", text, flags=re.IGNORECASE)
    text = re.sub(r"\bOCR\b", "O C R", text, flags=re.IGNORECASE)
    text = re.sub(r"\bAPI\b", "A P I", text, flags=re.IGNORECASE)

    return text

async def speak(text: str, web_mode: bool = False, response_id: str = None) -> None:
    # Generate unique response ID for tracing if not provided
    if response_id is None:
        import uuid
        response_id = str(uuid.uuid4())[:8]
    
    # Acquire Single-Speech Mutex to prevent overlapping voice collisions
    async with _speak_lock:
        normalized_text = normalize_speech_text(text)
        print(f"[TRACE] [TTS_SPEAK] [{response_id}] ENTERED SPEAK MUTEX | normalized='{normalized_text[:80]}...' | web_mode={web_mode} | text_len={len(text)}")
        if not normalized_text:
            print(f"[TRACE] [TTS_SPEAK] [{response_id}] ABORT: Empty normalized text")
            return

        try:
            from core.runtime_stability import get_stability_manager
            get_stability_manager().touch_audio()
            print(f"[TRACE] [TTS_SPEAK] [{response_id}] Janitor touch audio success")
        except Exception as e_touch:
            print(f"[TRACE] [TTS_SPEAK] [{response_id}] Janitor touch audio failed: {e_touch}")

        temp_path = None
        provider_used = None
        audio_file_size = 0

        try:
            # ─── PROVIDER 1: pyttsx3 (Primary Local Offline - 100% Consistent & Zero Latency) ────
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
                    temp_path = tmp.name

                print(f"[TRACE] [TTS_SPEAK] [{response_id}] [pyttsx3] ATTEMPTING SYNTHESIS | text='{normalized_text[:40]}...' | temp_path={temp_path}")
                loop = asyncio.get_running_loop()
                await asyncio.wait_for(
                    loop.run_in_executor(None, _run_sapi_tts, normalized_text, temp_path),
                    timeout=6.0
                )
                provider_used = "pyttsx3"
                audio_file_size = os.path.getsize(temp_path) if os.path.exists(temp_path) else 0
                print(f"[TRACE] [TTS_SPEAK] [{response_id}] [pyttsx3] SYNTHESIS SUCCESS | provider={provider_used} | file_size={audio_file_size} bytes")
            except asyncio.CancelledError:
                print(f"[TRACE] [TTS_SPEAK] [{response_id}] [pyttsx3] TASK CANCELLED")
                raise
            except Exception as e:
                print(f"[TRACE] [TTS_SPEAK] [{response_id}] [pyttsx3] FAILED: {e} | Falling back to gTTS...")
                if temp_path and os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass
                temp_path = None

            # ─── PROVIDER 2: gTTS (Secondary Online Backup) ───────────────────
            if provider_used is None:
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
                        temp_path = tmp.name

                    print(f"[TRACE] [TTS_SPEAK] [{response_id}] [gTTS] ATTEMPTING SYNTHESIS | text='{normalized_text[:40]}...' | temp_path={temp_path}")
                    from gtts import gTTS
                    loop = asyncio.get_running_loop()
                    tts_obj = gTTS(text=normalized_text, lang="en", tld="co.in")
                    await asyncio.wait_for(
                        loop.run_in_executor(None, tts_obj.save, temp_path),
                        timeout=5.0
                    )
                    provider_used = "gTTS"
                    audio_file_size = os.path.getsize(temp_path) if os.path.exists(temp_path) else 0
                    print(f"[TRACE] [TTS_SPEAK] [{response_id}] [gTTS] SYNTHESIS SUCCESS | provider={provider_used} | file_size={audio_file_size} bytes")
                except asyncio.CancelledError:
                    print(f"[TRACE] [TTS_SPEAK] [{response_id}] [gTTS] TASK CANCELLED")
                    raise
                except Exception as e:
                    print(f"[TRACE] [TTS_SPEAK] [{response_id}] [gTTS] FAILED: {e} | Falling back to Edge-TTS...")
                    if temp_path and os.path.exists(temp_path):
                        try:
                            os.remove(temp_path)
                        except Exception:
                            pass
                    temp_path = None

            # ─── PROVIDER 3: Edge-TTS (Tertiary Online Backup) ─────
            if provider_used is None:
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
                        temp_path = tmp.name

                    print(f"[TRACE] [TTS_SPEAK] [{response_id}] [Edge-TTS] ATTEMPTING SYNTHESIS | text='{normalized_text[:40]}...' | temp_path={temp_path}")
                    communicate = edge_tts.Communicate(text=normalized_text, voice=VOICE)
                    await asyncio.wait_for(communicate.save(temp_path), timeout=8.0)
                    provider_used = "Edge-TTS"
                    audio_file_size = os.path.getsize(temp_path) if os.path.exists(temp_path) else 0
                    print(f"[TRACE] [TTS_SPEAK] [{response_id}] [Edge-TTS] SYNTHESIS SUCCESS | provider={provider_used} | file_size={audio_file_size} bytes")
                except asyncio.CancelledError:
                    print(f"[TRACE] [TTS_SPEAK] [{response_id}] [Edge-TTS] TASK CANCELLED")
                    raise
                except Exception as e:
                    print(f"[TRACE] [TTS_SPEAK] [{response_id}] [Edge-TTS] FAILED: {e} | All TTS providers failed.")
                    if temp_path and os.path.exists(temp_path):
                        try:
                            os.remove(temp_path)
                        except Exception:
                            pass
                    return

            print(f"[TRACE] [TTS_SPEAK] [{response_id}] TTS GENERATION COMPLETE | provider={provider_used} | file_size={audio_file_size} bytes")

            from core.state_manager import AssistantState, get_state
            current_state = get_state()
            print(f"[TRACE] [TTS_SPEAK] [{response_id}] STATE CHECK | current_state={current_state} | expected=SPEAKING")
            if current_state != AssistantState.SPEAKING:
                print(f"[TRACE] [TTS_SPEAK] [{response_id}] ABORT: State is no longer SPEAKING (cancelled by user/state change)")
                return

            if web_mode:
                import base64
                from core.realtime_emit import emit_json
                import time
                import uuid
                
                loop = asyncio.get_running_loop()
                def _read_b64(path):
                    with open(path, "rb") as f:
                        return base64.b64encode(f.read()).decode("utf-8")
                print(f"[TRACE] [TTS_SPEAK] [{response_id}] READING AUDIO FILE FOR BASE64 ENCODING | temp_path={temp_path}")
                b64 = await loop.run_in_executor(None, _read_b64, temp_path)
                b64_size = len(b64)
                print(f"[TRACE] [TTS_SPEAK] [{response_id}] BASE64 ENCODE COMPLETE | b64_size={b64_size} chars")
                
                if get_state() == AssistantState.SPEAKING:
                    # Register response-specific event in the dictionary
                    playback_event = asyncio.Event()
                    _playback_events[response_id] = playback_event
                    
                    print(f"[TRACE] [TTS_SPEAK] [{response_id}] EMITTING AUDIO VIA WEBSOCKET | type=audio | b64_size={b64_size}")
                    await emit_json({"type": "audio", "audioBase64": b64, "responseId": response_id})
                    print(f"[TRACE] [TTS_SPEAK] [{response_id}] AUDIO EMITTED SUCCESSFULLY | Waiting for playback completion...")
                    
                    # Dynamic playback timeout: 0.15s per character + 15s buffer (min 20.0s, max 180.0s)
                    char_count = len(normalized_text)
                    audio_duration = max(20.0, min(180.0, char_count * 0.15 + 15.0))
                    global current_audio_duration
                    current_audio_duration = audio_duration
                    print(f"[TRACE] [TTS_SPEAK] [{response_id}] PLAYBACK TIMEOUT SET | duration={audio_duration}s | char_count={char_count}")
                    
                    try:
                        await asyncio.wait_for(playback_event.wait(), timeout=audio_duration)
                        print(f"[TRACE] [TTS_SPEAK] [{response_id}] PLAYBACK COMPLETION CONFIRMED FROM FRONTEND")
                    except asyncio.TimeoutError:
                        print(f"[TRACE] [TTS_SPEAK] [{response_id}] PLAYBACK COMPLETION TIMEOUT | timeout={audio_duration}s | FRONTEND MAY HAVE FAILED TO PLAY")
                    finally:
                        # Ensure cleanup of the specific response event
                        _playback_events.pop(response_id, None)
                else:
                    print(f"[TRACE] [TTS_SPEAK] [{response_id}] ABORT: State changed during base64 encoding | skipping emit")
            else:
                import sys
                if "api.server" in sys.modules:
                    print(f"[TRACE] [TTS_SPEAK] [{response_id}] Web server running but no UI connected | skipping local playback fallback to prevent audio driver deadlock")
                else:
                    loop = asyncio.get_running_loop()
                    print(f"[TRACE] [TTS_SPEAK] [{response_id}] DISPATCHING LOCAL PLAYBACK | temp_path={temp_path}")
                    await loop.run_in_executor(None, _sync_play, temp_path)
                    print(f"[TRACE] [TTS_SPEAK] [{response_id}] LOCAL PLAYBACK FINISHED")

        except asyncio.CancelledError:
            print(f"[TRACE] [TTS_SPEAK] [{response_id}] TASK CANCELLED")
            cancel_play()
            raise
        except Exception as e:
            print(f"[TRACE] [TTS_SPEAK] [{response_id}] EXCEPTION: {e}\n{traceback.format_exc()}")
        finally:
            if temp_path and os.path.exists(temp_path):
                for _ in range(6):
                    try:
                        os.remove(temp_path)
                        print(f"[TRACE] [TTS_SPEAK] [{response_id}] TEMP FILE CLEANED UP | temp_path={temp_path}")
                        break
                    except OSError:
                        time.sleep(0.1)
            print(f"[TRACE] [TTS_SPEAK] [{response_id}] SPEAK FUNCTION EXITING")