"""
FastAPI + WebSocket: state sync and text commands for the React UI.
Run:  python -m uvicorn api.server:app --host 127.0.0.1 --port 8001
(cwd = backend, or PYTHONPATH includes backend)

Shutdown contract:
- lifespan finally: cancel agent_task, close all WS clients, stop mic thread.
- WS message 'mic_off': disable backend listening immediately.
- WS message 'mic_on' : re-enable backend listening.
- WS message 'stop_speaking': cancel TTS and broadcast IDLE.
- WS message 'shutdown': trigger full process exit.
"""
import sys
import os
import datetime

# ── Load .env BEFORE any other imports ────────────────────────────────────────
# Critical for packaged FRIDAY.exe where uvicorn doesn't auto-load .env files.
# This ensures SERPER_API_KEY, GROQ_API_KEY, TAVILY_API_KEY are in os.environ.
_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_env_path = os.path.join(_backend_dir, ".env")
if not os.path.exists(_env_path):
    _env_path = os.path.join(os.path.dirname(_backend_dir), ".env")

if os.path.exists(_env_path):
    try:
        with open(_env_path, "r", encoding="utf-8") as _f:
            for _line in _f:
                _line = _line.strip()
                if _line and not _line.startswith("#") and "=" in _line:
                    _key, _val = _line.split("=", 1)
                    _key = _key.strip()
                    _val = _val.strip().strip('"').strip("'")
                    if _key and _key not in os.environ:
                        os.environ[_key] = _val
        print(f"[STARTUP] Loaded environment from {_env_path}")
    except Exception as _e:
        print(f"[STARTUP WARNING] Failed to load .env: {_e}")

import queue
import threading

class TeeLogger:
    def __init__(self, original):
        self.terminal = original
        self.log_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "friday_runtime.log")
        # Overwrite on start
        if original == sys.stdout:
            try:
                with open(self.log_file, "w", encoding="utf-8") as f:
                    f.write(f"--- FRIDAY RUNTIME LOG START {datetime.datetime.now()} ---\n")
            except Exception:
                pass
        
        self.queue = queue.Queue()
        self.worker = threading.Thread(target=self._log_writer, daemon=True)
        self.worker.start()
        
    def _log_writer(self):
        while True:
            msg = self.queue.get()
            if msg is None:
                break
            try:
                with open(self.log_file, "a", encoding="utf-8") as f:
                    f.write(msg)
            except Exception:
                pass
            self.queue.task_done()
            
    def write(self, message):
        try:
            self.terminal.write(message)
        except UnicodeEncodeError:
            # Safe fallback for Windows cp1252 terminals
            safe_msg = message.encode("ascii", errors="replace").decode("ascii")
            self.terminal.write(safe_msg)
        self.terminal.flush()
        self.queue.put(message)
            
    def flush(self):
        self.terminal.flush()

sys.stdout = TeeLogger(sys.stdout)
sys.stderr = TeeLogger(sys.stderr)



def enforce_single_backend_instance() -> None:
    """Enforce a single active python backend process on the system to prevent dangling duplicates."""
    import psutil
    
    pid_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "friday_backend.pid")
    my_pid = os.getpid()
    
    if os.path.exists(pid_file):
        try:
            with open(pid_file, "r") as f:
                old_pid = int(f.read().strip())
            
            if old_pid != my_pid and psutil.pid_exists(old_pid):
                proc = psutil.Process(old_pid)
                pname = proc.name().lower()
                cmdline = " ".join(proc.cmdline()).lower()
                if "python" in pname or "uvicorn" in cmdline:
                    print(f"[STARTUP LOCK] Found duplicate active backend instance (PID {old_pid}). Terminating it to take over...")
                    proc.kill()
                    proc.wait(timeout=2.0)
                    print(f"[STARTUP LOCK] Stale instance (PID {old_pid}) terminated successfully.")
        except Exception as e:
            print(f"[STARTUP LOCK WARNING] Error checking/killing stale backend PID: {e}")
            
    try:
        with open(pid_file, "w") as f:
            f.write(str(my_pid))
        print(f"[STARTUP LOCK] Backend instance registered successfully under PID {my_pid}.")
    except Exception as e:
        print(f"[STARTUP LOCK WARNING] Failed to record active PID lockfile: {e}")


