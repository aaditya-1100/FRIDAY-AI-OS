import asyncio
import json
import sys
import time
import os
import websockets

WS_URL = "ws://127.0.0.1:8001/api/ws"
LOG_FILE = "backend/logs/conversation_stress_validation.log"

os.makedirs("backend/logs", exist_ok=True)

PHASE_QUERIES = {
    "Phase 1 — Long Voice Stability": [
        "Explain quantum mechanics in detail.",
        "Explain black holes in detail.",
        "Compare IIT and NIT CSE in detail.",
        "Tell the complete story of Iron Man.",
        "Explain the latest major AI developments."
    ],
    "Phase 2 — Fresh Retrieval": [
        "Who is the current Prime Minister of the UK?",
        "Who is the current Prime Minister of India?",
        "Latest OpenAI news.",
        "Bitcoin price.",
        "Weather in Delhi."
    ],
    "Phase 3 — Follow-Up Continuity": [
        "Latest AI news.",
        "Tell me more.",
        "Why is that important?",
        "Weather in Delhi.",
        "What about tomorrow?",
        "Tell me about Elon Musk.",
        "How old is he?",
        "What companies does he own?"
    ],
    "Phase 4 — Pronoun Resolution": [
        "Tell me about Tesla.",
        "Who owns it?",
        "Where is it headquartered?",
        "Tell me about SpaceX.",
        "Who founded it?",
        "What rockets does it use?"
    ],
    "Phase 5 — Conversation Continuity": [
        "What is quantum computing?",
        "How does it compare with classical computing?",
        "Who is leading in quantum hardware?",
        "What are NVIDIA's latest GPU announcements?",
        "What is the price of Nvidia stock?",
        "Is SpaceX launching any rockets this week?"
    ],
    "Phase 6 — Voice + Retrieval Stress": [
        "Latest AI news.",
        "Tell me more about the second item.",
        "Explain it in detail."
    ]
}

# Reset raw validation log file
with open(LOG_FILE, "w", encoding="utf-8") as f:
    f.write("=== FRIDAY CONVERSATION STRESS & STABILITY VALIDATION LOG ===\n\n")


async def run_single_query(ws, query: str, phase_name: str) -> dict:
    """Send command via WebSocket, collect and analyze live responses."""
    print(f"\n[{phase_name}] Query: \"{query}\"")
    
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
        "state_flow": [],
        "errors": []
    }
    
    start_time = time.time()
    # Dynamic timeouts: 45s for long explanations, 30s for general
    timeout = 45.0 if "detail" in query.lower() or "story" in query.lower() or "history" in query.lower() else 30.0
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
                
    except Exception as e:
        result_data["errors"].append(str(e))
        
    duration = time.time() - start_time
    result_data["duration"] = duration
    
    # Write details to log file
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"Query: \"{query}\"\n")
        f.write(f"Phase: {phase_name}\n")
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


async def run_stress_validation():
    print("=" * 60)
    print("   FRIDAY CONVERSATION STRESS & STABILITY VALIDATOR")
    print("=" * 60)
    
    try:
        async with websockets.connect(WS_URL) as ws:
            print(f"[CONNECTED] Established raw WebSocket connection to: {WS_URL}")
            
            # Disable microphone stream context
            await ws.send(json.dumps({"type": "mic_off"}))
            await asyncio.sleep(0.5)
            
            total_cases = 0
            passed_cases = 0
            failed_cases = 0
            
            report = {}
            
            for phase_name, queries in PHASE_QUERIES.items():
                print(f"\n{'='*50}\nSTARTING: {phase_name}\n{'='*50}")
                report[phase_name] = []
                
                for q in queries:
                    total_cases += 1
                    res = await run_single_query(ws, q, phase_name)
                    
                    is_failed = len(res["errors"]) > 0 or (not res["speak_text"] and res["brain"] in ("LLM", "RETRIEVAL", "MEMORY"))
                    if is_failed:
                        failed_cases += 1
                        print(f"  -> [FAILED] Errors: {res['errors']}")
                    else:
                        passed_cases += 1
                        print(f"  -> [PASSED] ({res['duration']:.2f}s)")
                        
                    report[phase_name].append({
                        "query": q,
                        "passed": not is_failed,
                        "brain": res["brain"],
                        "intent": res["intent"],
                        "response": res["speak_text"],
                        "errors": res["errors"]
                    })
                    
                    # Yield event loop thread processing (longer gap to avoid TPM rate limits)
                    await asyncio.sleep(1.0)
                    
            print("\n" + "=" * 60)
            print("        STRESS VALIDATION REPORT")
            print("=" * 60)
            print(f"  Total tests executed : {total_cases}")
            print(f"  Passed               : {passed_cases}")
            print(f"  Failed               : {failed_cases}")
            print("=" * 60)
            
            if failed_cases > 0:
                sys.exit(1)
            else:
                sys.exit(0)
                
    except Exception as e:
        print(f"[FATAL STRESS ERROR] Failed to connect or execute stress validation: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_stress_validation())
