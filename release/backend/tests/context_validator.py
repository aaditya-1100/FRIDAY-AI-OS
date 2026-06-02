"""
context_validator.py — Exhaustive 600-Test Validation Suite for FRIDAY.
Validates: Core Context, Pronoun Resolution, Screen Cognition, Maps Brain,
           Contextual Multi-turn, and Mixed/Stress Sessions.
"""

import sys
import os
import time
import re

# Ensure backend root is on path
backend_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(backend_path)

from brain.context_graph import ConversationContextGraph, ContextEntity
from brain.context_manager import ContextManager
from brain.entity_tracker import extract_all_entities, has_reference


# ==============================================================================
# CATEGORY 1: CORE CONTEXT CASES GENERATOR
# ==============================================================================
def run_core_context_tests(log):
    log.write("=== CATEGORY 1: CORE CONTEXT TESTS ===\n")
    graph = ConversationContextGraph(entity_history_size=30)
    passed = 0
    total = 100

    # 1. Entity type registration and retrieval (40 tests)
    entity_types = [
        ("location", "Paris"), ("person", "Elon Musk"), ("app", "Spotify"),
        ("video", "Mark Rober Nerf"), ("website", "github.com"), ("file", "notes.pdf"),
        ("media", "Lofi Beats"), ("topic", "Quantum Gravity"), ("screen", "VS Code Editor"),
        ("route", "Paris to London")
    ]
    for idx, (etype, text) in enumerate(entity_types * 4):
        graph._register(text, etype, confidence=1.0, source="test")
        retrieved = graph.get(etype)
        is_ok = (retrieved == text)
        if is_ok:
            passed += 1
        log.write(f"[CORE] #{idx+1:03d} | Registered {etype}='{text}' | Retrieved: '{retrieved}' | {'PASS' if is_ok else 'FAIL'}\n")

    # 2. Linear confidence decay (20 tests)
    # Testing age/TTL math
    for idx in range(20):
        entity = ContextEntity(text=f"DecayTest{idx}", entity_type="topic", confidence=1.0, ttl_seconds=100.0)
        # Manually alter created_at to simulate aging
        entity.created_at = time.time() - (idx * 5) # 0s to 95s age
        expected_decay = max(0.0, 1.0 - (idx * 5) / 100.0)
        is_ok = abs(entity.effective_confidence - expected_decay) < 0.05
        if is_ok:
            passed += 1
        log.write(f"[CORE] #{idx+41:03d} | Age: {idx*5}s | Expected Conf: {expected_decay:.2f} | Got: {entity.effective_confidence:.2f} | {'PASS' if is_ok else 'FAIL'}\n")

    # 3. get_best() prioritization (20 tests)
    # Registering multiple entities and ensuring higher confidence wins
    for idx in range(20):
        g = ConversationContextGraph(entity_history_size=30)
        # Register a low confidence newer entity and high confidence older entity
        g._register("OldHigh", "location", confidence=1.0)
        g._entities[-1].created_at = time.time() - 10.0 # Age it slightly
        g._register("NewLow", "location", confidence=0.2)
        
        best = g.get_best(["location"])
        is_ok = (best == "OldHigh") # OldHigh has effective_confidence ~0.99 > 0.2
        if is_ok:
            passed += 1
        log.write(f"[CORE] #{idx+61:03d} | get_best Location | Expected: 'OldHigh' | Got: '{best}' | {'PASS' if is_ok else 'FAIL'}\n")

    # 4. TTL expiration pruning (20 tests)
    for idx in range(20):
        g = ConversationContextGraph(entity_history_size=30)
        g._register("FreshItem", "app", confidence=1.0)
        g._register("ExpiredItem", "person", confidence=1.0)
        g._entities[-1].created_at = time.time() - 2000.0 # Exceeds 600s TTL for person
        
        g.prune_expired()
        has_fresh = (g.get("app") == "FreshItem")
        has_expired = (g.get("person") is None)
        is_ok = has_fresh and has_expired
        if is_ok:
            passed += 1
        log.write(f"[CORE] #{idx+81:03d} | Expired person prune | Ok: {is_ok} | {'PASS' if is_ok else 'FAIL'}\n")

    log.write(f"-> CORE CONTEXT RESULT: Passed {passed}/{total} ({passed/total*100:.1f}%)\n\n")
    return passed, total


