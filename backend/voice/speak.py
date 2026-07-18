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

def init_tts_singleton() -> None:
    """Bypasses persistent singleton setup; SAPI5 operates on-demand per fallback turn."""
    print("[TTS pyttsx3 SAPI5] Singleton warm-up bypassed: SAPI5 operates on-demand.")

def _run_sapi_tts(text: str, path: str) -> None:
    """Uses a thread-isolated, fresh pyttsx3 engine for stable offline synthesis."""
    import pythoncom
    import pyttsx3
    
    print(f"[TTS pyttsx3 SAPI5] Thread-isolated worker: calling CoInitialize...")
    pythoncom.CoInitialize()
    try:
        print("[TTS pyttsx3 SAPI5] Thread-isolated worker: initializing pyttsx3 engine...")
        engine = pyttsx3.init()
        voices = engine.getProperty('voices')
        selected_voice = None
        # Authoritative local persona fallback (Hazel/Zira/Heera)
        for voice in voices:
            name_lower = voice.name.lower()
            if "heera" in name_lower or "zira" in name_lower or "hazel" in name_lower or "female" in name_lower:
                selected_voice = voice.id
                break
        if not selected_voice:
            for voice in voices:
                if "david" not in voice.name.lower() and "male" not in voice.name.lower():
                    selected_voice = voice.id
                    break
        if selected_voice:
            engine.setProperty('voice', selected_voice)
            print(f"[TTS pyttsx3 SAPI5] Thread-isolated worker selected SAPI5 voice: {selected_voice}")
        
        rate = engine.getProperty('rate')
        engine.setProperty('rate', int(rate * 1.15))
        
        print(f"[TTS pyttsx3 SAPI5] Thread-isolated worker: saving synthesis to path: {path}")
        engine.save_to_file(text, path)
        engine.runAndWait()
        print("[TTS pyttsx3 SAPI5] Thread-isolated worker: synthesis success!")
        del engine
    except Exception as e:
        print(f"[TTS pyttsx3 SAPI5 WORKER ERROR] {e}")
        raise e
    finally:
        print("[TTS pyttsx3 SAPI5] Thread-isolated worker: calling CoUninitialize...")
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
    
    # Clear any stale playback cancellation flag
    _play_cancelled.clear()
    
    # Determine language and select voice
    try:
        from friday.core.fsm import cognitive_core
        lang = cognitive_core.fsm.session_language or cognitive_core.fsm.working_memory.get("detected_language", "en")
    except Exception:
        print("[TTS_SPEAK] Could not read session_language or detected_language, defaulting to English voice")
        lang = "en"
        
    if lang == "hi":
        VOICE = "hi-IN-MadhurNeural"
    else:
        VOICE = "en-IN-NeerjaNeural"
        
    print(f"[TTS_SPEAK] Selected voice '{VOICE}' because detected language is '{lang}'")
    
    print(f"[E2E_TRACE] [STAGE 10: TTS Generated] Synthesis started for text: '{text[:60]}...' | web_mode={web_mode} | response_id={response_id}", flush=True)
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
            # ─── PROVIDER 1: Edge-TTS (Primary Neural - Authoritative Voice Identity) ────
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
                    temp_path = tmp.name

                # Edge-TTS retry logic: up to 2 attempts total (1 retry)
                max_attempts = 2
                edge_tts_error = None
                for attempt in range(1, max_attempts + 1):
                    try:
                        print(f"[TRACE] [TTS_SPEAK] [{response_id}] [Edge-TTS] ATTEMPT {attempt}/{max_attempts} | voice={VOICE} | text='{normalized_text[:40]}...' | temp_path={temp_path}")
                        communicate = edge_tts.Communicate(text=normalized_text, voice=VOICE)
                        # We use 8.0s timeout per attempt, except for very long texts where we give more time
                        timeout_limit = max(8.0, len(normalized_text) * 0.05)
                        await asyncio.wait_for(communicate.save(temp_path), timeout=timeout_limit)
                        provider_used = "Edge-TTS"
                        break
                    except Exception as e_attempt:
                        edge_tts_error = e_attempt
                        print(f"[TRACE] [TTS_SPEAK] [{response_id}] [Edge-TTS] ATTEMPT {attempt} FAILED: {e_attempt}")
                        if attempt < max_attempts:
                            await asyncio.sleep(0.5) # Quick pause before retry

                if provider_used is None:
                    raise edge_tts_error if edge_tts_error else Exception("Edge-TTS failed all attempts")

                audio_file_size = os.path.getsize(temp_path) if os.path.exists(temp_path) else 0
                print(f"[TRACE] [TTS_SPEAK] [{response_id}] [Edge-TTS] SYNTHESIS SUCCESS | provider={provider_used} | file_size={audio_file_size} bytes")
                print(f"[E2E_TRACE] [STAGE 10: TTS Generated] PASS. Edge-TTS synthesized speech successfully. File size: {audio_file_size} bytes. Path: {temp_path}", flush=True)
            except asyncio.CancelledError:
                print(f"[TRACE] [TTS_SPEAK] [{response_id}] [Edge-TTS] TASK CANCELLED")
                raise
            except Exception as e:
                # Log provider switch to gTTS in console
                print(f"[TRACE] [TTS_SPEAK] [{response_id}] [Edge-TTS] FAILED: {e} | Falling back to gTTS...")
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
                    timeout_limit = max(6.0, len(normalized_text) * 0.05)
                    await asyncio.wait_for(
                        loop.run_in_executor(None, tts_obj.save, temp_path),
                        timeout=timeout_limit
                    )
                    provider_used = "gTTS"
                    audio_file_size = os.path.getsize(temp_path) if os.path.exists(temp_path) else 0
                    print(f"[TRACE] [TTS_SPEAK] [{response_id}] [gTTS] SYNTHESIS SUCCESS | provider={provider_used} | file_size={audio_file_size} bytes")
                    print(f"[E2E_TRACE] [STAGE 10: TTS Generated] PASS. gTTS fallback synthesized speech successfully. File size: {audio_file_size} bytes. Path: {temp_path}", flush=True)
                except asyncio.CancelledError:
                    print(f"[TRACE] [TTS_SPEAK] [{response_id}] [gTTS] TASK CANCELLED")
                    raise
                except Exception as e:
                    # Log provider switch to pyttsx3 in console
                    print(f"[TRACE] [TTS_SPEAK] [{response_id}] [gTTS] FAILED: {e} | Falling back to pyttsx3...")
                    if temp_path and os.path.exists(temp_path):
                        try:
                            os.remove(temp_path)
                        except Exception:
                            pass
                    temp_path = None

            # ─── PROVIDER 3: pyttsx3 (Tertiary Offline Fallback) ─────
            if provider_used is None:
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
                        temp_path = tmp.name

                    print(f"[TRACE] [TTS_SPEAK] [{response_id}] [pyttsx3] ATTEMPTING SYNTHESIS | text='{normalized_text[:40]}...' | temp_path={temp_path}")
                    loop = asyncio.get_running_loop()
                    # Increase SAPI5 synthesis timeout dynamically for long texts to prevent premature cuts
                    timeout_limit = max(15.0, len(normalized_text) * 0.1)
                    await asyncio.wait_for(
                        loop.run_in_executor(None, _run_sapi_tts, normalized_text, temp_path),
                        timeout=timeout_limit
                    )
                    provider_used = "pyttsx3"
                    audio_file_size = os.path.getsize(temp_path) if os.path.exists(temp_path) else 0
                    print(f"[TRACE] [TTS_SPEAK] [{response_id}] [pyttsx3] SYNTHESIS SUCCESS | provider={provider_used} | file_size={audio_file_size} bytes")
                    print(f"[E2E_TRACE] [STAGE 10: TTS Generated] PASS. pyttsx3 (SAPI5) fallback synthesized speech successfully. File size: {audio_file_size} bytes. Path: {temp_path}", flush=True)
                except asyncio.CancelledError:
                    print(f"[TRACE] [TTS_SPEAK] [{response_id}] [pyttsx3] TASK CANCELLED")
                    raise
                except Exception as e:
                    print(f"[TRACE] [TTS_SPEAK] [{response_id}] [pyttsx3] FAILED: {e} | All TTS providers failed.")
                    if temp_path and os.path.exists(temp_path):
                        try:
                            os.remove(temp_path)
                        except Exception:
                            pass
                    raise RuntimeError("All TTS providers failed to synthesize speech.") from e

            print(f"[TRACE] [TTS_SPEAK] [{response_id}] TTS GENERATION COMPLETE | provider={provider_used} | file_size={audio_file_size} bytes")
            # NOTE: Intentional cancellations are handled by _play_cancelled (set by cancel_play())
            # and the pipeline-level _speak_cancelled flag. Do NOT check state here — the state
            # can legitimately drift to LISTENING during the synthesis window (Bluetooth A2DP
            # handoff delay + Edge-TTS retry overhead) causing valid audio to be silently dropped.

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
                
                # Audio is synthesized and encoded — emit it unconditionally.
                # The state may have drifted to LISTENING during synthesis (Edge-TTS
                # retry + gTTS fallback takes 2-4s). Real cancellations are handled
                # by _play_cancelled flag, not state checks.
                
                # Register response-specific event in the dictionary
                playback_event = asyncio.Event()
                _playback_events[response_id] = playback_event
                
                print(f"[TRACE] [TTS_SPEAK] [{response_id}] EMITTING AUDIO VIA WEBSOCKET | type=audio | b64_size={b64_size}")
                print(f"[E2E_TRACE] [STAGE 11: Audio Sent To Frontend] Sending audio base64 payload to WebSocket (b64_size={b64_size} chars)...", flush=True)
                await emit_json({"type": "audio", "audioBase64": b64, "responseId": response_id})
                print(f"[TRACE] [TTS_SPEAK] [{response_id}] AUDIO EMITTED SUCCESSFULLY | Waiting for playback completion...")
                print(f"[E2E_TRACE] [STAGE 11: Audio Sent To Frontend] PASS. Audio payload emitted successfully. Response ID: {response_id}", flush=True)
                    
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
                loop = asyncio.get_running_loop()
                print(f"[TRACE] [TTS_SPEAK] [{response_id}] DISPATCHING LOCAL PLAYBACK | temp_path={temp_path}")
                print(f"[E2E_TRACE] [STAGE 11: Audio Sent To Frontend] LOCAL PLAYBACK MODE. Dispatching local playback. Path: {temp_path}", flush=True)
                await loop.run_in_executor(None, _sync_play, temp_path)
                print(f"[TRACE] [TTS_SPEAK] [{response_id}] LOCAL PLAYBACK FINISHED")

        except asyncio.CancelledError:
            print(f"[TRACE] [TTS_SPEAK] [{response_id}] TASK CANCELLED")
            cancel_play()
            raise
        except Exception as e:
            print(f"[TRACE] [TTS_SPEAK] [{response_id}] EXCEPTION: {e}\n{traceback.format_exc()}")
            raise
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