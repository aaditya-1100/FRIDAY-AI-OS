"""
manual_gate_validator.py — End-to-end real WebSocket validation gate client.
Optimized version: Runs with the microphone disabled (mic_off) to prevent
PortAudio thread congestion, noise calibration latency, and audio VAD blockages.
"""
import asyncio
import json
import sys
import time
import os
import websockets

WS_URL = "ws://127.0.0.1:8001/api/ws"
LOG_FILE = "backend/logs/manual_validation_gate.log"

os.makedirs("backend/logs", exist_ok=True)

# ── Setup 7 test groups (excluding stress test for automated client) ──────────
TEST_GROUPS = {
    "Group 1: Voice Pipeline": [
        "Hello Friday.",
        "How are you?",
        "Tell me a joke.",
        "What is Python?",
        "Who is PM of India?",
        "Who is PM of UK?",
        "Latest AI news."
    ],
    "Group 2: Memory": [
        "Who is Aaditya?",
        "Who built you?",
        "What do you know about me?",
        "What are my goals?",
        "What am I preparing for?",
        "Tell me more.",
        "What else?",
        "What about my studies?"
    ],
    "Group 3: Search": [
        "Who is PM of UK?",
        "Weather in Delhi.",
        "Latest OpenAI news.",
        "Latest SpaceX launch.",
        "Latest AI developments.",
        "Tell me more.",
        "When did that happen?",
        "Who announced it?"
    ],
    "Group 4: Maps": [
        "Open map of Paris.",
        "Show route to London.",
        "How long will it take?",
        "Which route is fastest?",
        "What cities will I cross?",
        "Show nearby airports.",
        "Show satellite view.",
        "Avoid tolls.",
        "How far is it?",
        "What about traffic?"
    ],
    "Group 5: Screen Cognition": [
        "Open YouTube.",
        "What am I watching?",
        "Who uploaded it?",
        "Summarize it.",
        "Explain it.",
        "Open a PDF.",
        "What am I reading?",
        "Summarize it."
    ],
    "Group 6: Pronoun Resolution": [
        "Open Chrome.",
        "Close it.",
        "Open Downloads.",
        "Open the newest file in it.",
        "Open map of Paris.",
        "Show route to London.",
        "How long will it take?",
        "Open latest Mark Rober video.",
        "Play it again.",
        "Who made it?"
    ],
    "Group 7: Commands": [
        "Open Chrome.",
        "Open Spotify.",
        "Open Calculator.",
        "Open Settings.",
        "Close Chrome.",
        "Close Settings.",
        "Increase volume.",
        "Decrease volume.",
        "Mute volume.",
        "Increase brightness.",
        "Decrease brightness.",
        "Open Downloads.",
        "Open Documents.",
        "Open Desktop.",
        "Lock PC.",
        "Sleep PC."
    ]
}

# Reset raw validation log file
with open(LOG_FILE, "w", encoding="utf-8") as f:
    f.write("=== FRIDAY REAL WEBSOCKET MANUAL VALIDATION GATE LOG ===\n\n")


