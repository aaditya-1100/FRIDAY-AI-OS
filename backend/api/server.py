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
        # Append on start to preserve electron startup logs
        if original == sys.stdout:
            try:
                with open(self.log_file, "a", encoding="utf-8") as f:
                    f.write(f"\n--- FRIDAY RUNTIME LOG START {datetime.datetime.now()} ---\n")
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
                backend_marker = os.path.normcase(_backend_dir).lower()
                is_friday_backend = (
                    ("python" in pname or "uvicorn" in cmdline)
                    and ("api.server" in cmdline or "backend" in cmdline)
                    and backend_marker in os.path.normcase(cmdline)
                )
                if is_friday_backend:
                    print(f"[STARTUP LOCK] Found previous FRIDAY backend instance (PID {old_pid}). Requesting clean termination...")
                    proc.terminate()
                    try:
                        proc.wait(timeout=4.0)
                        print(f"[STARTUP LOCK] Previous backend instance (PID {old_pid}) terminated successfully.")
                    except psutil.TimeoutExpired:
                        print(f"[STARTUP LOCK WARNING] Previous backend PID {old_pid} did not exit after terminate(). Leaving it untouched.")
                else:
                    print(f"[STARTUP LOCK WARNING] Ignoring PID {old_pid}; it does not look like this FRIDAY backend.")
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

from core.realtime_emit import register_json_emitter, unregister_json_emitter, register_event_loop
from main import main as agent_loop
from voice.listen import request_stop, set_mic_enabled, reset_stop
from friday.core.fsm import cognitive_core, AssistantState

# Replaced state manager and pipeline functions for Cognitive OS
def get_state() -> str:
    try:
        state = cognitive_core.fsm.current_state
        if hasattr(state, "value"):
            return state.value
        return str(state)
    except Exception as e:
        print(f"[GET_STATE ERROR] {e}")
        return "IDLE"

def get_active_agent():
    try:
        working_memory = cognitive_core.fsm.working_memory or {}
        plan_type = working_memory.get("plan_type")
        if plan_type == "SINGLE":
            return working_memory.get("agent_type")
        elif plan_type == "MULTI":
            actions = working_memory.get("parsed_intent", {}).get("actions", [])
            if actions and isinstance(actions, list):
                from friday.core.routing_table import INTENT_TO_AGENT
                first_action = actions[0]
                sub_intent = first_action.get("intent")
                return INTENT_TO_AGENT.get(sub_intent, "PC_AGENT")
    except Exception:
        pass
    return None

def set_main_loop(loop):
    raise NotImplementedError("replaced by cognitive OS in Phase R1")

def register_state_callback(cb):
    raise NotImplementedError("replaced by cognitive OS in Phase R1")

def unregister_state_callback(cb):
    raise NotImplementedError("replaced by cognitive OS in Phase R1")

def set_web_session_active(value: bool = True) -> None:
    raise NotImplementedError("replaced by cognitive OS in Phase R1")

def cancel_speak() -> None:
    from voice.speak import cancel_play
    cancel_play()
    cognitive_core.fsm.transition_to(AssistantState.IDLE, reason="Cancellation requested", force=True)

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



async def broadcast_state(state: str) -> None:
    await _send_all_json({"type": "state", "state": state})


async def emit_to_clients(payload: dict) -> None:
    await _send_all_json(payload)


