"""
voice/listen.py — Robust and resilient interruptible microphone listener.

Key features:
- Persistent sr.Recognizer (not recreated per-call) so calibrated energy_threshold persists.
- Dynamic microphone device scanner with auto-fallback to first working input port.
- Deep audio quality tracing: RMS volume, audio duration, captured frames.
- WAV snippet saving for diagnostic inspection when speech is captured.
- Graceful PortAudio error recovery.
"""
import asyncio
import os
import struct
import threading
import time
import math
import wave

import speech_recognition as sr
from config.settings import LISTEN_TIMEOUT, PHRASE_TIME_LIMIT

# ── Conversational Realism & Adaptive Listening ─────────────────────────────────
USE_ADAPTIVE_LISTENING = True

# ── Diagnostic audio save directory ───────────────────────────────────────────
_AUDIO_DIAG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "audio_diags")
os.makedirs(_AUDIO_DIAG_DIR, exist_ok=True)
_DIAG_SAVE_ENABLED = True   # Set False to disable WAV saving after confirmed working
_DIAG_SAVE_COUNT = 0


def _save_audio_diag(audio: sr.AudioData, label: str) -> str:
    """Save captured audio as WAV for inspection. Returns path."""
    global _DIAG_SAVE_COUNT
    if not _DIAG_SAVE_ENABLED:
        return ""
    _DIAG_SAVE_COUNT += 1
    fname = f"capture_{_DIAG_SAVE_COUNT:04d}_{label}.wav"
    fpath = os.path.join(_AUDIO_DIAG_DIR, fname)
    try:
        wav_data = audio.get_wav_data()
        with open(fpath, "wb") as f:
            f.write(wav_data)
        return fpath
    except Exception as e:
        print(f"[TRACE] [MIC_DIAG] Failed to save WAV: {e}")
        return ""


def _compute_rms(audio: sr.AudioData) -> float:
    """Calculate RMS volume from raw audio frames (16-bit PCM)."""
    try:
        raw = audio.get_raw_data(convert_rate=16000, convert_width=2)
        count = len(raw) // 2
        if count == 0:
            return 0.0
        # Unpack as signed 16-bit ints
        samples = struct.unpack(f"<{count}h", raw)
        rms = math.sqrt(sum(s * s for s in samples) / count)
        return rms
    except Exception as e:
        print(f"[TRACE] [MIC_DIAG] RMS calculation failed: {e}")
        return 0.0


def _describe_rms(rms: float) -> str:
    """Human-readable volume level description."""
    if rms < 50:
        return "SILENT/DEAD (likely no audio)"
    elif rms < 300:
        return "very quiet (possible mic issue)"
    elif rms < 1000:
        return "quiet"
    elif rms < 5000:
        return "normal speech"
    elif rms < 15000:
        return "loud"
    else:
        return "very loud/clipping"


# ── ResilientMicrophone Subclass & Shared PyAudio singleton ───────────────────
class ResilientMicrophone(sr.Microphone):
    """
    Subclass of speech_recognition.Microphone that shares a single PyAudio instance
    across context entries/exits, preventing repeated terminate() calls that deadlock
    PortAudio on Windows.
    """
    _shared_pyaudio_instance = None
    _shared_pyaudio_lock = threading.Lock()

    @classmethod
    def get_shared_instance(cls):
        with cls._shared_pyaudio_lock:
            if cls._shared_pyaudio_instance is None:
                import pyaudio
                print("[TRACE] [MIC_INIT] Initializing resilient singleton PyAudio instance...")
                cls._shared_pyaudio_instance = pyaudio.PyAudio()
            return cls._shared_pyaudio_instance

    @classmethod
    def terminate_shared(cls):
        with cls._shared_pyaudio_lock:
            if cls._shared_pyaudio_instance is not None:
                print("[TRACE] [MIC_SHUTDOWN] Terminating resilient singleton PyAudio instance...")
                try:
                    cls._shared_pyaudio_instance.terminate()
                except Exception as e:
                    print(f"[TRACE] [MIC_SHUTDOWN_ERROR] Error terminating PyAudio: {e}")
                cls._shared_pyaudio_instance = None

    def __enter__(self):
        assert self.stream is None, "This audio source is already inside a context manager"
        self.pyaudio_instance = self.get_shared_instance()
        try:
            print(f"[TRACE] [MIC_OPEN] Opening input audio stream (device={self.device_index}, rate={self.SAMPLE_RATE})...")
            self.stream = self.pyaudio_instance.open(
                input_device_index=self.device_index,
                channels=1,
                format=self.format,
                rate=self.SAMPLE_RATE,
                frames_per_buffer=self.CHUNK,
                input=True,
            )
        except Exception as e:
            print(f"[TRACE] [MIC_ERROR] Failed to open audio stream: {e}")
            raise
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        print("[TRACE] [MIC_CLOSE] Closing audio stream...")
        try:
            if self.stream is not None:
                self.stream.close()
        except Exception as e:
            print(f"[TRACE] [MIC_CLOSE_ERROR] Error closing stream: {e}")
        finally:
            self.stream = None
            self.pyaudio_instance = None


# ── Shutdown / mic-off signal ─────────────────────────────────────────────────
_STOP_EVENT = threading.Event()
_MIC_ENABLED = False
_MIC_LOCK = threading.Lock()
_listen_execution_lock = threading.Lock() # Strict concurrency guard
_mic_open_lock = threading.Lock() # Guard against concurrent microphone stream initialization

def is_mic_enabled() -> bool:
    with _MIC_LOCK:
        return _MIC_ENABLED

# Microphone caching & resolution state
_microphone = None
_resolved_device_index = None
_resolved_device_name = "unknown"
_mic_init_lock = threading.Lock()

# ── PERSISTENT recognizer — survives across listen() calls ────────────────────
# CRITICAL FIX: Recreating sr.Recognizer() every call discards the calibrated
# energy_threshold from adjust_for_ambient_noise(). Use one instance globally.
_recognizer: sr.Recognizer | None = None
_ambient_calibrated = False


