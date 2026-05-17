"""
voice/listen.py — Interruptible microphone listener.

Key design:
- _STOP_EVENT is set on shutdown or mic-off to unblock the blocking sr.listen() call.
- On shutdown, PyAudio is explicitly terminated so the OS releases the mic port
  (otherwise other apps hear mic bleed / exclusive-mode artifacts).
- energy_threshold and pause_threshold tuned to reject background noise / hallucinations.
"""
import asyncio
import threading
import speech_recognition as sr

# ── Shutdown / mic-off signal ─────────────────────────────────────────────────
_STOP_EVENT  = threading.Event()
_MIC_ENABLED = True
_MIC_LOCK    = threading.Lock()

# Global PyAudio instance — held so we can terminate() it on shutdown
# instead of leaving the OS audio port open.
_pa_instance = None
_pa_lock     = threading.Lock()


def _get_pyaudio():
    """Return a shared PyAudio instance, creating it if needed."""
    global _pa_instance
    with _pa_lock:
        if _pa_instance is None:
            import pyaudio
            _pa_instance = pyaudio.PyAudio()
        return _pa_instance


def _terminate_pyaudio():
    """Terminate PyAudio and release the OS audio port."""
    global _pa_instance
    with _pa_lock:
        if _pa_instance is not None:
            try:
                _pa_instance.terminate()
            except Exception:
                pass
            _pa_instance = None


def set_mic_enabled(enabled: bool) -> None:
    global _MIC_ENABLED
    with _MIC_LOCK:
        _MIC_ENABLED = enabled
    if not enabled:
        _STOP_EVENT.set()


def request_stop() -> None:
    """Call on shutdown to unblock the listener thread and release audio ports."""
    _STOP_EVENT.set()
    # Terminate PyAudio so the OS audio device is freed immediately.
    # This stops the 'mic-open' sound bleed into other apps.
    _terminate_pyaudio()


def reset_stop() -> None:
    global _MIC_ENABLED
    _STOP_EVENT.clear()
    with _MIC_LOCK:
        _MIC_ENABLED = True


# ── Async wrapper ─────────────────────────────────────────────────────────────

async def listen() -> str | None:
    with _MIC_LOCK:
        if not _MIC_ENABLED:
            return None
    if _STOP_EVENT.is_set():
        return None
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, sync_listen)


# ── Blocking listener (runs in thread pool) ───────────────────────────────────

def sync_listen() -> str | None:
    if _STOP_EVENT.is_set():
        return None
    with _MIC_LOCK:
        if not _MIC_ENABLED:
            return None

    try:
        recognizer = sr.Recognizer()

        # ── Anti-hallucination thresholds ─────────────────────────────────────
        recognizer.energy_threshold         = 400   # ignore background noise / TV
        recognizer.dynamic_energy_threshold = False  # don't drift downward over time
        recognizer.pause_threshold          = 0.9   # reject clicks / short pops
        recognizer.non_speaking_duration    = 0.4

        with sr.Microphone() as source:
            if _STOP_EVENT.is_set():
                return None

            print("[LISTENING...]")
            recognizer.adjust_for_ambient_noise(source, duration=0.15)

            try:
                audio = recognizer.listen(source, timeout=3, phrase_time_limit=6)
            except sr.WaitTimeoutError:
                return None

        if _STOP_EVENT.is_set():
            return None
        with _MIC_LOCK:
            if not _MIC_ENABLED:
                return None

        query = recognizer.recognize_google(audio).lower().strip()
        if query:
            print(f"Sir: {query}")
        return query or None

    except sr.WaitTimeoutError:
        return None
    except sr.UnknownValueError:
        return None
    except sr.RequestError as e:
        print(f"[SR API ERROR] {e}")
        return None
    except OSError as e:
        print(f"[MIC ERROR] {e}")
        _STOP_EVENT.wait(timeout=1.5)
        return None
    except Exception as e:
        print(f"[LISTEN ERROR] {e}")
        return None