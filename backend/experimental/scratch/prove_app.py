import asyncio
import subprocess
import socket
import time
import sys
import os
import json

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

exe_path = r"C:\FRIDAY\release\FRIDAY\FRIDAY.exe"
ws_url = "ws://127.0.0.1:8001/api/ws"

def log(msg):
    print(msg)
    sys.stdout.flush()

log("==============================================================")
log("          FRIDAY LIVE PACKAGED APP E2E REPRODUCTION")
log("==============================================================\n")

def terminate_stale_processes():
    log("Terminating stale FRIDAY and port 8001 processes...")
    try:
        subprocess.run(["taskkill", "/F", "/IM", "FRIDAY.exe", "/T"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        log(f"taskkill error: {e}")
        
    try:
        import psutil
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                # Use safer net_connections checks on individual process with broad exceptions
                conns = proc.net_connections(kind='inet')
                for conn in conns:
                    if conn.laddr.port == 8001:
                        log(f"Killing process {proc.info['name']} (PID {proc.info['pid']}) on port 8001...")
                        proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
            except Exception as ex:
                continue
    except Exception as e:
        log(f"psutil cleanup error: {e}")

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
    terminate_stale_processes()
    
    log(f"Launching packaged executable: {exe_path}")
    try:
        proc = subprocess.Popen([exe_path], cwd=os.path.dirname(exe_path), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        log(f"[OK] FRIDAY.exe spawned with PID {proc.pid}")
    except Exception as e:
        log(f"[FATAL] Failed to spawn FRIDAY.exe: {e}")
        return

    log("Waiting for Uvicorn WebSocket server to spin up on port 8001...")
    start_time = time.time()
    server_ok = False
    while time.time() - start_time < 15:
        if is_server_running():
            server_ok = True
            break
        await asyncio.sleep(0.5)
        
    if not server_ok:
        log("[FATAL] Packaged application failed to start or bind to port 8001 within 15 seconds!")
        return
        
    log("[SUCCESS] Uvicorn WebSocket server is active on port 8001!")
    
    import websockets
    
    log(f"Connecting to live WebSocket: {ws_url}")
    try:
        async with websockets.connect(ws_url) as ws:
            log("[SUCCESS] WebSocket connection established successfully!\n")
            
            async def receive_events(until_type="result", timeout=8.0):
                events = []
                t_start = time.time()
                while time.time() - t_start < timeout:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                        msg = json.loads(raw)
                        events.append(msg)
                        log(f"  [WS EVENT] Received: {msg}")
                        if msg.get("type") == until_type:
                            break
                    except asyncio.TimeoutError:
                        continue
                    except Exception as e:
                        log(f"  [WS ERROR] {e}")
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
                log(f"\n------------------------------------------------------------")
                log(f"USER COMMAND: \"{cmd}\"")
                log(f"------------------------------------------------------------")
                
                payload = {"type": "command", "text": cmd}
                await ws.send(json.dumps(payload))
                log(f"  [WS EVENT] Emitted: {payload}")
                
                await receive_events(until_type="result", timeout=8.0)
            
            # Clean shutdown
            log(f"\n------------------------------------------------------------")
            log("Shutting down packaged application...")
            shutdown_payload = {"type": "shutdown"}
            await ws.send(json.dumps(shutdown_payload))
            log(f"  [WS EVENT] Emitted: {shutdown_payload}")
            await receive_events(until_type="state", timeout=2.0)
            
    except Exception as e:
        log(f"[FATAL] WebSocket error: {e}")
        
    log("\n==============================================================")
    log("          REPRODUCTION SEQUENCE COMPLETE!")
    log("==============================================================")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as ex:
        log(f"Crash in asyncio loop: {ex}")