def _get_recognizer() -> sr.Recognizer:
    """Return (or create) the single persistent recognizer instance."""
    global _recognizer
    if _recognizer is None:
        _recognizer = sr.Recognizer()
        _recognizer.energy_threshold = 120
        # CRITICAL: Keep dynamic_energy_threshold ON only during calibration.
        # After calibration we pin it OFF to prevent session-to-session drift.
        # The adaptive pause engine handles per-utterance timing independently.
        _recognizer.dynamic_energy_threshold = True
        _recognizer.dynamic_energy_adjustment_damping = 0.15
        _recognizer.dynamic_energy_ratio = 1.5
        _recognizer.pause_threshold = 0.8
        _recognizer.non_speaking_duration = 0.4
        print(f"[TRACE] [MIC_RECOGNIZER] Persistent recognizer created. Initial energy_threshold={_recognizer.energy_threshold}")
    return _recognizer


def _list_all_microphones() -> None:
    """Enumerate and print ALL available audio input devices for diagnostics."""
    import pyaudio
    pa = ResilientMicrophone.get_shared_instance()
    count = pa.get_device_count()
    print(f"[MIC_ENUM] ===== Available Audio Devices ({count} total) =====")
    for i in range(count):
        try:
            info = pa.get_device_info_by_index(i)
            ch_in = info.get('maxInputChannels', 0)
            ch_out = info.get('maxOutputChannels', 0)
            rate = info.get('defaultSampleRate', 0)
            name = info.get('name', 'unknown')
            if ch_in > 0:
                # Test if we can actually open it
                try:
                    s = pa.open(format=pyaudio.paInt16, channels=1, rate=16000,
                                input=True, input_device_index=i,
                                frames_per_buffer=512)
                    s.close()
                    status = "OPENABLE"
                except Exception as ex:
                    status = f"FAILED({ex})"
                print(f"[MIC_ENUM]   [{i}] INPUT  ch={ch_in} rate={int(rate)}Hz  '{name}'  -> {status}")
            elif ch_out > 0:
                print(f"[MIC_ENUM]   [{i}] OUTPUT ch={ch_out} rate={int(rate)}Hz  '{name}'")
        except Exception as e:
            print(f"[MIC_ENUM]   [{i}] ERROR reading device: {e}")
    print(f"[MIC_ENUM] ==============================================")

    try:
        default_in = pa.get_default_input_device_info()
        print(f"[MIC_ENUM] Default input: [{default_in['index']}] '{default_in['name']}'")
    except Exception as e:
        print(f"[MIC_ENUM] No default input device: {e}")


def _is_device_active(pa, idx, rate=16000) -> bool:
    """Verify if a microphone index physically records any audio signal and isn't a dead virtual/cached device or static-heavy empty jack."""
    import pyaudio
    import audioop
    import time
    try:
        dev_name = pa.get_device_info_by_index(idx).get("name", "unknown")
        print(f"[E2E_TRACE] [STAGE 1: Microphone Capture] Testing device index {idx} ('{dev_name}') signal activity (non-blocking callback)...", flush=True)
        rms_list = []
        
        def callback(in_data, frame_count, time_info, status):
            if in_data:
                try:
                    rms = audioop.rms(in_data, 2)
                    rms_list.append(rms)
                except Exception:
                    pass
            return (None, pyaudio.paContinue)

        stream = pa.open(format=pyaudio.paInt16, channels=1, rate=rate,
                         input=True, input_device_index=idx,
                         frames_per_buffer=256,
                         stream_callback=callback)
        
        stream.start_stream()
        
        # Wait up to 1.6 seconds for chunks (16ms * 80 = 1.28s nominal)
        start_time = time.time()
        while len(rms_list) < 80 and (time.time() - start_time) < 1.6:
            time.sleep(0.02)
            
        try:
            stream.stop_stream()
        except Exception:
            pass
        try:
            stream.close()
        except Exception:
            pass
            
        if len(rms_list) >= 80:
            # Measure steady-state RMS of the last 30 chunks (chunks 50-79) to bypass initial warmup transients/silence
            steady_chunks = rms_list[50:80]
            steady_rms = sum(steady_chunks) / len(steady_chunks)
            print(f"[MIC_CHECK] Device [{idx}] signal test: steady_state_rms={steady_rms:.1f} | chunks={len(rms_list)}")
            is_active = 1.0 < steady_rms < 25000.0
            print(f"[E2E_TRACE] [STAGE 1: Microphone Capture] Device index {idx} checked. steady_rms={steady_rms:.1f} | is_active={is_active}", flush=True)
            return is_active
            
        # If we got some chunks but less than 80, still check them if we ran out of time
        if len(rms_list) > 10:
            steady_chunks = rms_list[min(50, len(rms_list)-1):]
            steady_rms = sum(steady_chunks) / len(steady_chunks)
            print(f"[MIC_CHECK] Device [{idx}] partial signal test: steady_state_rms={steady_rms:.1f} | chunks={len(rms_list)}")
            is_active = 1.0 < steady_rms < 25000.0
            print(f"[E2E_TRACE] [STAGE 1: Microphone Capture] Device index {idx} checked (partial). steady_rms={steady_rms:.1f} | is_active={is_active}", flush=True)
            return is_active
            
        print(f"[E2E_TRACE] [STAGE 1: Microphone Capture] Device index {idx} failed (insufficient RMS chunks: {len(rms_list)}).", flush=True)
        return False
    except Exception as e:
        print(f"[MIC_CHECK] Device [{idx}] failed to open: {e}")
        print(f"[E2E_TRACE] [STAGE 1: Microphone Capture] Device index {idx} failed to open: {e}", flush=True)
        return False