# ==============================================================================
# CATEGORY 2: PRONOUN RESOLUTION CASES GENERATOR
# ==============================================================================
def run_pronoun_tests(log):
    log.write("=== CATEGORY 2: PRONOUN RESOLUTION TESTS ===\n")
    passed = 0
    total = 100

    pronoun_cases = [
        ("open it", "topic", "Notepad", "open Notepad"),
        ("what is the weather there", "location", "Paris", "what is the weather Paris"),
        ("who is he", "person", "Elon Musk", "who is Elon Musk"),
        ("tell me about her", "person", "Marie Curie", "tell me about Marie Curie"),
        ("zoom in there", "location", "Kashipur", "zoom in Kashipur"),
        ("close the app", "app", "Chrome", "close Chrome"),
        ("what is in the file", "file", "report.pdf", "what is in report.pdf"),
        ("open the website", "website", "wikipedia.org", "open wikipedia.org"),
        ("play the song", "media", "Lofi Track", "play Lofi Track"),
        ("tell me the route", "route", "Kashipur to Delhi", "tell me Kashipur to Delhi")
    ]

    # Run 100 variations (10 base cases * 10 reps)
    for idx in range(100):
        base_case = pronoun_cases[idx % len(pronoun_cases)]
        query, etype, entity_val, expected = base_case
        
        g = ConversationContextGraph()
        g._register(entity_val, etype, confidence=1.0)
        
        resolved = g.resolve(query)
        # Normalize double spaces or minor punctuation
        resolved_norm = re.sub(r'\s+', ' ', resolved).strip()
        expected_norm = re.sub(r'\s+', ' ', expected).strip()
        
        is_ok = (resolved_norm.lower() == expected_norm.lower())
        if is_ok:
            passed += 1
        log.write(f"[PRONOUN] #{idx+1:03d} | Query: '{query}' | Reg: {etype}='{entity_val}' | Resolved: '{resolved_norm}' | {'PASS' if is_ok else 'FAIL'}\n")

    log.write(f"-> PRONOUN RESOLUTION RESULT: Passed {passed}/{total} ({passed/total*100:.1f}%)\n\n")
    return passed, total


# ==============================================================================
# CATEGORY 3: SCREEN COGNITION CASES GENERATOR
# ==============================================================================
def run_screen_tests(log):
    log.write("=== CATEGORY 3: SCREEN COGNITION TESTS ===\n")
    passed = 0
    total = 100

    # 1. Explicit Screen Cognition Triggers (50 tests)
    explicit_queries = [
        "what is on my screen?", "explain what you see on my display",
        "describe my screen context", "explain this derivation visible on screen",
        "what document am I looking at?", "summarize this webpage on my monitor",
        "what code am I writing right now?", "describe this chart on my screen",
        "explain this graph", "what is this equation on the display?",
        "what is shown on my screen", "explain what is visible right here",
        "read what's on the screen", "analyze this diagram", "what's on my display?"
    ]
    g = ConversationContextGraph()
    for idx in range(50):
        q = explicit_queries[idx % len(explicit_queries)]
        is_screen_req = g.is_screen_cognition_request(q)
        if is_screen_req:
            passed += 1
        log.write(f"[SCREEN] #{idx+1:03d} | Trigger: '{q}' | Result: {is_screen_req} | {'PASS' if is_screen_req else 'FAIL'}\n")

    # 2. Screen Cognition Blocklist / Filters (30 tests)
    blocklist_queries = [
        "who am i", "who are you", "what are my goals", "how are you",
        "who is aaditya", "my target JEE score", "what is your name",
        "how is the CPU doing?", "what do you know about me?", "my targets for today",
        "who created friday?", "what is my favorite app?", "how is your system?"
    ]
    for idx in range(30):
        q = blocklist_queries[idx % len(blocklist_queries)]
        is_screen_req = g.is_screen_cognition_request(q)
        is_ok = (is_screen_req is False)
        if is_ok:
            passed += 1
        log.write(f"[SCREEN] #{idx+51:03d} | Blocked: '{q}' | Result: {is_screen_req} | {'PASS' if is_ok else 'FAIL'}\n")

    # 3. Passive active-window detection & snapshots (20 tests)
    manager = ContextManager()
    window_scans = [
        ("main.py - C:\\project - VS Code", "code.exe", "Coding in VS Code"),
        ("Mark Rober Nerf Gun - YouTube - Google Chrome", "chrome.exe", "Watching YouTube"),
        ("JEE 2026 Physics Notes.pdf - Adobe Reader", "acrord32.exe", "Reading PDF"),
        ("Spotify Premium", "spotify.exe", "Listening to Spotify"),
        ("Administrator: Command Prompt", "cmd.exe", "Running terminal commands")
    ]
    for idx in range(20):
        title, proc, expected_match = window_scans[idx % len(window_scans)]
        # Force title + process update passively
        manager._graph.update_passive_window(title, proc)
        snapshot = manager._build_passive_snapshot(title, proc)
        is_ok = (expected_match in snapshot)
        if is_ok:
            passed += 1
        log.write(f"[SCREEN] #{idx+81:03d} | Title: '{title}' | Snapshot: '{snapshot}' | {'PASS' if is_ok else 'FAIL'}\n")

    log.write(f"-> SCREEN COGNITION RESULT: Passed {passed}/{total} ({passed/total*100:.1f}%)\n\n")
    return passed, total


