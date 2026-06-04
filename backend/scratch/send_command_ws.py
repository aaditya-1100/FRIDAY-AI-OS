import asyncio
import json
import os
import sys
import time
import websockets

LOG_FILE = "C:/FRIDAY/backend/friday_runtime.log"

async def run_query(query: str):
    print(f"\nExecuting Query: '{query}'")
    
    # 1. Record current log size
    start_pos = 0
    if os.path.exists(LOG_FILE):
        start_pos = os.path.getsize(LOG_FILE)
        
    # 2. Connect to WebSocket
    uri = "ws://127.0.0.1:8001/api/ws"
    try:
        async with websockets.connect(uri) as websocket:
            # Receive initial state
            init_msg = await websocket.recv()
            
            # Send command
            cmd = {"type": "command", "text": query}
            await websocket.send(json.dumps(cmd))
            
            # Monitor state or timeout
            start_time = time.time()
            speaking_started = False
            
            while time.time() - start_time < 12.0:
                try:
                    # Timeout read after 1 second to check elapsed time
                    msg_str = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                    msg = json.loads(msg_str)
                    
                    if msg.get("type") == "state":
                        state = msg.get("state")
                        print(f"  [STATE CHANGE] -> {state}")
                        if state == "SPEAKING":
                            speaking_started = True
                        elif state in ("LISTENING", "IDLE") and speaking_started:
                            # Finished speaking
                            break
                except asyncio.TimeoutError:
                    pass
    except Exception as e:
        print(f"  [ERROR] WS connection failed: {e}")
        return
        
    # 3. Wait a bit for log flush
    await asyncio.sleep(1.0)
    
    # 4. Print new log entries
    if os.path.exists(LOG_FILE):
        end_pos = os.path.getsize(LOG_FILE)
        if end_pos > start_pos:
            with open(LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
                f.seek(start_pos)
                new_logs = f.read()
                print("=" * 60)
                print("                  RUNTIME LOGS")
                print("=" * 60)
                safe_logs = new_logs.encode("ascii", errors="replace").decode("ascii")
                print(safe_logs.strip())
                print("=" * 60)
        else:
            print("  [WARNING] No new log entries written to friday_runtime.log")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python send_command_ws.py <query>")
        sys.exit(1)
        
    query = " ".join(sys.argv[1:])
    asyncio.run(run_query(query))