def _get_microphone():
    """Dynamically resolve and cache a working input microphone device."""
    global _microphone, _resolved_device_index, _resolved_device_name, _ambient_calibrated
    with _mic_init_lock:
        if _microphone is not None:
            return _microphone

        import pyaudio

        # Always enumerate all devices on first init so we have a full picture
        _list_all_microphones()

        print("[TRACE] [MIC_SCAN] Scanning for best working microphone...")
        pa = ResilientMicrophone.get_shared_instance()
        device_index = None
        device_name = "unknown"

        try:
            # 1. Test preferred device index from environment variable
            preferred_index = os.getenv("MICROPHONE_INDEX")
            if preferred_index is not None:
                try:
                    preferred_index = int(preferred_index)
                except ValueError:
                    preferred_index = None

            if preferred_index is not None:
                try:
                    info = pa.get_device_info_by_index(preferred_index)
                    if info.get('maxInputChannels', 0) > 0:
                        device_index = preferred_index
                        device_name = info.get('name', 'unknown')
                        print(f"[MIC] Using preferred index {device_index} directly: '{device_name}'")
                except Exception as e:
                    print(f"[TRACE] [MIC_SCAN] Preferred index {preferred_index} check failed: {e}")

            # 1.5. Test preferred device by name match from environment variable
            preferred_name = os.getenv("MICROPHONE_NAME")
            if device_index is None and preferred_name is not None:
                print(f"[TRACE] [MIC_SCAN] Searching for device matching name: '{preferred_name}'")
                for i in range(pa.get_device_count()):
                    try:
                        info = pa.get_device_info_by_index(i)
                        if info.get('maxInputChannels', 0) > 0:
                            dev_name = info.get('name', '')
                            if preferred_name.lower() in dev_name.lower():
                                if _is_device_active(pa, i):
                                    device_index = i
                                    device_name = dev_name
                                    print(f"[MIC] Found matching working device name '{device_name}' at index {device_index}")
                                    break
                                else:
                                    print(f"[TRACE] [MIC_SCAN] Name match '{dev_name}' index {i} is inactive/silent.")
                    except Exception:
                        continue

            # 2. Test default input device
            if device_index is None:
                try:
                    default_info = pa.get_default_input_device_info()
                    default_idx = default_info['index']
                    if _is_device_active(pa, default_idx):
                        device_index = default_idx
                        device_name = default_info.get('name', 'unknown')
                        print(f"[MIC] Using default index {device_index}: '{device_name}'")
                    else:
                        print(f"[TRACE] [MIC_SCAN] Default index {default_idx} is inactive/silent.")
                except Exception as e:
                    print(f"[TRACE] [MIC_SCAN] Default input device failed: {e}")

            # 3. Scan and auto-select first operational input device
            if device_index is None:
                for i in range(pa.get_device_count()):
                    try:
                        info = pa.get_device_info_by_index(i)
                        if info.get('maxInputChannels', 0) > 0:
                            if _is_device_active(pa, i):
                                device_index = i
                                device_name = info.get('name', 'unknown')
                                print(f"[MIC] Auto-detected working index {device_index}: '{device_name}'")
                                break
                    except Exception:
                        continue

            # 4. Critical fallback: if all devices were silent, select standard default
            if device_index is None:
                try:
                    default_info = pa.get_default_input_device_info()
                    device_index = default_info['index']
                    device_name = default_info.get('name', 'unknown')
                    print(f"[MIC WARNING] All microphones appeared silent. Selecting default device index {device_index}: '{device_name}'")
                except Exception:
                    # Select first openable device regardless of signal
                    for i in range(pa.get_device_count()):
                        try:
                            info = pa.get_device_info_by_index(i)
                            if info.get('maxInputChannels', 0) > 0:
                                stream = pa.open(format=pyaudio.paInt16, channels=1, rate=16000,
                                                 input=True, input_device_index=i)
                                stream.close()
                                device_index = i
                                device_name = info.get('name', 'unknown')
                                break
                        except Exception:
                            continue

        except Exception as e:
            print(f"[TRACE] [MIC_SCAN_ERROR] Scanning failed: {e}")

        if device_index is not None:
            _resolved_device_index = device_index
            _resolved_device_name = device_name
            _microphone = ResilientMicrophone(device_index=device_index, sample_rate=16000)
        else:
            print("[MIC WARNING] No confirmed working microphone. Falling back to system default.")
            _microphone = ResilientMicrophone(sample_rate=16000)
            _resolved_device_index = None
            _resolved_device_name = "system-default"

        # Reset calibration whenever device changes
        _ambient_calibrated = False
        print(f"[MIC] Selected device: index={_resolved_device_index} name='{_resolved_device_name}'")
        return _microphone


def _invalidate_microphone():
    """Clear cached microphone state on errors to force re-scanning on next try."""
    global _microphone, _resolved_device_index, _resolved_device_name, _ambient_calibrated, _recognizer
    with _mic_init_lock:
        print("[TRACE] [MIC_INVALIDATE] Clearing cached microphone reference and recognizer")
        if _microphone is not None:
            try:
                if _microphone.stream is not None:
                    print("[TRACE] [MIC_INVALIDATE] Closing active microphone stream...")
                    _microphone.stream.close()
            except Exception as e_close:
                print(f"[TRACE] [MIC_INVALIDATE_ERROR] Failed to close stream: {e_close}")
            finally:
                _microphone.stream = None
        _microphone = None
        _resolved_device_index = None
        _resolved_device_name = "unknown"
        _ambient_calibrated = False
        _recognizer = None  # Also reset recognizer so it re-calibrates on next device


