import asyncio
import json
import websockets
import time

WS_URL = "ws://127.0.0.1:8001/api/ws"

async def run_reproduction_test(cmd: str, timeout: float = 12.0):
    print(f"\n{'-'*60}")
    print(f"Executing: '{cmd}'")
    print(f"{'-'*60}")
    
    events = []
    try:
        async with websockets.connect(WS_URL) as ws:
            # 1. Enable mic
            await ws.send(json.dumps({"type": "mic_on"}))
            # 2. Send transcript command
            await ws.send(json.dumps({"type": "command", "text": cmd}))
            
            deadline = time.time() + timeout
            while time.time() < deadline:
                remaining = deadline - time.time()
                if remaining <= 0:
                    break
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=min(remaining, 2.0))
                    data = json.loads(msg)
                    events.append(data)
                    
                    mtype = data.get("type")
                    if mtype == "state":
                        print(f"  [STATE CHANGE] -> {data.get('state')}")
                        # If we transition back to IDLE or LISTENING, and we already got something, we can stop
                        if data.get("state") == "LISTENING" and len(events) > 3:
                            break
                    elif mtype == "transcript":
                        print(f"  [TRANSCRIPT] raw='{data.get('text')}'")
                    elif mtype == "speak":
                        print(f"  [SPEAK RESPONSE] -> '{data.get('text')}'")
                    elif mtype == "result":
                        print(f"  [RESULT] ok={data.get('ok')} | intent='{data.get('intent')}' | action_result={data.get('result')}")
                    elif mtype == "audio":
                        print(f"  [AUDIO PLAYBACK] {len(data.get('audioBase64', ''))} bytes base64 payload")
                        # Emulate frontend playback completion confirmation to unlock the SAPI5 speak lock immediately!
                        response_id = data.get("responseId")
                        if response_id:
                            print(f"  [EMULATOR] Confirming audio playback completion for responseId='{response_id}'")
                            await ws.send(json.dumps({"type": "audio_done", "responseId": response_id}))
                    else:
                        print(f"  [{mtype.upper()}] {data}")
                except asyncio.TimeoutError:
                    pass
    except Exception as e:
        print(f"  [CONNECTION ERROR] {e}")
        
    return events

async def main():
    print("FRIDAY Packaged E2E Reproduction Session starting...")
    await asyncio.sleep(1.0)
    
    # Test A: Hello Friday
    await run_reproduction_test("Hello Friday")
    
    # Test B: Hello Friday (deterministic repeat 3 times)
    print("\nDeterministic Greeting Repeat Test:")
    for i in range(3):
        await run_reproduction_test("Hello Friday")
        await asyncio.sleep(0.5)
        
    # Test C: Friday are you there
    await run_reproduction_test("Friday are you there")
    
    # Test D: Open Chrome
    await run_reproduction_test("Open Chrome")
    
    # Test E: What is 2 plus 2
    await run_reproduction_test("What is 2 plus 2")

if __name__ == "__main__":
    asyncio.run(main())
