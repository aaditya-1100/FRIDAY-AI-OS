"""
mic_diagnostic.py — Standalone microphone and speech recognition diagnostic tool.
Run this from the backend directory with the venv active:
  ..\\.venv\\Scripts\\python.exe mic_diagnostic.py

Tests EVERY available input device:
- Opens stream and reads raw audio
- Calculates RMS volume
- Saves a 3-second WAV clip
- Tests speech recognition on that clip
"""
import math
import os
import struct
import sys
import time
import wave

try:
    import pyaudio
    import speech_recognition as sr
except ImportError as e:
    print(f"[ERROR] Missing dependency: {e}")
    print("Run: pip install pyaudio speechrecognition")
    sys.exit(1)

DIAG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "audio_diags")
os.makedirs(DIAG_DIR, exist_ok=True)

SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK = 1024
FORMAT = pyaudio.paInt16
RECORD_SECONDS = 3


def compute_rms(frames: bytes) -> float:
    count = len(frames) // 2
    if count == 0:
        return 0.0
    samples = struct.unpack(f"<{count}h", frames)
    return math.sqrt(sum(s * s for s in samples) / count)


def describe_rms(rms: float) -> str:
    if rms < 50:    return "SILENT/DEAD"
    if rms < 300:   return "very quiet"
    if rms < 1000:  return "quiet"
    if rms < 5000:  return "normal speech"
    if rms < 15000: return "loud"
    return "very loud/clipping"