def set_mic_enabled(enabled: bool) -> None:
    global _MIC_ENABLED, _microphone
    print(f"[TRACE] [MIC_CONTROL] set_mic_enabled({enabled}) called")
    with _MIC_LOCK:
        _MIC_ENABLED = enabled
    if not enabled:
        _STOP_EVENT.set()
        # Safely acquire _listen_execution_lock to ensure listen thread stops reading before stream close
        acquired = _listen_execution_lock.acquire(timeout=2.0)
        try:
            if _microphone is not None and _microphone.stream is not None:
                try:
                    print("[TRACE] [MIC_CONTROL] Closing active microphone stream to release port...")
                    _microphone.__exit__(None, None, None)
                except Exception as e_close:
                    print(f"[TRACE] [MIC_CLOSE_ERROR] Failed to close active stream: {e_close}")
        finally:
            if acquired:
                _listen_execution_lock.release()
        from core.state_manager import set_state, AssistantState, get_state
        if get_state() != AssistantState.SPEAKING:
            set_state(AssistantState.IDLE, force=True)
    else:
        from core.state_manager import set_state, AssistantState, get_state
        if get_state() != AssistantState.SPEAKING:
            set_state(AssistantState.LISTENING, force=True)


def request_stop() -> None:
    """Call on shutdown to unblock the listener thread and release audio ports."""
    global _microphone
    print("[TRACE] [MIC_CONTROL] request_stop() called — terminating PyAudio")
    _STOP_EVENT.set()
    acquired = _listen_execution_lock.acquire(timeout=2.0)
    try:
        if _microphone is not None and _microphone.stream is not None:
            try:
                print("[TRACE] [MIC_CLOSE] Closing persistent microphone stream context...")
                _microphone.__exit__(None, None, None)
            except Exception as e:
                print(f"[TRACE] [MIC_CLOSE_ERROR] Error closing stream during shutdown: {e}")
    finally:
        if acquired:
            _listen_execution_lock.release()
    ResilientMicrophone.terminate_shared()


def reset_stop() -> None:
    global _MIC_ENABLED
    print("[TRACE] [MIC_CONTROL] reset_stop() called")
    _STOP_EVENT.clear()
    with _MIC_LOCK:
        _MIC_ENABLED = True