def cleanup_backend_pid() -> None:
    """Release the active backend PID lockfile on shutdown."""
    pid_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "friday_backend.pid")
    if os.path.exists(pid_file):
        try:
            os.remove(pid_file)
            print("[SERVER] Backend PID lockfile released.")
        except Exception:
            pass

from contextlib import asynccontextmanager
import asyncio
import sys
from typing import Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from core.pipeline import process_transcript, set_web_session_active, cancel_speak
from core.realtime_emit import register_json_emitter, unregister_json_emitter, register_event_loop
from main import main as agent_loop
from core.state_manager import (
    AssistantState, get_state,
    register_state_callback, unregister_state_callback, set_main_loop,
)
from voice.listen import request_stop, set_mic_enabled, reset_stop

clients: Set[WebSocket] = set()


# ── WebSocket helpers ─────────────────────────────────────────────────────────

async def _prune_send(ws: WebSocket, payload: dict) -> bool:
    try:
        await ws.send_json(payload)
        return True
    except Exception:
        return False


async def _send_all_json(payload: dict) -> None:
    dead = []
    for ws in list(clients):
        if not await _prune_send(ws, payload):
            dead.append(ws)
    for ws in dead:
        clients.discard(ws)


async def _close_all_clients() -> None:
    """Gracefully close every connected WebSocket on shutdown."""
    for ws in list(clients):
        try:
            await ws.close(code=1001)   # 1001 = Going Away
        except Exception:
            pass
    clients.clear()


# ── State broadcast ───────────────────────────────────────────────────────────

async def broadcast_state(state: str) -> None:
    await _send_all_json({"type": "state", "state": state})


async def emit_to_clients(payload: dict) -> None:
    await _send_all_json(payload)


