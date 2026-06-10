import os
import sys
import asyncio
import subprocess
import websockets
import json

# Load env to find token
token = ""
env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
if os.path.exists(env_path):
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                if k.strip() == "FRIDAY_AUTH_TOKEN":
                    token = v.strip().strip('"').strip("'")

# Log file
log_path = os.path.join(os.path.dirname(__file__), "smoke_test_r4.log")
log_file = open(log_path, "w", encoding="utf-8")

def log(msg):
    print(msg, flush=True)
    log_file.write(msg + "\n")
    log_file.flush()

def delete_qdrant_lock():
    lock_path = "c:\\FRIDAY\\backend\\data\\qdrant\\.lock"
    if os.path.exists(lock_path):
        try:
            os.remove(lock_path)
            log("[SMOKE] Deleted stale Qdrant lock file successfully.")
        except Exception as e:
            log(f"[SMOKE WARNING] Could not delete Qdrant lock file: {e}")

async def read_stdout(proc):
    loop = asyncio.get_running_loop()
    while True:
        line = await loop.run_in_executor(None, proc.stdout.readline)
        if not line:
            break
        decoded = line.decode("utf-8", errors="ignore").strip()
        log(f"[SERVER] {decoded}")

async def wait_for_idle(ws, last_corr_id=None, timeout=30.0):
    start_time = asyncio.get_event_loop().time()
    
    # 1. Wait for FSM to leave IDLE state (start processing)
    while True:
        elapsed = asyncio.get_event_loop().time() - start_time
        if elapsed > timeout:
            log(f"[SMOKE WARNING] Timeout waiting for FSM to start (limit {timeout}s)")
            break
        try:
            msg_str = await asyncio.wait_for(ws.recv(), timeout=1.0)
            log(f"[WS CLIENT] Received: {msg_str}")
            msg = json.loads(msg_str)
            if msg.get("type") == "confirm_required":
                corr_id = msg.get("correlation_id")
                log(f"[SMOKE] Received confirm_required for {msg.get('tool_name')}. Autoconfirming...")
                await ws.send(json.dumps({
                    "type": "user_confirmed",
                    "correlation_id": corr_id
                }))
            elif msg.get("type") == "fsm_state_change":
                state = msg.get("state")
                corr_id = msg.get("correlation_id")
                if state != "IDLE":
                    log(f"[SMOKE] FSM started processing (state={state}).")
                    break
        except asyncio.TimeoutError:
            pass
        except websockets.exceptions.ConnectionClosed as e:
            log(f"[SMOKE ERROR] Connection closed in wait_for_idle phase 1: {e}")
            raise e
            
    # 2. Now wait for FSM to return to IDLE state
    while True:
        elapsed = asyncio.get_event_loop().time() - start_time
        if elapsed > timeout:
            log(f"[SMOKE WARNING] Timeout waiting for IDLE state (limit {timeout}s)")
            return last_corr_id
        try:
            msg_str = await asyncio.wait_for(ws.recv(), timeout=1.0)
            log(f"[WS CLIENT] Received: {msg_str}")
            msg = json.loads(msg_str)
            if msg.get("type") == "confirm_required":
                corr_id = msg.get("correlation_id")
                log(f"[SMOKE] Received confirm_required for {msg.get('tool_name')}. Autoconfirming...")
                await ws.send(json.dumps({
                    "type": "user_confirmed",
                    "correlation_id": corr_id
                }))
            elif msg.get("type") == "fsm_state_change":
                state = msg.get("state")
                corr_id = msg.get("correlation_id")
                if state == "IDLE":
                    log(f"[SMOKE] FSM reached IDLE state for correlation_id={corr_id}.")
                    return corr_id
        except asyncio.TimeoutError:
            pass
        except websockets.exceptions.ConnectionClosed as e:
            log(f"[SMOKE ERROR] Connection closed in wait_for_idle phase 2: {e}")
            raise e

async def main():
    # Delete stale lock file before boot
    delete_qdrant_lock()

    log("[SMOKE] Starting FRIDAY backend server...")
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # Start server
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api.server:app", "--host", "127.0.0.1", "--port", "8001"],
        cwd=backend_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env
    )
    
    # Start reading server stdout in background
    stdout_task = asyncio.create_task(read_stdout(proc))
    
    # Wait for server to boot and connect
    log("[SMOKE] Waiting for server to boot...")
    ws_url = "ws://127.0.0.1:8001/api/ws"
    if token:
        ws_url += f"?token={token}"

    ws = None
    for attempt in range(15):
        try:
            log(f"[SMOKE] Connecting to WebSocket (attempt {attempt+1}/15): {ws_url}")
            ws = await websockets.connect(ws_url)
            log("[SMOKE] Connected successfully!")
            break
        except Exception as e:
            log(f"[SMOKE] Connection failed, retrying in 2s... Error: {e}")
            await asyncio.sleep(2.0)

    if not ws:
        log("[SMOKE ERROR] WebSocket client failed to connect after 15 attempts")
    else:
        try:
            # Wait for server startup tasks to settle down
            log("[SMOKE] Sleeping 15s to let server startup and warm up...")
            await asyncio.sleep(15.0)

            # Turn off microphone to ensure no ambient noise triggers concurrent FSM turns
            log("[SMOKE] Turning microphone off via WS...")
            await ws.send(json.dumps({
                "type": "mic_off"
            }))
            await asyncio.sleep(1.0)

            # Flush any initial messages (like initial state broadcast)
            while True:
                try:
                    init_msg = await asyncio.wait_for(ws.recv(), timeout=0.5)
                    log(f"[WS CLIENT INITIAL] Received: {init_msg}")
                except asyncio.TimeoutError:
                    break

            queries = [
                "open Notepad",
                "what is the system status?",
                "delete C:/test.txt"
            ]
            
            last_corr_id = None
            for query in queries:
                log(f"\n[SMOKE] --- Processing Query: '{query}' ---")
                await ws.send(json.dumps({
                    "type": "command",
                    "text": query
                }))
                # Wait for FSM to cycle back to IDLE
                last_corr_id = await wait_for_idle(ws, last_corr_id)
                await asyncio.sleep(2.0) # wait a couple of seconds between queries
                
            await ws.close()
        except Exception as e:
            log(f"[SMOKE ERROR] Communication failed: {e}")
        
    log("[SMOKE] Terminating server...")
    proc.terminate()
    try:
        proc.wait(timeout=5.0)
    except subprocess.TimeoutExpired:
        proc.kill()
        
    # Cancel stdout task
    stdout_task.cancel()
    
    # Delete lock file after shutdown
    delete_qdrant_lock()

    log("[SMOKE] Smoke test complete.")
    log_file.close()

if __name__ == "__main__":
    asyncio.run(main())