def _force_calibration() -> None:
    """Run microphone calibration eagerly during startup, before TTS plays.
    This ensures ambient RMS is measured in true silence rather than during
    speaker playback of the startup greeting."""
    global _ambient_calibrated
    import audioop

    if _ambient_calibrated:
        print("[TRACE] [MIC_CAL] Already calibrated, skipping forced calibration.")
        return

    recognizer = _get_recognizer()
    try:
        mic = get_open_microphone()
        source = mic
    except Exception as e:
        print(f"[TRACE] [MIC_CAL] Failed to open mic for pre-calibration: {e}")
        return

    # Extended warmup: read and discard 64 chunks (~4s at 16kHz) to let the
    # audio driver fully settle. Cirrus Logic and similar USB/BT codecs produce
    # high transient RMS (1000-3000) during the first 2-3s after init.
    print("[TRACE] [MIC_CAL] Warming up microphone stream for ~4s...")
    try:
        for _ in range(64):
            source.stream.read(source.CHUNK, exception_on_overflow=False)
    except Exception as e:
        print(f"[TRACE] [MIC_CAL] Stream warmup trace: {e}")

    # Measure ambient RMS over 1.5s with extended sampling.
    # Use the 10th percentile (not median) to capture the TRUE noise floor.
    # Transient pops, driver glitches, and settling artifacts all produce
    # outlier-high RMS values that would inflate even the median.
    print("[TRACE] [MIC_CAL] Measuring ambient RMS (1.5s)...")
    rms_samples = []
    chunks_to_read = int(1.5 * source.SAMPLE_RATE / source.CHUNK)
    for _ in range(max(chunks_to_read, 24)):
        try:
            chunk = source.stream.read(source.CHUNK, exception_on_overflow=False)
            rms_samples.append(audioop.rms(chunk, source.SAMPLE_WIDTH))
        except Exception:
            break

    if rms_samples:
        rms_samples.sort()
        # 10th percentile: index at 10% of the sorted array
        p10_idx = max(0, len(rms_samples) // 10)
        ambient_rms = rms_samples[p10_idx]
        print(f"[TRACE] [MIC_CAL] RMS samples (sorted): min={rms_samples[0]:.0f} p10={ambient_rms:.0f} median={rms_samples[len(rms_samples)//2]:.0f} max={rms_samples[-1]:.0f} count={len(rms_samples)}")
    else:
        ambient_rms = 10.0

    # Threshold = 6x ambient gives strong SNR margin.
    # Floor at 80 ensures speech detection on very quiet mics.
    # Ceiling at 400 prevents extreme environments from locking out detection.
    floor_threshold = max(ambient_rms * 6.0, 80.0)
    floor_threshold = min(floor_threshold, 400.0)

    recognizer.energy_threshold = floor_threshold
    _ambient_calibrated = True
    recognizer.dynamic_energy_threshold = False

    print(f"[TRACE] [MIC_CAL] Pre-calibration COMPLETE. AmbientRMS={ambient_rms:.1f} -> Threshold={floor_threshold:.1f}")
    print(f"MIC_SELECTED:\nIndex={_resolved_device_index}\nName={_resolved_device_name}\nRMS={ambient_rms:.1f}\n")
    print(f"VAD_CALIBRATION:\nRawThreshold=N/A\nFinalThreshold={floor_threshold:.1f}\nAmbientRMS={ambient_rms:.1f}\n")


# ── Async wrapper ─────────────────────────────────────────────────────────────

async def listen() -> str | None:
    print("[TRACE] [MIC_ASYNC] listen() called")
    with _MIC_LOCK:
        if not _MIC_ENABLED:
            print("[TRACE] [MIC_ASYNC] Mic is muted/disabled, sleeping")
            await asyncio.sleep(0.3)
            return None
    if _STOP_EVENT.is_set():
        print("[TRACE] [MIC_ASYNC] Stop event is set, sleeping")
        await asyncio.sleep(0.3)
        return None
    loop = asyncio.get_running_loop()
    print("[TRACE] [MIC_ASYNC] Dispatching sync_listen() to thread pool executor...")
    query = await loop.run_in_executor(None, sync_listen)
    print(f"[TRACE] [MIC_ASYNC] listen() returned query: {query!r}")
    return query


# ── Blocking listener (runs in thread pool) ───────────────────────────────────

def get_open_microphone() -> ResilientMicrophone:
    """Obtain the microphone, ensuring the persistent stream is entered and active."""
    global _microphone
    with _mic_open_lock:
        mic = _get_microphone()
        if mic.stream is None:
            print("[TRACE] [MIC_OPEN] Opening persistent microphone stream context...")
            mic.__enter__()
        return mic


def _adaptive_listen(recognizer: sr.Recognizer, source: sr.AudioSource, timeout: float = None, phrase_time_limit: float = None, state: str = "CASUAL_CHAT", generation_id: int = 0) -> sr.AudioData | None:
    """
    Custom chunk-by-chunk listener that implements real-time adaptive pause thresholds
    based on conversational state, pacing, and hesitation patterns.
    """
    import math
    import collections
    import audioop

    seconds_per_buffer = float(source.CHUNK) / source.SAMPLE_RATE

    # ── Deterministic silence targets per conversational state ────────────────
    # These are FIXED. Dynamic threshold is frozen after calibration so these
    # values never drift between sessions or across turns.
    if state == "TASK_MODE":
        base_pause = 0.55           # Fast commands: cut quickly
        non_speaking_dur = 0.25
    elif state == "RETRIEVAL_MODE":
        base_pause = 0.65           # Questions: slight pause cushion
        non_speaking_dur = 0.30
    elif state == "EMOTIONAL_CONTEXT":
        base_pause = 1.40           # Emotional: generous, human-like
        non_speaking_dur = 0.65
    else:  # CASUAL_CHAT (default)
        base_pause = 0.90           # Conversational: natural pacing
        non_speaking_dur = 0.45

    # Minimum phrase duration — anything under 250ms is a noise pulse, not speech
    phrase_threshold = 0.25
    phrase_buffer_count = int(math.ceil(phrase_threshold / seconds_per_buffer))
    non_speaking_buffer_count = int(math.ceil(non_speaking_dur / seconds_per_buffer))

    elapsed_time = 0
    buffer = b""
    frames = collections.deque()

    # ── Mic-level streaming to frontend ──────────────────────────────────────
    # Every MIC_LEVEL_EMIT_INTERVAL chunks, send mic RMS to frontend via WS.
    # This gives the orb real-time amplitude data during LISTENING state,
    # even though PyAudio owns the hardware (browser cannot open getUserMedia).
    MIC_LEVEL_EMIT_INTERVAL = 4   # ~33ms at 8kHz chunk, ~20ms at 16kHz
    _mic_level_chunk_count = 0

    def _emit_mic_level(energy_value: float) -> None:
        """Fire-and-forget: send mic_level message to all connected WS clients."""
        try:
            # Normalize to 0.0–1.0 using the current threshold as reference.
            # Cap at 3x threshold for full-scale display.
            normalized = min(1.0, energy_value / max(recognizer.energy_threshold * 3.0, 1.0))
            from core.realtime_emit import emit_json_sync
            emit_json_sync({"type": "mic_level", "level": round(normalized, 3)})
        except Exception:
            pass  # Never let WS emission crash the audio capture loop

    # Phase 1: Wait for phrase to start
    print("[E2E_TRACE] [STAGE 2: Raw Audio Received] listen() started. Awaiting voice input...", flush=True)
    first_chunk_logged = False
    
    while True:
        if _STOP_EVENT.is_set():
            return None
        with _MIC_LOCK:
            if not _MIC_ENABLED:
                print("[TRACE] [MIC_ADAPTIVE] Mic disabled during Phase 1, aborting.")
                return None
        from core.runtime_orchestrator import orchestrator
        if generation_id != orchestrator.current_generation_id:
            print(f"[TRACE] [MIC_ADAPTIVE] Stale generation detected ({generation_id} vs {orchestrator.current_generation_id}) during Phase 1, aborting.")
            return None

        elapsed_time += seconds_per_buffer
        if timeout and elapsed_time > timeout:
            print("[E2E_TRACE] [STAGE 3: VAD Triggered] FAIL. WaitTimeoutError - no speech detected above threshold.", flush=True)
            raise sr.WaitTimeoutError("listening timed out while waiting for phrase to start")

        buffer = source.stream.read(source.CHUNK)
        if len(buffer) == 0:
            break
        
        energy = audioop.rms(buffer, source.SAMPLE_WIDTH)
        
        if not first_chunk_logged:
            first_chunk_logged = True
            print(f"[E2E_TRACE] [STAGE 2: Raw Audio Received] PASS. Read first audio chunk: {len(buffer)} bytes | initial RMS={energy:.1f}", flush=True)
            
        frames.append(buffer)
        if len(frames) > non_speaking_buffer_count:
            frames.popleft()

        # ── Emit mic level to frontend every N chunks ─────────────────────
        _mic_level_chunk_count += 1
        if _mic_level_chunk_count >= MIC_LEVEL_EMIT_INTERVAL:
            _mic_level_chunk_count = 0
            _emit_mic_level(energy)

        # Log ambient energy periodically to trace active levels
        if elapsed_time % 1.5 < seconds_per_buffer:
            print(f"[E2E_TRACE] [VAD_AWAITING] Ambient RMS={energy:.1f} | Threshold={recognizer.energy_threshold:.1f}", flush=True)

        # Adjust speaking threshold dynamically while silent
        if energy > recognizer.energy_threshold:
            print(f"[TRACE] [MIC_VAD] Speech detected! energy={energy:.1f} vs threshold={recognizer.energy_threshold:.1f} (accepted)")
            print(f"[E2E_TRACE] [STAGE 3: VAD Triggered] PASS. Speech detected! energy={energy:.1f} > threshold={recognizer.energy_threshold:.1f}", flush=True)
            break

        # NOTE: dynamic_energy_threshold is now FROZEN after calibration.
        # No threshold adjustment here — it would undo the calibration lock.
        # Log only significant deviations (>50% from threshold) for debugging.
        if abs(energy - recognizer.energy_threshold) / max(recognizer.energy_threshold, 1) > 0.5:
            if elapsed_time % 2.0 < seconds_per_buffer:
                print(f"[TRACE] [MIC_VAD] Ambient energy={energy:.1f} vs threshold={recognizer.energy_threshold:.1f}")

    # Phase 2: User has started speaking. Read until phrase ends, adjusting threshold dynamically!
    from core.state_manager import set_state, AssistantState
    set_state(AssistantState.LISTENING)
    
    pause_count = 0
    phrase_count = 0
    phrase_start_time = elapsed_time

    # Tracking vocal pacing and hesitations
    speech_segments = []
    current_speaking_streak = 0
    current_pause_streak = 0
    adaptive_pause_threshold = base_pause

    while True:
        if _STOP_EVENT.is_set():
            return None
        with _MIC_LOCK:
            if not _MIC_ENABLED:
                print("[TRACE] [MIC_ADAPTIVE] Mic disabled during Phase 2, aborting.")
                return None
        from core.runtime_orchestrator import orchestrator
        if generation_id != orchestrator.current_generation_id:
            print(f"[TRACE] [MIC_ADAPTIVE] Stale generation detected ({generation_id} vs {orchestrator.current_generation_id}) during Phase 2, aborting.")
            return None

        elapsed_time += seconds_per_buffer
        if phrase_time_limit and elapsed_time - phrase_start_time > phrase_time_limit:
            break

        buffer = source.stream.read(source.CHUNK)
        if len(buffer) == 0:
            break
        frames.append(buffer)
        phrase_count += 1

        energy = audioop.rms(buffer, source.SAMPLE_WIDTH)

        # ── Emit mic level to frontend every N chunks ─────────────────────
        _mic_level_chunk_count += 1
        if _mic_level_chunk_count >= MIC_LEVEL_EMIT_INTERVAL:
            _mic_level_chunk_count = 0
            _emit_mic_level(energy)

        # Determine if currently speaking or pausing
        if energy > recognizer.energy_threshold:
            if current_pause_streak > 0:
                # Recorded a silence gap
                pause_dur = current_pause_streak * seconds_per_buffer
                current_pause_streak = 0
            current_speaking_streak += 1
            pause_count = 0
        else:
            if current_speaking_streak > 0:
                # Recorded a vocal burst
                speech_dur = current_speaking_streak * seconds_per_buffer
                speech_segments.append(speech_dur)
                current_speaking_streak = 0
            current_pause_streak += 1
            pause_count += 1

        # ── DYNAMIC TURN-TAKING ENGINE ──
        # Computes turn-end threshold based on rhythm, conversational state, and pacing.
        tmp_threshold = base_pause
        
        # Calculate total spoken duration so far
        total_vocal_time = sum(speech_segments) + (current_speaking_streak * seconds_per_buffer)
        
        # Extract the first segment duration if finished OR currently in it
        first_segment_dur = 0.0
        if len(speech_segments) == 1:
            first_segment_dur = speech_segments[0]
        elif len(speech_segments) == 0:
            first_segment_dur = current_speaking_streak * seconds_per_buffer

        # 1. State-Aware Baselines & Continuous Speech Cushioning
        if state in ("CASUAL_CHAT", "EMOTIONAL_CONTEXT"):
            # Casual conversation & storytelling require generous pauses
            if total_vocal_time > 4.0 or len(speech_segments) >= 2:
                # User is storytelling, explaining, or speaking continuously.
                # Enforce human-like turn-taking: require a clear, confident silence gap.
                tmp_threshold = max(tmp_threshold, 1.8 if state == "EMOTIONAL_CONTEXT" else 1.4)
            elif total_vocal_time > 1.5:
                # Continuous talk cushion
                tmp_threshold = max(tmp_threshold, 1.4 if state == "EMOTIONAL_CONTEXT" else 1.1)
        
        # 2. Rule A: Single short vocalization at start (e.g. "friday...", "are...") -> Hesitation/Call
        if first_segment_dur > 0 and first_segment_dur < 0.8 and len(speech_segments) <= 1:
            # Pacing indicates potential hesitation or thought-gathering pause at the beginning.
            # Raise the pause threshold to allow them to collect thoughts and continue.
            tmp_threshold = max(tmp_threshold, 1.3)
            
        # 3. Rule B: Halting or conversational rhythm (multiple short segments with frequent thinking gaps)
        elif len(speech_segments) > 1:
            avg_speech = sum(speech_segments) / len(speech_segments)
            if avg_speech < 1.0:
                # Halting pacing detected, cushion threshold to prevent early interruption
                cushion = 0.5 if state in ("CASUAL_CHAT", "EMOTIONAL_CONTEXT") else 0.25
                tmp_threshold = max(tmp_threshold, base_pause + cushion)

        # 4. Rule C: Fast, fluent command (continuous speech, single segment, no previous gaps)
        if state in ("TASK_MODE", "RETRIEVAL_MODE", "CASUAL_CHAT") and first_segment_dur > 0.8 and len(speech_segments) <= 1:
            # Continuous speech running, likely a direct command.
            # Allow rapid cutoff once they stop.
            tmp_threshold = min(tmp_threshold, 0.4 if state in ("TASK_MODE", "RETRIEVAL_MODE") else 0.6)

        adaptive_pause_threshold = tmp_threshold
        pause_buffer_count = int(math.ceil(adaptive_pause_threshold / seconds_per_buffer))

        if pause_count > pause_buffer_count:
            break

    # Exclude trailing non-speaking frames
    phrase_count -= pause_count
    if phrase_count < phrase_buffer_count and len(buffer) > 0:
        # Phrase was too short to be speech, return None
        print(f"[TRACE] [MIC_VAD] Phrase duration too short ({phrase_count * seconds_per_buffer:.2f}s < {phrase_threshold}s), rejected as noise pulse.")
        print(f"[E2E_TRACE] [STAGE 3: VAD Triggered] FAIL. Rejected as noise pulse. Duration={phrase_count * seconds_per_buffer:.2f}s < threshold={phrase_threshold}s", flush=True)
        return None

    # Remove extra non-speaking frames at the end
    for _ in range(pause_count - non_speaking_buffer_count):
        if frames:
            frames.pop()

    frame_data = b"".join(frames)
    audio_duration_s = len(frame_data) / (source.SAMPLE_RATE * source.SAMPLE_WIDTH)
    print(f"[E2E_TRACE] [STAGE 3: VAD Triggered] PASS. Audio phrase captured! duration={audio_duration_s:.2f}s", flush=True)
    return sr.AudioData(frame_data, source.SAMPLE_RATE, source.SAMPLE_WIDTH)


def sync_listen() -> str | None:
    global _ambient_calibrated

    if not _listen_execution_lock.acquire(blocking=False):
        print("[TRACE] [MIC_SYNC] WARNING: Another listen thread is already active! Aborting concurrent execution to prevent PortAudio deadlock.")
        return None

    try:
        from core.runtime_orchestrator import orchestrator
        generation_id = orchestrator.current_generation_id

        print("[TRACE] [MIC_SYNC] sync_listen() thread entered")
        if _STOP_EVENT.is_set():
            print("[TRACE] [MIC_SYNC] Stop event is set, exiting sync_listen()")
            return None
        with _MIC_LOCK:
            if not _MIC_ENABLED:
                print("[TRACE] [MIC_SYNC] Mic is muted, exiting sync_listen()")
                return None

        recognizer = _get_recognizer()
        print(f"[TRACE] [MIC_SYNC] Recognizer energy_threshold={recognizer.energy_threshold:.1f}")

        print("[TRACE] [MIC_SYNC] Resolving microphone...")
        print("[E2E_TRACE] [STAGE 1: Microphone Capture] Resolving active microphone...", flush=True)
        try:
            mic = get_open_microphone()
            source = mic
            print(f"[TRACE] [MIC_SYNC] Persistent microphone resolved: index={_resolved_device_index} name='{_resolved_device_name}'")
            print(f"[E2E_TRACE] [STAGE 1: Microphone Capture] PASS. Active mic resolved: index={_resolved_device_index} name='{_resolved_device_name}'", flush=True)
        except Exception as e_open:
            print(f"[TRACE] [MIC_SYNC_ERROR] Failed to obtain open microphone: {e_open}. Invalidating and retrying.")
            print(f"[E2E_TRACE] [STAGE 1: Microphone Capture] FAIL. Failed to resolve mic: {e_open}", flush=True)
            _invalidate_microphone()
            return None

        # Calibrate ambient noise exactly ONCE per device to establish baseline.
        # Because recognizer is now persistent, the calibrated threshold is retained.
        if not _ambient_calibrated:
            print("[TRACE] [MIC_SYNC] Warming up microphone stream for ~4s to bypass driver startup delay...")
            try:
                # Read and discard 64 chunks (~4s at 16kHz) to let the audio driver fully settle
                for _ in range(64):
                    if _STOP_EVENT.is_set():
                        break
                    _ = source.stream.read(source.CHUNK, exception_on_overflow=False)
            except Exception as e_warm:
                print(f"[TRACE] [MIC_SYNC_WARNING] Stream warmup trace: {e_warm}")

            print("[TRACE] [MIC_SYNC] Running one-time ambient noise calibration (1.5s)...")
            print("[E2E_TRACE] [STAGE 1: Microphone Capture] Running ambient noise calibration...", flush=True)
            try:
                import audioop

                # Measure ambient RMS over 1.5s. Use 10th percentile to ignore
                # driver transients that inflate readings during early init.
                rms_samples = []
                chunks_to_read = int(1.5 * source.SAMPLE_RATE / source.CHUNK)
                for _ in range(max(chunks_to_read, 24)):
                    try:
                        chunk = source.stream.read(source.CHUNK, exception_on_overflow=False)
                        rms_samples.append(audioop.rms(chunk, source.SAMPLE_WIDTH))
                    except Exception:
                        break

                if rms_samples:
                    rms_samples.sort()
                    p10_idx = max(0, len(rms_samples) // 10)
                    ambient_rms = rms_samples[p10_idx]
                    print(f"[TRACE] [MIC_SYNC] RMS samples: min={rms_samples[0]:.0f} p10={ambient_rms:.0f} median={rms_samples[len(rms_samples)//2]:.0f} max={rms_samples[-1]:.0f} count={len(rms_samples)}")
                else:
                    ambient_rms = 10.0

                selected_rms = ambient_rms

                floor_threshold = max(ambient_rms * 6.0, 80.0)
                floor_threshold = min(floor_threshold, 400.0)

                raw_threshold = recognizer.energy_threshold
                recognizer.energy_threshold = floor_threshold
                _ambient_calibrated = True
                recognizer.dynamic_energy_threshold = False

                print(f"MIC_SELECTED:\nIndex={_resolved_device_index}\nName={_resolved_device_name}\nRMS={selected_rms:.1f}\n")
                print(f"VAD_CALIBRATION:\nRawThreshold={raw_threshold:.1f}\nFinalThreshold={floor_threshold:.1f}\nAmbientRMS={ambient_rms:.1f}\n")
                print(f"[E2E_TRACE] [STAGE 1: Microphone Capture] Calibration completed. AmbientRMS={ambient_rms:.1f} -> EnforcedThreshold={floor_threshold:.1f} | dynamic_energy_threshold=False (frozen)", flush=True)

                print(f"[TRACE] [MIC_SYNC] Calibration done + threshold FROZEN. "
                      f"ambient_rms={ambient_rms:.1f} -> enforced_threshold={recognizer.energy_threshold:.1f} "
                      f"| dynamic_energy_threshold=False (locked)")
            except Exception as e_cal:
                print(f"[TRACE] [MIC_SYNC_ERROR] Ambient noise calibration failed: {e_cal}. Re-calibrating next turn.")
                print(f"[E2E_TRACE] [STAGE 1: Microphone Capture] FAIL. Ambient noise calibration failed: {e_cal}", flush=True)
                return None

        # Get active conversational state
        state = "CASUAL_CHAT"
        try:
            from core.state_manager import get_conversational_state
            state = get_conversational_state()
        except Exception as e_state:
            print(f"[MIC_DYNAMIC_ERROR] Failed to get conversational state: {e_state}")

        # State remains AssistantState.LISTENING (deleted set_state(AssistantState.SOFT_IDLE) call)

        print(f"[TRACE] [MIC_SYNC] Listening... (timeout={LISTEN_TIMEOUT}s, phrase_limit={PHRASE_TIME_LIMIT}s, threshold={recognizer.energy_threshold:.1f}, state={state})")
        t_start = time.monotonic()
        try:
            if USE_ADAPTIVE_LISTENING:
                audio = _adaptive_listen(
                    recognizer,
                    source,
                    timeout=LISTEN_TIMEOUT,
                    phrase_time_limit=PHRASE_TIME_LIMIT,
                    state=state,
                    generation_id=generation_id
                )
            else:
                audio = recognizer.listen(
                    source,
                    timeout=LISTEN_TIMEOUT,
                    phrase_time_limit=PHRASE_TIME_LIMIT
                )

            if audio is None:
                # Handled internal cutoff or blank capture
                return None

            t_captured = time.monotonic() - t_start
            print(f"[TRACE] [MIC_SYNC] Audio phrase captured! duration={t_captured:.2f}s")
        except sr.WaitTimeoutError:
            print(f"[TRACE] [MIC_SYNC] recognizer.listen timeout ({LISTEN_TIMEOUT}s) — no speech detected above threshold={recognizer.energy_threshold:.1f} (rejected)")
            return None

        # ── Audio quality diagnostics ──────────────────────────────────────────
        raw_len = len(audio.get_raw_data())
        # Calculate approximate duration from raw byte length (16-bit, mono, 16kHz)
        audio_duration_s = raw_len / (16000 * 2)
        rms = _compute_rms(audio)
        rms_desc = _describe_rms(rms)

        print(f"[TRACE] [MIC_QUALITY] raw_bytes={raw_len} | duration={audio_duration_s:.2f}s | RMS={rms:.1f} ({rms_desc})")

        # Save WAV snippet for inspection (first 20 captures)
        if _DIAG_SAVE_COUNT < 20:
            if rms < 50:
                label = "SILENT"
            elif rms < 300:
                label = "quiet"
            else:
                label = "speech"
            wav_path = _save_audio_diag(audio, label)
            if wav_path:
                print(f"[TRACE] [MIC_DIAG] Saved captured audio to: {wav_path}")

        # Warn explicitly if audio is suspiciously silent
        if rms < 100:
            print(f"[TRACE] [MIC_QUALITY] WARNING: RMS={rms:.1f} is near-silent. "
                  f"Possible causes: wrong mic device, mic muted in Windows, or hardware issue. "
                  f"Current device: index={_resolved_device_index} '{_resolved_device_name}'")

        if _STOP_EVENT.is_set():
            print("[TRACE] [MIC_SYNC] Stop event set post-listening, exiting")
            return None
        with _MIC_LOCK:
            if not _MIC_ENABLED:
                print("[TRACE] [MIC_SYNC] Mic disabled post-listening, exiting")
                return None

        print("[TRACE] [MIC_SYNC] Sending audio to Google Speech Recognition...")
        print(f"[E2E_TRACE] [STAGE 4: Speech Recognition Executed] Sending {audio_duration_s:.2f}s of captured audio (RMS={rms:.1f}) to Google Speech Recognition...", flush=True)
        try:
            query = recognizer.recognize_google(audio, language="en-IN").lower().strip()
            print(f"[TRACE] [MIC_SYNC] ✓ TRANSCRIPT: '{query}' (speech accepted)")
            print(f"[E2E_TRACE] [STAGE 5: Transcript Generated] PASS. Transcript: '{query}'", flush=True)
            if query:
                print(f"Sir: {query}")
            return query or None
        except sr.UnknownValueError:
            print(f"[TRACE] [MIC_SYNC] Google could not understand audio "
                  f"(RMS={rms:.1f}, duration={audio_duration_s:.2f}s, "
                  f"threshold={recognizer.energy_threshold:.1f}, speech rejected)")
            print(f"[E2E_TRACE] [STAGE 5: Transcript Generated] FAIL (UnknownValueError). Google SR did not understand the audio (likely empty or background noise).", flush=True)
            return None
        except sr.RequestError as e:
            print(f"[TRACE] [MIC_SYNC] [SR API ERROR] Google SR request failed: {e} (rejected)")
            print(f"[E2E_TRACE] [STAGE 5: Transcript Generated] FAIL (RequestError). Google SR request failed: {e}", flush=True)
            return None

    except sr.WaitTimeoutError:
        print("[TRACE] [MIC_SYNC] WaitTimeoutError (outer block)")
        return None
    except (OSError, Exception) as e:
        print(f"[TRACE] [MIC_SYNC] [MIC ERROR] Audio stream disrupted: {type(e).__name__}: {e}. Invalidating mic.")
        _invalidate_microphone()
        _STOP_EVENT.wait(timeout=1.0)
        return None
    finally:
        _listen_execution_lock.release()