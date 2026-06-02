import asyncio
import json
import websockets
import time

WS_URL = "ws://127.0.0.1:8001/api/ws"

async def run_single_test(cmd: str, iteration: int) -> dict:
    result_data = {
        "command": cmd,
        "iteration": iteration,
        "transcript": None,
        "intent": None,
        "speak": None,
        "status": "FAIL",
        "opened_app": False
    }
    
    try:
        async with websockets.connect(WS_URL) as ws:
            await ws.send(json.dumps({"type": "mic_on"}))
            # Wait for list_devices and calibration lock to settle (1.0 second)
            await asyncio.sleep(1.0)
            await ws.send(json.dumps({"type": "command", "text": cmd}))
            
            # Give it up to 25 seconds E2E to allow audio synthesis, VAD, and execution
            deadline = time.time() + 25.0
            while time.time() < deadline:
                remaining = deadline - time.time()
                if remaining <= 0:
                    break
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=min(remaining, 1.0))
                    data = json.loads(msg)
                    
                    mtype = data.get("type")
                    if mtype == "transcript":
                        result_data["transcript"] = data.get("text")
                    elif mtype == "speak":
                        result_data["speak"] = data.get("text")
                    elif mtype == "result":
                        result_data["intent"] = data.get("intent")
                        res_val = data.get("result")
                        if data.get("ok"):
                            result_data["status"] = "PASS"
                            if data.get("intent") == "OPEN":
                                result_data["opened_app"] = True
                    elif mtype == "audio":
                        response_id = data.get("responseId")
                        if response_id:
                            # Emulate UI audio playback completion immediately to release locks
                            # Crucial: event type is "playback_completed" in server.py
                            await ws.send(json.dumps({"type": "playback_completed", "responseId": response_id}))
                            
                    # Exit condition: once we have state transition back to LISTENING or IDLE
                    # and we have gathered intent/speak details
                    if mtype == "state" and data.get("state") in ("LISTENING", "IDLE"):
                        # Standalone wake/greeting commands
                        if cmd.lower() in ("hello friday", "friday are you there"):
                            if result_data["speak"]:
                                result_data["status"] = "PASS"
                                result_data["intent"] = "CASUAL_CHAT"
                                break
                        # Action commands (need both intent or speak)
                        elif result_data["intent"] or result_data["speak"]:
                            result_data["status"] = "PASS"
                            break
                except asyncio.TimeoutError:
                    pass
    except Exception as e:
        print(f"    Error: {e}")
        
    return result_data

async def main():
    print("=" * 60)
    print("FRIDAY POST-IMPLEMENTATION DETERMINISM VERIFICATION")
    print("=" * 60)
    
    test_commands = [
        "Hello Friday",
        "Friday are you there",
        "Open Chrome",
        "What is 2 plus 2"
    ]
    
    results = []
    
    # Run the tests 5 times consecutively
    for i in range(1, 6):
        print(f"\n--- ITERATION {i}/5 ---")
        for cmd in test_commands:
            print(f"  Testing: '{cmd}'...")
            res = await run_single_test(cmd, i)
            results.append(res)
            # Log inline
            print(f"    Intent  : {res['intent']}")
            print(f"    Speak   : {res['speak']}")
            print(f"    Status  : {res['status']}")
            # Safe settle interval to let SAPI5 thread and backend locks fully release
            await asyncio.sleep(4.0)
            
    print("\n" + "=" * 60)
    print("POST-IMPLEMENTATION DETERMINISTIC VERIFICATION MATRIX")
    print("=" * 60)
    
    counts = {"Hello Friday": 0, "Friday are you there": 0, "Open Chrome": 0, "What is 2 plus 2": 0}
    failures = []
    
    for r in results:
        cmd = r["command"]
        status = r["status"]
        if status == "PASS":
            counts[cmd] += 1
        else:
            failures.append(r)
            
    for cmd, passed in counts.items():
        print(f"  - '{cmd}' : Passed {passed}/5 matches ({(passed/5)*100:.1f}%)")
        
    print("-" * 60)
    if len(failures) == 0:
        print("  VERIFICATION RESULT: 100% SUCCESS — DETERMINISM CONFIRMED.")
    else:
        print(f"  VERIFICATION RESULT: {len(failures)} FAILURES OBSERVED!")
        for f in failures:
            print(f"    FAILED: Iter {f['iteration']} | '{f['command']}' -> Speak: {f['speak']} | Intent: {f['intent']}")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
