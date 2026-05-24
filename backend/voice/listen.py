"""
voice/listen.py — Robust and resilient interruptible microphone listener.

Key features:
- Dynamic microphone device scanner with auto-fallback to first working input port.
- One-time ambient noise calibration to prevent temporary room noises from muting the user.
- Graceful PortAudio error recovery: invalidates cache on error to recover dynamically.
- Native integration of settings config for timeouts and limits.
"""
import asyncio
import os
import threading
import speech_recognition as sr
from config.settings import LISTEN_TIMEOUT, PHRASE_TIME_LIMIT

# ── Shutdown / mic-off signal ─────────────────────────────────────────────────
_STOP_EVENT = threading.Event()
_MIC_ENABLED = True
_MIC_LOCK = threading.Lock()

# Global PyAudio instance — held so we can terminate() it on shutdown
_pa_instance = None
_pa_lock = threading.Lock()

# Microphone caching & resolution state
_microphone = None
_resolved_device_index = None
_ambient_calibrated = False
_mic_init_lock = threading.Lock()


def _get_microphone():
    """Dynamically resolve and cache a working input microphone device."""
    global _microphone, _resolved_device_index, _ambient_calibrated
    with _mic_init_lock:
        if _microphone is not None:
            return _microphone

        import pyaudio

        # Look for configured micro-index in environment
        preferred_index = os.getenv("MICROPHONE_INDEX")
        if preferred_index is not None:
            try:
                preferred_index = int(preferred_index)
            except ValueError:
                preferred_index = None

        pa = pyaudio.PyAudio()
        device_index = None

        try:
            # 1. Test preferred device index first
            if preferred_index is not None:
                try:
                    info = pa.get_device_info_by_index(preferred_index)
                    if info.get('maxInputChannels', 0) > 0:
                        # Try to open briefly to ensure it isn't locked/busy
                        stream = pa.open(
                            format=pyaudio.paInt16,
                            channels=1,
                            rate=16000,
                            input=True,
                            input_device_index=preferred_index
                        )
                        stream.close()
                        device_index = preferred_index
                        print(f"[MIC] Using preferred index {device_index}: {info.get('name')}")
                except Exception:
                    pass

            # 2. Test default input device
            if device_index is None:
                try:
                    default_info = pa.get_default_input_device_info()
                    default_idx = default_info['index']
                    stream = pa.open(
                        format=pyaudio.paInt16,
                        channels=1,
                        rate=16000,
                        input=True,
                        input_device_index=default_idx
                    )
                    stream.close()
                    device_index = default_idx
                    print(f"[MIC] Using default index {device_index}: {default_info.get('name')}")
                except Exception:
                    pass

            # 3. Scan and auto-select first operational input device
            if device_index is None:
                for i in range(pa.get_device_count()):
                    try:
                        info = pa.get_device_info_by_index(i)
                        if info.get('maxInputChannels', 0) > 0:
                            stream = pa.open(
                                format=pyaudio.paInt16,
                                channels=1,
                                rate=16000,
                                input=True,
                                input_device_index=i
                            )
                            stream.close()
                            device_index = i
                            print(f"[MIC] Auto-detected working index {device_index}: {info.get('name')}")
                            break
                    except Exception:
                        continue
        finally:
            pa.terminate()

        # Instantiate microphone source
        if device_index is not None:
            _resolved_device_index = device_index
            _microphone = sr.Microphone(device_index=device_index)
        else:
            print("[MIC WARNING] No confirmed working microphone. Falling back to default system mic.")
            _microphone = sr.Microphone()
            _resolved_device_index = None

        # Reset ambient calibration for the new device
        _ambient_calibrated = False
        return _microphone


def _invalidate_microphone():
    """Clear cached microphone state on errors to force re-scanning on next try."""
    global _microphone, _resolved_device_index, _ambient_calibrated
    with _mic_init_lock:
        _microphone = None
        _resolved_device_index = None
        _ambient_calibrated = False


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
            await asyncio.sleep(0.3)
            return None
    if _STOP_EVENT.is_set():
        await asyncio.sleep(0.3)
        return None
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, sync_listen)


# ── Blocking listener (runs in thread pool) ───────────────────────────────────

def sync_listen() -> str | None:
    global _ambient_calibrated
    if _STOP_EVENT.is_set():
        return None
    with _MIC_LOCK:
        if not _MIC_ENABLED:
            return None

    try:
        recognizer = sr.Recognizer()

        # ── Sensitivity and Threshold tuning ──────────────────────────────────
        recognizer.energy_threshold = 300
        recognizer.dynamic_energy_threshold = True
        recognizer.dynamic_energy_adjustment_damping = 0.15
        recognizer.dynamic_energy_ratio = 1.5
        recognizer.pause_threshold = 0.8
        recognizer.non_speaking_duration = 0.4

        with _get_microphone() as source:
            if _STOP_EVENT.is_set():
                return None

            # Calibrate ambient noise exactly ONCE to establish baseline threshold
            if not _ambient_calibrated:
                print("[MIC] Running one-time ambient noise calibration (0.6s)...")
                recognizer.adjust_for_ambient_noise(source, duration=0.6)
                _ambient_calibrated = True
                print(f"[MIC] Calibration done. Baseline threshold: {recognizer.energy_threshold}")

            print("[LISTENING...]")
            try:
                audio = recognizer.listen(
                    source,
                    timeout=LISTEN_TIMEOUT,
                    phrase_time_limit=PHRASE_TIME_LIMIT
                )
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
    except (OSError, Exception) as e:
        print(f"[MIC ERROR] Audio stream disrupted: {e}. Invalidating mic index.")
        _invalidate_microphone()
        _STOP_EVENT.wait(timeout=1.0)
        return None