# ==============================================================================
# CATEGORY 4: UNIVERSAL MAPS BRAIN CASES GENERATOR
# ==============================================================================
def run_maps_tests(log):
    log.write("=== CATEGORY 4: UNIVERSAL MAPS BRAIN TESTS ===\n")
    passed = 0
    total = 100

    # Test cases for map follow-ups
    map_cases = [
        ("how long to get there", "eta", {}),
        ("what is the distance?", "distance", {}),
        ("which cities will I pass through?", "cities_crossed", {}),
        ("is there traffic?", "traffic", {}),
        ("show me satellite view", "satellite_view", {}),
        ("switch to street view", "street_view", {}),
        ("zoom out", "zoom_out", {}),
        ("zoom in more", "zoom_in", {}),
        ("find hotels nearby", "nearby_places", {"place_type": "lodging"}),
        ("find gas stations around here", "nearby_places", {"place_type": "gas_station"}),
        ("airports near the route", "nearby_places", {"place_type": "airport"})
    ]

    # 1. Map Session Active (50 tests)
    g = ConversationContextGraph()
    g.update_map_session(
        current_map_location="Delhi",
        route_origin="Kashipur",
        route_destination="Delhi",
        distance="200 km",
        duration="4 hours",
        duration_in_traffic="4.5 hours",
        cities_crossed=["Moradabad", "Hapur", "Ghaziabad"]
    )
    for idx in range(50):
        query, expected_action, expected_extra = map_cases[idx % len(map_cases)]
        is_followup, action, extra = g.detect_map_followup(query)
        is_ok = (is_followup is True and action == expected_action and extra.get("place_type") == expected_extra.get("place_type"))
        if is_ok:
            passed += 1
        log.write(f"[MAPS] #{idx+1:03d} | Active Session | Query: '{query}' | Got Action: '{action}' | {'PASS' if is_ok else 'FAIL'}\n")

    # 2. Map Session Inactive/Empty (50 tests)
    g_empty = ConversationContextGraph()
    for idx in range(50):
        query, _, _ = map_cases[idx % len(map_cases)]
        is_followup, action, _ = g_empty.detect_map_followup(query)
        is_ok = (is_followup is False and action == "")
        if is_ok:
            passed += 1
        log.write(f"[MAPS] #{idx+51:03d} | Inactive Session | Query: '{query}' | Got Followup: {is_followup} | {'PASS' if is_ok else 'FAIL'}\n")

    log.write(f"-> UNIVERSAL MAPS RESULT: Passed {passed}/{total} ({passed/total*100:.1f}%)\n\n")
    return passed, total


