import asyncio
import subprocess
import socket
import time
import sys
import os

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

exe_path = r"C:\FRIDAY\release\FRIDAY\FRIDAY.exe"
ws_url = "ws://127.0.0.1:8001/api/ws"

print("==============================================================")
print("          FRIDAY LIVE PACKAGED APP E2E REPRODUCTION")
print("==============================================================\n")

def is_server_running():
    try:
        s = socket.socket()
        s.settimeout(0.5)
        s.connect(("127.0.0.1", 8001))
        s.close()
        return True
    except Exception:
        return False

async def main():
    # 1. Start the actual packaged FRIDAY.exe
    print(f"Launching packaged executable: {exe_path}")
    proc = subprocess.Popen([exe_path], cwd=os.path.dirname(exe_path), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # 2. Wait for port 8001 to become active (up to 15 seconds)
    print("Waiting for Uvicorn WebSocket server to spin up on port 8001...")
    start_time = time.time()
    server_ok = False
    while time.time() - start_time < 15:
        if is_server_running():
            server_ok = True
            break
        await asyncio.sleep(0.5)
        
    if not server_ok:
        print("[FATAL] Packaged application failed to start or bind to port 8001!")
        sys.exit(1)
        
    print("✓ Uvicorn WebSocket server is active!")
    
    # 3. Connect WebSocket client
    import websockets
    import json
    
    print(f"Connecting to live WebSocket: {ws_url}")
    try:
        async with websockets.connect(ws_url) as ws:
            print("✓ WebSocket connection established successfully!\n")
            
            # Helper to receive messages with timeout
            async def receive_events(until_type="result", timeout=8.0):
                events = []
                t_start = time.time()
                while time.time() - t_start < timeout:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                        msg = json.loads(raw)
                        events.append(msg)
                        print(f"  [WS EVENT] Received: {msg}")
                        if msg.get("type") == until_type:
                            # If it is a result type, we can stop early
                            break
                    except asyncio.TimeoutError:
                        continue
                    except Exception as e:
                        print(f"  [WS ERROR] {e}")
                        break
                return events

            # Read initial state broadcast
            initial = await receive_events(until_type="state", timeout=3.0)
            
            # Commands to interact exactly as a user:
            commands = [
                "Friday",
                "Hello Friday",
                "Open Chrome",
                "What is 2 plus 2"
            ]
            
            for cmd in commands:
                print(f"\n------------------------------------------------------------")
                print(f"USER SPOKE/COMMAND: \"{cmd}\"")
                print(f"------------------------------------------------------------")
                
                # Send text command over live WebSocket
                payload = {"type": "command", "text": cmd}
                await ws.send(json.dumps(payload))
                print(f"  [WS EVENT] Emitted: {payload}")
                
                # Receive and print all state transitions, transcripts, and speak events
                await receive_events(until_type="result", timeout=8.0)
            
            # Send clean shutdown message to release lock and exit cleanly
            print(f"\n------------------------------------------------------------")
            print("Shutting down packaged application...")
            shutdown_payload = {"type": "shutdown"}
            await ws.send(json.dumps(shutdown_payload))
            print(f"  [WS EVENT] Emitted: {shutdown_payload}")
            await receive_events(until_type="state", timeout=2.0)
            
    except Exception as e:
        print(f"[FATAL] WebSocket error: {e}")
        
    print("\n==============================================================")
    print("          REPRODUCTION SEQUENCE COMPLETE!")
    print("==============================================================")

if __name__ == "__main__":
    asyncio.run(main())