# -- Application lifespan -------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    enforce_single_backend_instance()
    from config.paths import ensure_data_dirs
    ensure_data_dirs()
    loop = asyncio.get_running_loop()
    from core.state_manager import set_main_loop as sm_set_main_loop
    sm_set_main_loop(loop)

    # Start event bus and FSM WS manager
    from friday.core.event_bus import event_bus
    from friday.api.websocket import fsm_ws_manager
    event_bus.start(loop)
    fsm_ws_manager.start()

    # Bridge legacy state_manager callback to WS manager broadcast
    from core.state_manager import register_state_callback as sm_register
    async def sm_callback(state):
        await fsm_ws_manager.broadcast({"type": "state", "state": state})
    sm_register(sm_callback)

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
    
    print("[STARTUP] SAPI5 local TTS engine lazy-init is deferred to first-use fallback.")

    reset_stop()                         # arm the mic listener
    agent_task = loop.create_task(agent_loop())

    # Pre-warm Faster-Whisper model in a background thread.
    # WhisperModel() only loads weights into RAM — it does NOT open any audio
    # device, so this is Bluetooth A2DP safe. By the time Sir presses the
    # hotkey the model is already loaded and first transcription is instant.
    def _prewarm_whisper():
        try:
            from voice.listen import _get_whisper_model
            _get_whisper_model()
            print("[STARTUP] Faster-Whisper model pre-warmed successfully.")
        except Exception as e_pw:
            print(f"[STARTUP WARNING] Whisper pre-warm failed (non-fatal): {e_pw}")
    loop.run_in_executor(None, _prewarm_whisper)

    try:
        yield
    finally:
        print("[SERVER] Shutting down — stopping all subsystems...")

        # Unregister legacy state_manager callback bridge
        from core.state_manager import unregister_state_callback as sm_unregister
        try:
            sm_unregister(sm_callback)
        except Exception:
            pass

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
        
        # Stop event bus
        try:
            from friday.core.event_bus import event_bus
            await event_bus.stop()
        except Exception as e_eb:
            print(f"[SHUTDOWN WARNING] Failed to stop event bus: {e_eb}")
            
        try:
            from friday.memory.semantic import close_qdrant_client
            close_qdrant_client()
        except Exception as e_qdrant:
            print(f"[SHUTDOWN WARNING] Failed to close Qdrant client: {e_qdrant}")

        cleanup_backend_pid()

        print("[SERVER] All subsystems stopped.")


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(title="FRIDAY", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.getenv(
            "FRIDAY_CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173,file://,null",
        ).split(",")
        if origin.strip()
    ],
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

    LAT = float(os.getenv("FRIDAY_WEATHER_LAT", "29.2098"))
    LON = float(os.getenv("FRIDAY_WEATHER_LON", "78.9618"))
    loc_name = os.getenv("FRIDAY_WEATHER_LOCATION", "Kashipur, Uttarakhand, India")

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
        from friday.core.events import EventEnvelope, EventPriority
        from friday.core.event_bus import event_bus
        from uuid import uuid4
        envelope = EventEnvelope(
            topic="friday.perception.text.input",
            priority=EventPriority.P1,
            source="user_interface.websocket",
            correlation_id=uuid4(),
            session_id=uuid4(),
            payload={"text": text, "is_voice": False}
        )
        await event_bus.publish(envelope)
    except Exception as e:
        print(f"[API COMMAND ERROR] {e}")


# ── WebSocket endpoint ────────────────────────────────────────────────────────