# ==============================================================================
# CATEGORY 5: CONTEXTUAL MULTI-TURN CASES GENERATOR
# ==============================================================================
def run_multiturn_tests(log):
    log.write("=== CATEGORY 5: CONTEXTUAL MULTI-TURN TESTS ===\n")
    passed = 0
    total = 100

    # 20 sequential multi-turn sequences (5 turns each = 100 tests total)
    sequences = [
        # Sequence 1: Navigation follow-ups
        [
            ("open map of Paris", "location", "Paris"),
            ("show route to London", "route", "Paris to London"),
            ("how far is it?", "resolved", "how far is Paris to London?"),
            ("which cities will I pass through?", "followup", "cities_crossed"),
            ("zoom in", "followup", "zoom_in")
        ],
        # Sequence 2: Video study session
        [
            ("watch Mark Rober nerf gun video", "video", "Mark Rober nerf gun"),
            ("explain it to me", "resolved", "explain Mark Rober nerf gun to me"),
            ("open VS Code", "app", "VS Code"),
            ("write python code in it", "resolved", "write python code in VS Code"),
            ("close it", "resolved", "close VS Code")
        ]
    ]

    for seq_idx in range(20):
        seq = sequences[seq_idx % len(sequences)]
        g = ConversationContextGraph()
        
        for turn_idx, (query, expected_type, expected_val) in enumerate(seq):
            test_idx = seq_idx * 5 + turn_idx
            
            # Simulated update pipeline
            g.update(query)
            
            is_ok = False
            got_val = ""
            
            if expected_type == "location":
                got_val = g.get("location")
                is_ok = (got_val == expected_val)
            elif expected_type == "video":
                got_val = g.get("video")
                is_ok = (got_val == expected_val)
            elif expected_type == "app":
                got_val = g.get("app")
                is_ok = (got_val == expected_val)
            elif expected_type == "route":
                # Trigger action_executor simulated update
                g.update_map_session(route_origin="Paris", route_destination="London")
                got_val = g.get("route")
                is_ok = (got_val == expected_val)
            elif expected_type == "resolved":
                got_val = g.resolve(query)
                is_ok = (got_val.lower() == expected_val.lower())
            elif expected_type == "followup":
                is_fol, act, _ = g.detect_map_followup(query)
                got_val = act
                is_ok = (is_fol is True and act == expected_val)
                
            if is_ok:
                passed += 1
                
            log.write(f"[MULTITURN] #{test_idx+1:03d} | Turn #{turn_idx+1} | Query: '{query}' | Got: '{got_val}' | {'PASS' if is_ok else 'FAIL'}\n")

    log.write(f"-> MULTI-TURN RESULT: Passed {passed}/{total} ({passed/total*100:.1f}%)\n\n")
    return passed, total


# ==============================================================================
# CATEGORY 6: MIXED/STRESS CASES GENERATOR
# ==============================================================================
def run_stress_tests(log):
    log.write("=== CATEGORY 6: MIXED/STRESS SESSION TESTS ===\n")
    passed = 0
    total = 100

    g = ConversationContextGraph()

    # 1. Empty/Whitespace queries (20 tests)
    for idx in range(20):
        query = "   \n  " * (idx + 1)
        try:
            g.update(query)
            resolved = g.resolve(query)
            is_ok = (resolved == query.strip())
            if is_ok:
                passed += 1
        except Exception as e:
            is_ok = False
        log.write(f"[STRESS] #{idx+1:03d} | Empty query | Resolved: '{resolved}' | {'PASS' if is_ok else 'FAIL'}\n")

    # 2. Concurrent rapid entity registration (20 tests)
    # Registering 50 entities rapidly, ensuring no crash and deque rolling limits work
    for idx in range(20):
        g_rapid = ConversationContextGraph(entity_history_size=30)
        for i in range(50):
            g_rapid._register(f"Entity{i}", "topic")
        # Ensure only 30 elements are retained
        history_len = len(g_rapid._entities)
        is_ok = (history_len == 30)
        if is_ok:
            passed += 1
        log.write(f"[STRESS] #{idx+21:03d} | Rapid Registration | Count: {history_len} | {'PASS' if is_ok else 'FAIL'}\n")

    # 3. Pronoun resolving with completely empty context (20 tests)
    g_empty = ConversationContextGraph()
    queries = ["open it", "close that", "how far is it?", "what is the weather there?", "is he there?"]
    for idx in range(20):
        q = queries[idx % len(queries)]
        resolved = g_empty.resolve(q)
        # Should return original query because no entities exist to replace them
        is_ok = (resolved == q)
        if is_ok:
            passed += 1
        log.write(f"[STRESS] #{idx+41:03d} | Empty Context Pronouns | Query: '{q}' | Resolved: '{resolved}' | {'PASS' if is_ok else 'FAIL'}\n")

    # 4. Latency stress tests (40 tests)
    # Executing operations in a loop and measuring time < 2ms per turn
    for idx in range(40):
        g_latency = ConversationContextGraph()
        g_latency.update_map_session(route_origin="Kashipur", route_destination="Delhi")
        
        t0 = time.perf_counter()
        # Do 10 operations
        for i in range(10):
            g_latency.update(f"query {i} Paris")
            g_latency.resolve("how far is it to Paris")
            g_latency.detect_map_followup("how long does it take")
            
        t1 = time.perf_counter()
        elapsed_ms = (t1 - t0) * 1000
        # 10 iterations * 3 operations = 30 context operations in elapsed_ms
        per_op_ms = elapsed_ms / 30
        is_ok = (per_op_ms < 2.0)
        if is_ok:
            passed += 1
        log.write(f"[STRESS] #{idx+61:03d} | Latency test | Total: {elapsed_ms:.2f}ms | Per Op: {per_op_ms:.3f}ms | {'PASS' if is_ok else 'FAIL'}\n")

    log.write(f"-> STRESS TEST RESULT: Passed {passed}/{total} ({passed/total*100:.1f}%)\n\n")
    return passed, total