async def run_single_query(ws, query: str, group_name: str) -> dict:
    """Send command via WebSocket, collect and analyze live responses."""
    print(f"\n[{group_name}] Query: \"{query}\"")
    
    # Send command
    await ws.send(json.dumps({"type": "command", "text": query}))
    
    result_data = {
        "query": query,
        "success": False,
        "brain": None,
        "intent": None,
        "speak_text": "",
        "has_audio": False,
        "audio_bytes": 0,
        "map_location": None,
        "state_flow": [],
        "errors": []
    }
    
    start_time = time.time()
    timeout = 35.0 # Max 35 seconds per turn to absorb Groq failover latencies
    deadline = start_time + timeout
    
    try:
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                result_data["errors"].append("Timeout exceeded")
                break
                
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=min(remaining, 1.0))
            except asyncio.TimeoutError:
                continue
                
            data = json.loads(msg)
            t = data.get("type")
            
            if t == "state":
                state = data.get("state")
                result_data["state_flow"].append(state)
                # Return to IDLE or LISTENING state is our processing boundaries signal
                if state in ("IDLE", "LISTENING") and (result_data["speak_text"] or result_data["intent"]):
                    break
            elif t == "thinking":
                result_data["brain"] = data.get("brain")
                print(f"  [THINKING] Routing to: {result_data['brain']}")
            elif t == "speak":
                result_data["speak_text"] = data.get("text", "")
                print(f"  [SPEAK] \"{result_data['speak_text'][:80]}...\"")
            elif t == "audio":
                result_data["has_audio"] = True
                b64 = data.get("audioBase64", "")
                result_data["audio_bytes"] += len(b64)
                # Emulate client playback completed acknowledgement
                response_id = data.get("responseId")
                await ws.send(json.dumps({"type": "playback_completed", "responseId": response_id}))
            elif t == "result":
                result_data["intent"] = data.get("intent")
                result_data["success"] = data.get("ok", False)
                print(f"  [RESULT] ok={result_data['success']} resolved_intent={result_data['intent']}")
            elif t == "show_map":
                result_data["map_location"] = data.get("location")
                print(f"  [MAP_UI] show_map event triggered: {result_data['map_location']}")
                
    except Exception as e:
        result_data["errors"].append(str(e))
        
    duration = time.time() - start_time
    result_data["duration"] = duration
    
    # ── Post-process turn evaluation ──────────────────────────────────────────
    # Check for empty/silent responses
    if not result_data["speak_text"] and result_data["success"]:
        # Command execution like LOCK or SLEEP might not generate spoken voice directly or might return success directly
        pass
    elif not result_data["speak_text"] and not result_data["errors"]:
        result_data["errors"].append("Silent response detected: Speak block empty")
        
    # Write details to log file
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"Query: \"{query}\"\n")
        f.write(f"Group: {group_name}\n")
        f.write(f"Brain: {result_data['brain']}\n")
        f.write(f"Intent: {result_data['intent']}\n")
        f.write(f"Response: {result_data['speak_text']}\n")
        f.write(f"Audio: {result_data['has_audio']} ({result_data['audio_bytes']} bytes)\n")
        f.write(f"State Flow: {' -> '.join(result_data['state_flow'])}\n")
        f.write(f"Duration: {duration:.2f}s\n")
        if result_data["errors"]:
            f.write(f"Errors: {', '.join(result_data['errors'])}\n")
        f.write("-" * 40 + "\n")
        
    return result_data


async def run_manual_gate():
    print("=" * 60)
    print("      FRIDAY REAL WEBSOCKET MANUAL VALIDATION GATE")
    print("=" * 60)
    
    try:
        async with websockets.connect(WS_URL) as ws:
            print(f"[CONNECTED] Established raw WebSocket connection to: {WS_URL}")
            
            # CRITICAL ENHANCEMENT: Turn mic OFF to disable PortAudio background stream,
            # calibration latency, and blocking audio threads during verification
            print("[CONFIG] Disabling background mic listener to free PortAudio stream thread...")
            await ws.send(json.dumps({"type": "mic_off"}))
            await asyncio.sleep(0.5)
            
            total_cases = 0
            passed_cases = 0
            failed_cases = 0
            
            report = {}
            
            for group_name, queries in TEST_GROUPS.items():
                print(f"\n{'='*50}\nSTARTING: {group_name}\n{'='*50}")
                report[group_name] = []
                
                for q in queries:
                    total_cases += 1
                    res = await run_single_query(ws, q, group_name)
                    
                    # Determine pass/fail
                    is_failed = len(res["errors"]) > 0 or (not res["speak_text"] and res["brain"] in ("LLM", "RETRIEVAL", "MEMORY"))
                    if is_failed:
                        failed_cases += 1
                        print(f"  -> [FAILED] Errors: {res['errors']}")
                    else:
                        passed_cases += 1
                        print(f"  -> [PASSED] ({res['duration']:.2f}s)")
                        
                    report[group_name].append({
                        "query": q,
                        "passed": not is_failed,
                        "brain": res["brain"],
                        "intent": res["intent"],
                        "response": res["speak_text"],
                        "errors": res["errors"]
                    })
                    
                    # Yield event loop thread processing
                    await asyncio.sleep(0.3)
                    
            # ── Compiled manual validation report ─────────────────────────────
            print("\n" + "=" * 60)
            print("        MANUAL VALIDATION GATE REPORT")
            print("=" * 60)
            print(f"  Total tests executed : {total_cases}")
            print(f"  Passed               : {passed_cases}")
            print(f"  Failed               : {failed_cases}")
            print("=" * 60)
            
            # Print detailed stats per group
            print("\n  GROUP DETAILED BREAKDOWN:")
            for group, cases in report.items():
                grp_passed = sum(1 for c in cases if c["passed"])
                grp_total = len(cases)
                print(f"    - {group}: {grp_passed}/{grp_total} passed")
                
            print(f"\nFull raw validation logs saved to: {os.path.abspath(LOG_FILE)}")
            print("=" * 60)
            
            if failed_cases > 0:
                sys.exit(1)
            else:
                sys.exit(0)
                
    except Exception as e:
        print(f"[FATAL GATE ERROR] Failed to connect or execute manual gate: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_manual_gate())
