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

from contextlib import asynccontextmanager
import asyncio
import sys
from typing import Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from core.pipeline import process_transcript, set_web_session_active, cancel_speak
from core.realtime_emit import register_json_emitter, unregister_json_emitter
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
    loop = asyncio.get_running_loop()
    set_main_loop(loop)
    register_state_callback(broadcast_state)
    register_json_emitter(emit_to_clients)

    reset_stop()                         # arm the mic listener
    agent_task = loop.create_task(agent_loop())

    try:
        yield
    finally:
        print("[SERVER] Shutting down — stopping all subsystems...")

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
        unregister_json_emitter(emit_to_clients)
        unregister_state_callback(broadcast_state)

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
    # Send current state immediately so UI doesn't show stale "Waiting"
    await _prune_send(websocket, {"type": "state", "state": get_state()})

    try:
        while True:
            msg = await websocket.receive_json()
            msg_type = msg.get("type", "")

            if msg_type == "command":
                text = msg.get("text", "").strip()
                if text:
                    asyncio.get_running_loop().create_task(_run_command(text))

            elif msg_type == "stop_speaking":
                cancel_speak()
                await _send_all_json({"type": "state", "state": AssistantState.IDLE})

            elif msg_type == "mic_off":
                # Disable backend microphone listener immediately
                set_mic_enabled(False)
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
        clients.discard(websocket)
    except Exception as e:
        print(f"[WS ERROR] {e}")
        clients.discard(websocket)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)