# ==============================================================================
# MAIN TEST SUITE RUNNER
# ==============================================================================
def run_test_suite():
    print("=" * 60)
    print("FRIDAY CONTEXT & MAPS INTEL VALIDATION TEST SUITE RUNNER")
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    log_dir = os.path.join(backend_path, "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "context_test_results.log")

    total_passed = 0
    total_cases = 0

    with open(log_path, "w", encoding="utf-8") as log_file:
        log_file.write("=" * 70 + "\n")
        log_file.write(f"FRIDAY 600-TEST CONTEXT & MAPS VALIDATION LOG — {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        log_file.write("=" * 70 + "\n\n")

        # Category 1
        print("Running 1. CORE CONTEXT TESTS (Count: 100)...")
        p, t = run_core_context_tests(log_file)
        total_passed += p
        total_cases += t
        print(f"      -> Passed: {p}/{t} ({p/t*100:.1f}%)")

        # Category 2
        print("Running 2. PRONOUN RESOLUTION TESTS (Count: 100)...")
        p, t = run_pronoun_tests(log_file)
        total_passed += p
        total_cases += t
        print(f"      -> Passed: {p}/{t} ({p/t*100:.1f}%)")

        # Category 3
        print("Running 3. SCREEN COGNITION TESTS (Count: 100)...")
        p, t = run_screen_tests(log_file)
        total_passed += p
        total_cases += t
        print(f"      -> Passed: {p}/{t} ({p/t*100:.1f}%)")

        # Category 4
        print("Running 4. UNIVERSAL MAPS TESTS (Count: 100)...")
        p, t = run_maps_tests(log_file)
        total_passed += p
        total_cases += t
        print(f"      -> Passed: {p}/{t} ({p/t*100:.1f}%)")

        # Category 5
        print("Running 5. CONTEXTUAL MULTI-TURN TESTS (Count: 100)...")
        p, t = run_multiturn_tests(log_file)
        total_passed += p
        total_cases += t
        print(f"      -> Passed: {p}/{t} ({p/t*100:.1f}%)")

        # Category 6
        print("Running 6. MIXED/STRESS SESSION TESTS (Count: 100)...")
        p, t = run_stress_tests(log_file)
        total_passed += p
        total_cases += t
        print(f"      -> Passed: {p}/{t} ({p/t*100:.1f}%)")

        overall_rate = (total_passed / total_cases) * 100
        print("=" * 60)
        print(f"OVERALL SUMMARY: Passed {total_passed}/{total_cases} ({overall_rate:.1f}%)")
        print(f"Full log written to: {log_path}")
        print("=" * 60)

        log_file.write("=" * 70 + "\n")
        log_file.write(f"OVERALL VALIDATION SUMMARY: Passed {total_passed}/{total_cases} ({overall_rate:.1f}%)\n")
        log_file.write("=" * 70 + "\n")


if __name__ == "__main__":
    run_test_suite()
