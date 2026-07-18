import os
import sys
import time
import asyncio
from datetime import datetime

# ─── LOAD ENVIRONMENT VARIABLES ──────────────────────────────────────────────
base_dir = r"c:\FRIDAY"
sys.path.insert(0, os.path.join(base_dir, "backend"))

env_path = os.path.join(base_dir, ".env")
if os.path.exists(env_path):
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k not in os.environ:
                    os.environ[k] = v

# Ensure standard environment loads
from brain.planner import PlannerBrain
from brain.intent_parser import parse_intent
from brain.context_manager import ContextManager
from system.retrieval_utils import rewrite_query, rank_and_filter, verify_results
from system.live_data import realtime_web_query
from execution.action_executor import execute_action
from llm.groq_client import ask_groq, DEFAULT_SYSTEM_PROMPT

async def verify_retrieval_architecture():
    print("======================================================================")
    print("      FRIDAY PACKAGED-RUNTIME ARCHITECTURE REAL STRESS TEST")
    print("======================================================================")
    print(f"Current System Time: {datetime.now().strftime('%A, %b %d, %Y at %I:%M %p')}\n")

    planner = PlannerBrain()
    ctx_mgr = ContextManager()

    # ------------------------------------------------------------------------
    # 1. TEST CASE: Latest Video Freshness & Numeric Freshness Routing
    # ------------------------------------------------------------------------
    print("[TEST 1] Latest Video Freshness & Freshness Scoring")
    query = "latest upload of mkbhd"
    decision = planner.plan(query, ctx_mgr)
    print(f"  * Planner Target Brain: {decision.target_brain} (Expected: RETRIEVAL)")
    print(f"  * Planner Freshness Score: {decision.freshness_score:.1f} (Expected: 10.0)")
    print(f"  * Planner Requires Freshness: {decision.requires_freshness} (Expected: True)")
    
    rewritten = rewrite_query(query)
    print(f"  * Rewriter Output: {rewritten} (Expected: universal search queries, no creator stripping)")
    
    print("  * Running LIVE Parallel Search Synthesis (Tavily/Serper)...")
    t0 = time.perf_counter()
    summary = realtime_web_query(query)
    print(f"  * Live Retrieval Latency: {(time.perf_counter() - t0)*1000:.1f}ms")
    print(f"  * Synthesized Voice Response: {summary!r}")
    print("----------------------------------------------------------------------\n")

    # ------------------------------------------------------------------------
    # 2. TEST CASE: Stale Weather Prevention & Context Enrichment
    # ------------------------------------------------------------------------
    print("[TEST 2] Stale Weather Prevention & Default City Enrichment")
    # Simulate a bare weather query without location
    decision = planner.plan("what is the weather", ctx_mgr)
    print(f"  * Planner Target Brain: {decision.target_brain} (Expected: RETRIEVAL)")
    print(f"  * Enriched Query: {decision.enriched_query!r} (Expected to contain 'in Kashipur, Uttarakhand, India')")
    
    t0 = time.perf_counter()
    weather_summary = realtime_web_query(decision.enriched_query)
    print(f"  * Live Weather Latency: {(time.perf_counter() - t0)*1000:.1f}ms")
    print(f"  * Weather Voice Response: {weather_summary!r}")
    print("----------------------------------------------------------------------\n")

    # ------------------------------------------------------------------------
    # 3. TEST CASE: Pronoun & Context Continuity
    # ------------------------------------------------------------------------
    print("[TEST 3] Pronoun & Context Continuity")
    # Simulate history: User asked "who is the current PM of UK?" and assistant responded.
    simulated_history = [
        {"role": "user", "content": "who is the current PM of UK?"},
        {"role": "assistant", "content": "The Prime Minister of the United Kingdom is Keir Starmer, sir."}
    ]
    
    # User follows up: "how old is he?"
    followup = "how old is he?"
    print(f"  * Raw User Follow-up: {followup!r}")
    
    # Feed to parse_intent with simulated history to test LLM-driven pronoun rewrite
    t0 = time.perf_counter()
    parsed_intent = parse_intent(followup, simulated_history)
    print(f"  * Intent Parser Latency: {(time.perf_counter() - t0)*1000:.1f}ms")
    print(f"  * Parsed Intent: {parsed_intent.get('intent')} (Expected: REALTIME_QUERY)")
    print(f"  * Rewritten Contextual Query: {parsed_intent.get('query')!r} (Expected: 'how old is Keir Starmer')")
    print("----------------------------------------------------------------------\n")

    # ------------------------------------------------------------------------
    # 4. TEST CASE: Multi-Query Orchestration & Conjunction Decomposition
    # ------------------------------------------------------------------------
    print("[TEST 4] Multi-Query Orchestration")
    multi_query = "what is the weather in Delhi and latest news on AI"
    decision = planner.plan(multi_query, ctx_mgr)
    print(f"  * Planner Multi-task Detection: {decision.is_multi_task} (Expected: True)")
    
    t0 = time.perf_counter()
    parsed_multi = parse_intent(decision.enriched_query)
    print(f"  * Multi-Intent Parser Latency: {(time.perf_counter() - t0)*1000:.1f}ms")
    print(f"  * Decomposed Actions:")
    for a in parsed_multi.get("actions", []):
        print(f"    - {a}")
    print("----------------------------------------------------------------------\n")

    # ------------------------------------------------------------------------
    # 5. TEST CASE: Conversational Presence Latency (<150ms)
    # ------------------------------------------------------------------------
    print("[TEST 5] Conversational Presence Fast-Path Latency")
    presence_checks = ["are you there", "hey friday", "sup"]
    
    from core.pipeline import _PRESENCE_PATTERNS, _PRESENCE_REPLIES
    import random
    
    for check in presence_checks:
        t0 = time.perf_counter()
        # strip casing and ending symbols to match pipeline logic
        q_match = check.rstrip("?!. ").lower()
        is_presence = q_match in _PRESENCE_PATTERNS
        reply = random.choice(_PRESENCE_REPLIES) if is_presence else None
        latency = (time.perf_counter() - t0)*1000
        print(f"  * Presence query: {check!r} | Latency: {latency:.4f}ms | Reply: {reply!r}")
        
    print("----------------------------------------------------------------------\n")

    # ------------------------------------------------------------------------
    # 6. TEST CASE: Conversational Humanization & Emotional Awareness
    # ------------------------------------------------------------------------
    print("[TEST 6] Conversational Humanization & Emotional Awareness")
    emotional_query = "I had a really long day today"
    print(f"  * User: {emotional_query!r}")
    t0 = time.perf_counter()
    response = ask_groq(emotional_query, system_prompt=DEFAULT_SYSTEM_PROMPT)
    latency = (time.perf_counter() - t0)*1000
    print(f"  * Jarvis Response Latency: {latency:.1f}ms")
    print(f"  * Jarvis Reply: {response!r}")
    print("----------------------------------------------------------------------\n")

    # ------------------------------------------------------------------------
    # 7. TEST CASE: Concurrent Temporal System Controls
    # ------------------------------------------------------------------------
    print("[TEST 7] Concurrent Temporal System Controls")
    stopwatch_queries = [
        "start stopwatch",
        "show stopwatch",
        "stop stopwatch"
    ]
    for sq in stopwatch_queries:
        print(f"  * User Command: {sq!r}")
        t0 = time.perf_counter()
        parsed_sw = parse_intent(sq)
        print(f"    - Parsed Intent: {parsed_sw.get('intent')} | Command: {parsed_sw.get('command')}")
        # Run action executor synchronously to check state
        res = await execute_action(parsed_sw)
        latency = (time.perf_counter() - t0)*1000
        print(f"    - Execution Output: {res.get('response') or res.get('speak') or res.get('text')!r} | Latency: {latency:.1f}ms")

    # ------------------------------------------------------------------------
    # 8. TEST CASE: Dynamic Conversational Pause Thresholds & Vocal Pacing Heuristics
    # ------------------------------------------------------------------------
    print("[TEST 8] Dynamic Conversational Pause Thresholds & Vocal Pacing Heuristics")
    from core.state_manager import set_conversational_state, AssistantState
    from voice.listen import get_open_microphone, _adaptive_listen, USE_ADAPTIVE_LISTENING
    
    print(f"  * USE_ADAPTIVE_LISTENING global flag: {USE_ADAPTIVE_LISTENING}")
    assert USE_ADAPTIVE_LISTENING is True
    
    # Safe test for persistent microphone initialization
    try:
        print("  * Resolving persistent microphone...")
        mic = get_open_microphone()
        print(f"    - Persistent microphone stream resolved: {mic.device_index}")
    except Exception as e_mic:
        print(f"    - [WARN] Local microphone not openable/available in test environment: {e_mic}")

    # Mock testing the adaptive pacing logic of _adaptive_listen
    class MockStream:
        def __init__(self, energy_sequence, chunk_size=512):
            self.energy_sequence = list(energy_sequence)
            self.chunk_size = chunk_size
            self.index = 0
            
        def read(self, num_bytes):
            if self.index >= len(self.energy_sequence):
                return b""
            # Generate synthetic PCM-16 mono buffer matching the desired energy
            energy = self.energy_sequence[self.index]
            self.index += 1
            # 512 samples of PCM-16 is 1024 bytes (SAMPLE_WIDTH = 2)
            val = int(energy)
            import struct
            try:
                return struct.pack("<512h", *[val]*512)
            except Exception:
                return b"\x00" * 1024

    class MockSource:
        def __init__(self, energy_sequence):
            self.CHUNK = 512
            self.SAMPLE_RATE = 16000
            self.SAMPLE_WIDTH = 2
            self.stream = MockStream(energy_sequence)

    from voice.listen import _get_recognizer
    recognizer = _get_recognizer()
    recognizer.energy_threshold = 300
    recognizer.dynamic_energy_threshold = False
    
    # Scenario A: Short initial phrase (vocal burst of 0.3s -> ~10 chunks at 16kHz/512) followed by silence.
    # Expected: should extend pause threshold to max(base, 2.0s) -> 2.0s (~62 chunks)
    print("  * Scenario A: Short initial hesitation (vocal burst then silence)")
    # 10 chunks high energy (600), then 80 chunks silence (0)
    energy_seq_a = [600] * 10 + [0] * 80
    source_a = MockSource(energy_seq_a)
    
    audio_a = _adaptive_listen(recognizer, source_a, timeout=2.0, state=AssistantState.CASUAL_CHAT)
    print(f"    - Completed Scenario A. Chunks read: {source_a.stream.index} (Expected > 50)")
    assert source_a.stream.index > 50, f"Expected to wait longer than 50 chunks, got {source_a.stream.index}"
    
    # Scenario B: Fluent long command (vocal run of 1.6s -> 50 chunks) followed by silence in TASK_MODE.
    # Expected: should use fast command cutoff (0.6s -> ~19 chunks)
    print("  * Scenario B: Fluent long command in TASK_MODE (long run then silence)")
    energy_seq_b = [600] * 50 + [0] * 40
    source_b = MockSource(energy_seq_b)
    
    audio_b = _adaptive_listen(recognizer, source_b, timeout=2.0, state=AssistantState.TASK_MODE)
    print(f"    - Completed Scenario B. Chunks read: {source_b.stream.index} (Expected < 75)")
    assert source_b.stream.index < 75, f"Expected rapid cutoff, got {source_b.stream.index} chunks"
    
    # Scenario C: Storytelling in CASUAL_CHAT (Halting/continuous conversation)
    # Expected: should extend pause threshold to 2.3s (~72 chunks) to tolerate thinking gaps
    print("  * Scenario C: Storytelling in CASUAL_CHAT (Continuous flow with thinking gaps)")
    # Vocal run 1 (30 chunks), small gap (10 chunks), vocal run 2 (30 chunks), then 80 chunks silence
    energy_seq_c = [600] * 30 + [0] * 10 + [600] * 30 + [0] * 80
    source_c = MockSource(energy_seq_c)
    
    audio_c = _adaptive_listen(recognizer, source_c, timeout=3.0, state=AssistantState.CASUAL_CHAT)
    print(f"    - Completed Scenario C. Chunks read: {source_c.stream.index} (Expected > 120)")
    assert source_c.stream.index > 120, f"Expected storytelling cushion, got {source_c.stream.index} chunks"
    
    # ------------------------------------------------------------------------
    # 9. TEST CASE: Personal Knowledge, Identity Awareness & Slicing
    # ------------------------------------------------------------------------
    print("[TEST 9] Personal Knowledge, Identity Awareness & Contextual Slicing")
    from brain.identity_manager import IdentityManager
    id_mgr = IdentityManager()
    
    # Check 1: Authoritative profile load
    print("  * Checking authoritative profile configuration...")
    print(f"    - Self Name: {id_mgr.profile['self_identity']['name']} (Expected: FRIDAY)")
    print(f"    - User Name: {id_mgr.profile['user_identity']['name']} (Expected: Aaditya)")
    assert id_mgr.profile['self_identity']['name'] == "FRIDAY"
    assert id_mgr.profile['user_identity']['name'] == "Aaditya"
    
    # Check 2: Contextual Slicing for "Who created you?"
    print("  * Checking slice scope for: 'who created you?'")
    slice_created = id_mgr.get_contextual_slices("who created you?")
    print(f"    - Retrieved Slices: {list(slice_created.keys())} (Expected: self_identity, user_identity)")
    assert "self_identity" in slice_created
    assert "user_identity" in slice_created
    assert "workflow_memory" not in slice_created
    assert "goal_memory" not in slice_created
    
    # Check 3: Contextual Slicing for goals
    print("  * Checking slice scope for: 'what are my goals?'")
    slice_goals = id_mgr.get_contextual_slices("what are my goals?")
    print(f"    - Retrieved Slices: {list(slice_goals.keys())} (Expected: goal_memory, user_identity)")
    assert "goal_memory" in slice_goals
    assert "user_identity" in slice_goals
    assert "self_identity" not in slice_goals
    assert "preference_memory" not in slice_goals

    # Check 4: Contextual Slicing for music
    print("  * Checking slice scope for: 'what music do I like?'")
    slice_music = id_mgr.get_contextual_slices("what music do I like?")
    print(f"    - Retrieved Slices: {list(slice_music.keys())} (Expected: preference_memory)")
    assert "preference_memory" in slice_music
    assert "music" in slice_music["preference_memory"]
    assert "coding" not in slice_music["preference_memory"]
    assert "self_identity" not in slice_music
    
    # Check 5: Run live Groq query on self-identity
    print("  * Querying Groq (llama-3.3-70b-versatile) for Creator Identity:")
    query_created = "who is your creator and who built you?"
    parsed_created = parse_intent(query_created)
    res_created = await execute_action(parsed_created)
    print(f"    - Query: '{query_created}'")
    print(f"    - Jarvis Reply: {res_created.get('response')!r}")
    assert any(w in res_created.get("response").lower() for w in ("aaditya", "you", "sir"))
    
    # Check 5b: Explicitly query for the user's name to verify the name Aaditya is retrieved
    print("  * Querying what is my name:")
    query_name = "what is my name?"
    parsed_name = parse_intent(query_name)
    res_name = await execute_action(parsed_name)
    print(f"    - Query: '{query_name}'")
    print(f"    - Jarvis Reply: {res_name.get('response')!r}")
    assert "aaditya" in res_name.get("response").lower()
    
    # Check 6: Run live weather query (should enrich location Kashipur naturally)
    print("  * Querying weather widget (should lock Kashipur):")
    parsed_weather = parse_intent("how's the weather?")
    res_weather = await execute_action(parsed_weather)
    print(f"    - Response: {res_weather.get('response')!r}")
    
    # Check 7: Self-Referential System Commands
    print("  * Checking voice self-mute action execution...")
    parsed_mute = parse_intent("mute yourself")
    res_mute = await execute_action(parsed_mute)
    print(f"    - Action Response: {res_mute.get('response')!r}")
    assert "muting microphone" in res_mute.get("response").lower()
    
    # Verify that self-referential pronouns are properly enriched in temporal payload
    print("  * Checking temporal self-referential reminder payload resolution...")
    parsed_rem = parse_intent("remind me in 30 sec to turn off you")
    print(f"    - Remind intent: {parsed_rem.get('intent')} | text: {parsed_rem.get('text')!r}")
    assert parsed_rem.get("intent") == "SET_REMINDER"
    assert "friday" in parsed_rem.get("text").lower() or "you" not in parsed_rem.get("text").lower()
    
    # Check 8: Direct Website Open Shortcuts (PW / Physics Wallah)
    print("  * Checking PW / Physics Wallah direct shortcut resolution...")
    parsed_pw = parse_intent("open pw")
    parsed_phys = parse_intent("physics wallah")
    print(f"    - 'open pw' intent: {parsed_pw.get('intent')} | target: {parsed_pw.get('target')!r}")
    print(f"    - 'physics wallah' intent: {parsed_phys.get('intent')} | target: {parsed_phys.get('target')!r}")
    assert parsed_pw.get("intent") == "OPEN"
    assert parsed_pw.get("target") == "pw"
    assert parsed_phys.get("intent") == "OPEN"
    assert parsed_phys.get("target") == "physics wallah"
    
    print("----------------------------------------------------------------------\n")

    print("======================================================================")
    print("            ALL ARCHITECTURAL STRESS TEST CHECKS COMPLETED")
    print("======================================================================")

if __name__ == "__main__":
    asyncio.run(verify_retrieval_architecture())