@app.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket):
    origin = websocket.headers.get("origin")
    if origin:
        origin_lower = origin.strip().lower()
        # "null" is sent by Electron 42+ (Chromium 130+) when loading from file://
        # file:// and file:///path/... are sent by older Electron / dev builds
        _allowed_origins = {"file://", "http://localhost:5173", "null"}
        if origin_lower not in _allowed_origins and not origin_lower.startswith("file://"):
            print(f"[WS AUTH FAIL] Origin '{origin}' is not authorized.")
            await websocket.close(code=1008)
            return

    expected_token = os.getenv("FRIDAY_AUTH_TOKEN")
    if expected_token:
        token = websocket.query_params.get("token")
        if token != expected_token:
            print(f"[WS AUTH FAIL] Invalid or missing auth token: '{token}'")
            await websocket.close(code=1008)
            return

    await websocket.accept()
    clients.add(websocket)
    from friday.api.websocket import fsm_ws_manager
    fsm_ws_manager.register_client(websocket)
    # Re-arm mic stopping state cleanly. Do not enable mic automatically —
    # wait for the client's explicit "mic_on" / "mic_off" sync message.
    reset_stop()
    # Bug 2 fix: Never send LISTENING/PERCEIVING as the initial snapshot.
    # If the FSM is mid-active-turn at connection time, reflect it.
    # If it's LISTENING or any other non-active state at connection open, send
    # IDLE — LISTENING without a keypress means a stale or race-condition state.
    _ACTIVE_FSM_STATES = {
        "PERCEIVING", "PLANNING", "DELEGATING", "WAITING",
        "SYNTHESIZING", "RESPONDING", "REFLECTING"
    }
    _snap_state = get_state()
    if _snap_state not in _ACTIVE_FSM_STATES:
        _snap_state = "IDLE"
    await _prune_send(websocket, {"type": "state", "state": _snap_state, "active_agent": get_active_agent()})

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
                cognitive_core.fsm.transition_to(AssistantState.IDLE, reason="UI disabled mic", force=True)
                print("[MIC] Disabled by UI")

            elif msg_type == "force_idle":
                cognitive_core.abort_current_turn()
                cancel_speak()
                set_mic_enabled(False)
                cognitive_core.fsm.transition_to(AssistantState.IDLE, reason="Forced idle by UI double click", force=True)
                print("[WS INCOMING] Forced state to IDLE by client request")

            elif msg_type == "mic_on":
                # Re-enable backend microphone listener
                mode = msg.get("mode")
                reset_stop()
                set_mic_enabled(True, mode=mode)
                from core.state_manager import set_state
                # Only transition to LISTENING immediately if this is an active voice turn command (mode is provided)
                if mode is not None:
                    set_state("LISTENING")
                    print(f"[MIC] Enabled by UI. Transitioned state to LISTENING immediately. Mode={mode}")
                else:
                    print(f"[MIC] Enabled by UI (mic_on synced). Mode={mode}")

            elif msg_type == "shutdown":
                # UI-initiated full shutdown
                print("[SHUTDOWN] Requested by UI")
                await _send_all_json({"type": "state", "state": AssistantState.IDLE})
                await _close_all_clients()
                asyncio.get_running_loop().call_later(0.3, sys.exit, 0)

            elif msg_type == "ping":
                await _prune_send(websocket, {"type": "pong"})

            elif msg_type == "user_confirmed":
                from friday.core.events import EventEnvelope, EventPriority
                from friday.core.event_bus import event_bus
                from uuid import UUID, uuid4
                corr_id = msg.get("correlation_id")
                envelope = EventEnvelope(
                    topic="friday.tool.user_confirmed",
                    priority=EventPriority.P0,
                    source="user_interface.websocket",
                    correlation_id=UUID(corr_id) if corr_id else uuid4(),
                    session_id=uuid4(),
                    payload={}
                )
                asyncio.get_running_loop().create_task(event_bus.publish(envelope))
                print(f"[WS SERVER] Published user_confirmed for correlation_id={corr_id}")

    except (WebSocketDisconnect, RuntimeError):
        pass
    except Exception as e:
        print(f"[WS ERROR] {e}")
    finally:
        clients.discard(websocket)
        from friday.api.websocket import fsm_ws_manager
        fsm_ws_manager.unregister_client(websocket)
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

        # Safely record or report active microphone usage
        res = vl.diag_record_sample(duration=1.0)
        return res
    except Exception as e_outer:
        print(f"[DIAG MIC] Unexpected diagnostic failure: {e_outer}")
        return {"ok": False, "error": str(e_outer)}


@app.post("/api/diag/play_tts")
async def diag_play_tts():
    """Trigger a sample TTS playback event for diagnostics."""
    raise NotImplementedError("replaced by cognitive OS in Phase R1")


if __name__ == "__main__":
    import socket
    import sys
    import uvicorn
    
    port = 8001
    host = "127.0.0.1"
    
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind((host, port))
        s.close()
    except socket.error:
        print(f"[SERVER ERROR] Port {port} is already in use by another process. Exiting cleanly.")
        sys.exit(1)
        
    uvicorn.run(app, host=host, port=port)