def save_wav(frames: bytes, path: str) -> None:
    with wave.open(path, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(frames)


def test_google_sr(wav_path: str) -> str:
    """Try to transcribe a saved WAV with Google Speech Recognition."""
    r = sr.Recognizer()
    try:
        with sr.AudioFile(wav_path) as source:
            audio = r.record(source)
        result = r.recognize_google(audio)
        return f"✓ TRANSCRIPT: '{result}'"
    except sr.UnknownValueError:
        return "✗ Google could not understand (silence or unclear speech)"
    except sr.RequestError as e:
        return f"✗ SR API error: {e}"
    except Exception as e:
        return f"✗ Exception: {e}"


def main():
    try:
        import sys
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    pa = pyaudio.PyAudio()
    device_count = pa.get_device_count()

    print("\n" + "=" * 70)
    print("   FRIDAY MIC DIAGNOSTIC TOOL")
    print("=" * 70)
    print(f"Found {device_count} audio devices total.\n")

    # List all devices
    input_devices = []
    for i in range(device_count):
        try:
            info = pa.get_device_info_by_index(i)
            ch_in = info.get('maxInputChannels', 0)
            ch_out = info.get('maxOutputChannels', 0)
            rate = info.get('defaultSampleRate', 0)
            name = info.get('name', 'unknown')
            tag = "INPUT " if ch_in > 0 else "output"
            print(f"  [{i}] {tag}  ch_in={ch_in}  rate={int(rate)}  '{name}'")
            if ch_in > 0:
                input_devices.append((i, name))
        except Exception as e:
            print(f"  [{i}] ERROR: {e}")

    try:
        default_info = pa.get_default_input_device_info()
        print(f"\nDefault input device: [{default_info['index']}] '{default_info['name']}'")
    except Exception as e:
        print(f"\nNo default input: {e}")

    if not input_devices:
        print("\n[FATAL] No input devices found!")
        pa.terminate()
        return

    print("\n" + "=" * 70)
    print(f"Testing all {len(input_devices)} input device(s)...")
    print("SPEAK INTO THE MIC when prompted.\n")

    results = []

    for dev_idx, dev_name in input_devices:
        print(f"\n{'-' * 60}")
        print(f"Testing device [{dev_idx}]: '{dev_name}'")

        # Try to open stream at 16000Hz (SR needs this), fall back to native rate
        native_rate = 44100
        try:
            info_tmp = pa.get_device_info_by_index(dev_idx)
            native_rate = int(info_tmp.get('defaultSampleRate', 44100))
        except Exception:
            pass

        opened_rate = None
        for try_rate in [16000, native_rate, 44100, 48000]:
            try:
                stream = pa.open(
                    format=FORMAT,
                    channels=CHANNELS,
                    rate=try_rate,
                    input=True,
                    input_device_index=dev_idx,
                    frames_per_buffer=CHUNK
                )
                opened_rate = try_rate
                break
            except Exception as e:
                last_err = e
                continue

        if opened_rate is None:
            print(f"  CANNOT OPEN STREAM at any rate: {last_err}")
            results.append((dev_idx, dev_name, "OPEN_FAILED", 0.0, str(last_err)))
            continue

        print(f"  Stream opened at {opened_rate}Hz (native={native_rate}Hz). Recording {RECORD_SECONDS}s...")
        print(f"  > SPEAK NOW!")
        frames_data = b""
        chunk_rms_vals = []

        try:
            for _ in range(int(SAMPLE_RATE / CHUNK * RECORD_SECONDS)):
                chunk = stream.read(CHUNK, exception_on_overflow=False)
                frames_data += chunk
                chunk_rms_vals.append(compute_rms(chunk))
        except Exception as e:
            print(f"  ✗ READ ERROR: {e}")
            stream.stop_stream()
            stream.close()
            results.append((dev_idx, dev_name, "READ_FAILED", 0.0, str(e)))
            continue

        stream.stop_stream()
        stream.close()

        total_rms = compute_rms(frames_data)
        peak_rms = max(chunk_rms_vals) if chunk_rms_vals else 0.0
        avg_rms = sum(chunk_rms_vals) / len(chunk_rms_vals) if chunk_rms_vals else 0.0

        print(f"  ✓ Recorded {len(frames_data)} bytes ({RECORD_SECONDS}s)")
        print(f"  ✓ RMS avg={avg_rms:.1f}  peak={peak_rms:.1f}  total={total_rms:.1f}")
        print(f"  ✓ Volume: {describe_rms(avg_rms)}")

        # Save WAV
        wav_name = f"diag_device_{dev_idx:02d}.wav"
        wav_path = os.path.join(DIAG_DIR, wav_name)
        save_wav(frames_data, wav_path)
        print(f"  ✓ Saved WAV: {wav_path}")

        # Try Google SR
        print(f"  > Testing Google Speech Recognition...")
        sr_result = test_google_sr(wav_path)
        print(f"  {sr_result}")

        results.append((dev_idx, dev_name, describe_rms(avg_rms), avg_rms, sr_result))

    pa.terminate()

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    for dev_idx, dev_name, vol_desc, rms, sr_result in results:
        status = "✓ USABLE" if "TRANSCRIPT" in sr_result else ("⚠ OPEN BUT SILENT" if rms < 50 else "⚠ NO TRANSCRIPT")
        print(f"  [{dev_idx}] '{dev_name}'")
        print(f"       Volume={vol_desc} (RMS={rms:.0f}) | SR={sr_result}")
        print(f"       Status: {status}")

    # Recommend best device
    best = [(idx, name, rms, sr_r) for idx, name, _, rms, sr_r in results if "TRANSCRIPT" in sr_r]
    if best:
        best.sort(key=lambda x: -x[2])
        b = best[0]
        print(f"\n✓ RECOMMENDED: device [{b[0]}] '{b[1]}' (RMS={b[2]:.0f})")
        print(f"  Set in backend/.env: MICROPHONE_INDEX={b[0]}")
    else:
        loud = [(idx, name, rms, sr_r) for idx, name, _, rms, sr_r in results if rms > 100]
        if loud:
            loud.sort(key=lambda x: -x[2])
            b = loud[0]
            print(f"\n⚠ No device produced a transcript. Loudest device: [{b[0]}] '{b[1]}' (RMS={b[2]:.0f})")
            print(f"  Check: mic not muted in Windows Sound settings? Say something loud during the test?")
        else:
            print(f"\n✗ ALL DEVICES RETURNED SILENT AUDIO.")
            print(f"  Check: Windows microphone privacy settings, mic not plugged in?")


if __name__ == "__main__":
    main()