# ── Application lifespan ──────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    enforce_single_backend_instance()
    loop = asyncio.get_running_loop()
    set_main_loop(loop)
    register_state_callback(broadcast_state)
    register_json_emitter(emit_to_clients)
    # Register the event loop so emit_json_sync() can schedule coroutines from
    # the PyAudio thread (mic_level streaming during LISTENING state).
    register_event_loop(loop)
    from core.realtime_emit import register_client_count_callback, unregister_client_count_callback
    register_client_count_callback(lambda: len(clients))

    # Start temporal background scheduler task
    from system.temporal_engine import temporal_engine
    temporal_engine.start_scheduler(loop)

    # Start Runtime Stability Janitor and Watchdog
    from core.runtime_stability import get_stability_manager
    janitor = get_stability_manager(loop)
    janitor.start()

    # Trigger background installed apps indexing prefetch
    from system.app_control import ensure_app_index_loaded
    ensure_app_index_loaded()
    
    # Warm SAPI5 Singleton Startup
    try:
        from voice.speak import init_tts_singleton
        init_tts_singleton()
        print("[STARTUP] SAPI5 TTS singleton initialized successfully.")
    except Exception as e_tts:
        print(f"[STARTUP WARNING] Failed to warm SAPI5 singleton: {e_tts}")

    reset_stop()                         # arm the mic listener
    agent_task = loop.create_task(agent_loop())

    try:
        yield
    finally:
        print("[SERVER] Shutting down — stopping all subsystems...")

        # Stop Runtime Stability Janitor
        try:
            get_stability_manager().stop()
        except Exception:
            pass

        # Cancel temporal engine background task
        if temporal_engine._scheduler_task:
            temporal_engine._scheduler_task.cancel()

        # 1. Signal mic thread to stop immediately (unblocks sr.listen)
        request_stop()

        # 2. Cancel any in-flight TTS
        cancel_speak()

        # 3. Cancel the agent loop task and wait for it to finish
        agent_task.cancel()
        try:
            await asyncio.wait_for(asyncio.shield(agent_task), timeout=6.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass

        # 4. Close all WebSocket clients
        await _close_all_clients()

        # 5. Stop pygame mixer if it is still running
        try:
            import pygame
            if pygame.mixer.get_init():
                pygame.mixer.music.stop()
                pygame.mixer.quit()
        except Exception:
            pass

        # 6. Unregister callbacks
        unregister_client_count_callback()
        unregister_json_emitter(emit_to_clients)
        unregister_state_callback(broadcast_state)
        cleanup_backend_pid()

        print("[SERVER] All subsystems stopped.")


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(title="FRIDAY", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"ok": True, "state": get_state()}


@app.get("/api/weather")
def weather_endpoint():
    """
    Real-time weather with dynamic geo-location lookup.
    Uses ipapi.co to locate user, and Open-Meteo for hyper-accurate weather.
    Returns structured JSON for the frontend WeatherWidget.
    """
    import requests as _req
    from datetime import datetime as _dt

    LAT, LON = 29.2098, 78.9618  # Unconditionally locked to Kashipur, Uttarakhand, India
    loc_name = "Kashipur, Uttarakhand, India"

    _WMO = {
        0: ("Clear Sky", "clear"), 1: ("Mainly Clear", "clear"),
        2: ("Partly Cloudy", "cloudy"), 3: ("Overcast", "cloudy"),
        45: ("Foggy", "fog"), 48: ("Icy Fog", "fog"),
        51: ("Light Drizzle", "drizzle"), 53: ("Drizzle", "drizzle"), 55: ("Heavy Drizzle", "drizzle"),
        61: ("Light Rain", "rain"), 63: ("Moderate Rain", "rain"), 65: ("Heavy Rain", "rain"),
        71: ("Light Snow", "snow"), 73: ("Snow", "snow"), 75: ("Heavy Snow", "snow"),
        80: ("Showers", "rain"), 81: ("Showers", "rain"), 82: ("Heavy Showers", "rain"),
        95: ("Thunderstorm", "thunder"), 96: ("Thunderstorm", "thunder"), 99: ("Thunderstorm", "thunder"),
    }

    try:
        params = (
            f"latitude={LAT}&longitude={LON}"
            "&current=temperature_2m,apparent_temperature,relative_humidity_2m,"
            "weather_code,wind_speed_10m,wind_direction_10m,uv_index,precipitation"
            "&daily=temperature_2m_max,temperature_2m_min,sunrise,sunset,weather_code"
            "&wind_speed_unit=kmh&timezone=Asia/Kolkata&forecast_days=3"
        )
        r = _req.get(
            f"https://api.open-meteo.com/v1/forecast?{params}",
            timeout=8,
            headers={"User-Agent": "FRIDAY-Assistant/2.0"}
        )
        r.raise_for_status()
        d = r.json()
        cur = d["current"]
        daily = d.get("daily", {})

        code = cur.get("weather_code", 0)
        label, kind = _WMO.get(code, ("Unknown", "clear"))

        def fmt_time(iso_str):
            if not iso_str:
                return ""
            try:
                return _dt.fromisoformat(iso_str).strftime("%-I:%M %p")
            except Exception:
                # Windows doesn't support %-I
                dt = _dt.fromisoformat(iso_str)
                return dt.strftime("%I:%M %p").lstrip("0")

        # Build 3-day forecast
        forecast = []
        for i in range(min(3, len(daily.get("time", [])))):
            fc_code = daily["weather_code"][i]
            fc_label, fc_kind = _WMO.get(fc_code, ("Unknown", "clear"))
            forecast.append({
                "date": daily["time"][i],
                "max": round(daily["temperature_2m_max"][i]),
                "min": round(daily["temperature_2m_min"][i]),
                "label": fc_label,
                "kind": fc_kind,
            })

        return {
            "ok": True,
            "location": loc_name,
            "temp": round(cur["temperature_2m"]),
            "feels": round(cur["apparent_temperature"]),
            "humidity": cur["relative_humidity_2m"],
            "wind": round(cur["wind_speed_10m"]),
            "wind_dir": cur.get("wind_direction_10m", 0),
            "uv": round(cur.get("uv_index", 0)),
            "precip": round(cur.get("precipitation", 0), 1),
            "code": code,
            "label": label,
            "kind": kind,
            "sunrise": fmt_time(daily.get("sunrise", [""])[0]),
            "sunset":  fmt_time(daily.get("sunset",  [""])[0]),
            "forecast": forecast,
            "updated_at": _dt.now().strftime("%I:%M %p"),
        }

    except Exception as e:
        print(f"[WEATHER API ERROR] {e}")
        return {"ok": False, "error": str(e)}


async def _run_command(text: str) -> None:
    try:
        await process_transcript(text, web_mode=True)
    except Exception as e:
        print(f"[API COMMAND ERROR] {e}")


# ── WebSocket endpoint ────────────────────────────────────────────────────────

@app.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    clients.add(websocket)
    set_web_session_active(True)
    # Re-arm mic stopping state cleanly. Do not enable mic automatically —
    # wait for the client's explicit "mic_on" / "mic_off" sync message.
    reset_stop()
    await _prune_send(websocket, {"type": "state", "state": get_state()})

    from core.runtime_orchestrator import orchestrator
    orchestrator.set_websocket_state("CONNECTED")

    try:
        while True:
            msg = await websocket.receive_json()
            # Log raw incoming message for diagnostics
            try:
                print(f"[WS INCOMING] From client: {msg}")
            except Exception:
                print("[WS INCOMING] Received non-serializable message from client")
            msg_type = msg.get("type", "")

            if msg_type == "command":
                text = msg.get("text", "").strip()
                if text:
                    asyncio.get_running_loop().create_task(_run_command(text))

            elif msg_type == "stop_speaking":
                cancel_speak()
                # cancel_speak() already calls set_state(IDLE) which broadcasts via callback.
                # No need to send a second IDLE broadcast here.

            elif msg_type == "playback_completed":
                response_id = msg.get("responseId")
                from voice.speak import register_playback_completed
                register_playback_completed(response_id)

            elif msg_type == "mic_off":
                # Disable backend microphone listener immediately
                set_mic_enabled(False)
                # Cancel any active TTS playback or speak loops instantly
                cancel_speak()
                from core.state_manager import AssistantState, set_state
                set_state(AssistantState.IDLE)
                print("[MIC] Disabled by UI")

            elif msg_type == "mic_on":
                # Re-enable backend microphone listener
                reset_stop()
                set_mic_enabled(True)
                print("[MIC] Enabled by UI")

            elif msg_type == "shutdown":
                # UI-initiated full shutdown
                print("[SHUTDOWN] Requested by UI")
                await _send_all_json({"type": "state", "state": AssistantState.IDLE})
                await _close_all_clients()
                asyncio.get_running_loop().call_later(0.3, sys.exit, 0)

            elif msg_type == "ping":
                await _prune_send(websocket, {"type": "pong"})

    except (WebSocketDisconnect, RuntimeError):
        pass
    except Exception as e:
        print(f"[WS ERROR] {e}")
    finally:
        clients.discard(websocket)
        if len(clients) == 0:
            orchestrator.set_websocket_state("DISCONNECTED")


@app.get("/api/diag/mic")
def diag_mic():
    """Synchronous diagnostic endpoint to enumerate audio devices and capture a short sample.
    Runs quickly and returns basic RMS/transcript info to help debug microphone issues.
    """
    try:
        from voice import listen as vl
        # Enumerate devices (prints to backend logs)
        try:
            vl._list_all_microphones()
        except Exception as e_enum:
            print(f"[DIAG MIC] Device enumeration failed: {e_enum}")

        # Attempt to capture a short 1.0s sample using the persistent microphone
        try:
            mic = vl.get_open_microphone()
            recognizer = vl._get_recognizer()
            with mic as source:
                print("[DIAG MIC] Recording 1.0s test sample...")
                audio = recognizer.record(source, duration=1.0)
            rms = vl._compute_rms(audio)
            raw_len = len(audio.get_raw_data())
            transcript = None
            try:
                transcript = recognizer.recognize_google(audio, language="en-IN")
            except Exception as e_rec:
                transcript = f"(recognition failed: {e_rec})"
            wav_path = vl._save_audio_diag(audio, "diag_sample")
            return {"ok": True, "rms": rms, "raw_bytes": raw_len, "transcript": transcript, "wav": wav_path}
        except Exception as e:
            print(f"[DIAG MIC] Capture failed: {e}")
            return {"ok": False, "error": str(e)}

    except Exception as e_outer:
        print(f"[DIAG MIC] Unexpected diagnostic failure: {e_outer}")
        return {"ok": False, "error": str(e_outer)}


@app.post("/api/diag/play_tts")
async def diag_play_tts():
    """Trigger a sample TTS playback event for diagnostics."""
    try:
        from core.pipeline import safe_speak
        from core.realtime_emit import has_emitters
        if not has_emitters():
            return {"ok": False, "error": "No active frontend websocket clients connected."}
        asyncio.get_running_loop().create_task(safe_speak("This is a sample TTS test from Friday.", web_mode=True))
        return {"ok": True, "message": "Sample TTS playback triggered."}
    except Exception as e:
        print(f"[DIAG TTS] Failed to trigger sample TTS: {e}")
        return {"ok": False, "error": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)
