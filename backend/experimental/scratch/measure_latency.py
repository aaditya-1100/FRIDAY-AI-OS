import os
import sys
import time
import asyncio
import json


# Ensure backend imports work
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from brain.planner import PlannerBrain
from brain.intent_parser import parse_intent
from brain.context_manager import ContextManager
from memory.preference import PreferenceMemory
from memory.episodic import EpisodicMemory
from execution.action_executor import execute_action
from voice.speak import _run_sapi_tts

planner = PlannerBrain()
context_mgr = ContextManager()
pref_mem = PreferenceMemory()
episodic_mem = EpisodicMemory()

QUERIES = [
    "Explain recursion",
    "Rust vs Python",
    "What project are we working on?"
]

async def measure_query(query: str):
    print(f"\n==========================================")
    print(f"MEASURING LATENCY FOR: \"{query}\"")
    print(f"==========================================")
    
    # 1. Preprocessing and Planner
    t0 = time.perf_counter()
    dec = planner.plan(query, context_mgr, pref_mem, episodic_mem)
    t_plan = (time.perf_counter() - t0) * 1000
    print(f"Planner Routing Time: {t_plan:.2f} ms (Target Brain: {dec.target_brain})")
    
    # 2. Intent Parsing (Groq LLM call)
    t1 = time.perf_counter()
    # Mock parameters representing pipeline context
    intent_data = parse_intent(
        query,
        history=[],
        preferences=pref_mem.preferences,
        semantic_facts={},
        recent_episodes=episodic_mem.events,
        planner_hint=dec.target_brain
    )
    t_intent = (time.perf_counter() - t1) * 1000
    print(f"Intent Parser (Groq API + Sanity Filters) Time: {t_intent:.2f} ms (Intent: {intent_data.get('intent')})")
    
    # 3. Action Execution (excluding speak)
    t2 = time.perf_counter()
    result = await execute_action(intent_data, memory=None)
    t_exec = (time.perf_counter() - t2) * 1000
    print(f"Action Execution Time: {t_exec:.2f} ms")
    
    # Extract text to speak
    speak_text = "Done sir"
    if isinstance(result, dict) and result.get("type") == "ai_response":
        speak_text = result.get("response")
    elif intent_data.get("intent") == "YOUTUBE_TOPIC_SEARCH":
        speak_text = f"Opening search results on YouTube sir"
        
    print(f"Response to Synthesize: \"{speak_text[:60]}...\"")
    
    # 4. TTS SAPI5 Offline Generation
    t3 = time.perf_counter()
    # We save to a temporary file locally
    temp_wav = os.path.join(os.path.dirname(__file__), "temp_latency.wav")
    try:
        _run_sapi_tts(speak_text[:100], temp_wav) # Synthesize first 100 chars to measure init + write
        t_tts = (time.perf_counter() - t3) * 1000
        print(f"TTS Offline SAPI5 Generation Time: {t_tts:.2f} ms")
    except Exception as e:
        t_tts = 0.0
        print(f"TTS Synthesis failed: {e}")
    finally:
        if os.path.exists(temp_wav):
            try:
                os.remove(temp_wav)
            except:
                pass
                
    total = t_plan + t_intent + t_exec + t_tts
    print(f"------------------------------------------")
    print(f"Total Turn Latency (E2E): {total:.2f} ms ({total/1000:.2f} s)")
    print(f"==========================================")
    
    return {
        "query": query,
        "planner": t_plan,
        "intent": t_intent,
        "exec": t_exec,
        "tts": t_tts,
        "total": total
    }

async def main():
    results = []
    for q in QUERIES:
        res = await measure_query(q)
        results.append(res)
        
    # Write to a JSON file
    out_path = os.path.join(os.path.dirname(__file__), "latency_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nAll latency results saved to: {out_path}")

if __name__ == "__main__":
    asyncio.run(main())
