"""
scratch/semantic_rehearsal.py — Robust Semantic Stress Rehearsal Testing Suite.
Validates strict domain isolation, deterministic routing, and zero routing contamination.
"""
import sys
import os

# Ensure backend is in PATH
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain.semantic_routing import SemanticRoutingEngine
from brain.intent_parser import parse_intent

def run_rehearsal_suite():
    print("======================================================================")
    print("             FRIDAY SEMANTIC REHEARSAL & ISOLATION SUITE              ")
    print("======================================================================")

    router = SemanticRoutingEngine()

    # ── Test Scenarios Definition ──────────────────────────────────────────
    scenarios = [
        # Domain 1: Creator & Identity Grounding (Memory - No-Escalation Zone)
        {"query": "who is Aaditya?", "expected_brain": "MEMORY", "no_triggers": ["VISION", "RETRIEVAL"]},
        {"query": "what do you know about me?", "expected_brain": "MEMORY", "no_triggers": ["VISION", "RETRIEVAL"]},
        {"query": "who created you?", "expected_brain": "MEMORY", "no_triggers": ["VISION", "RETRIEVAL"]},
        {"query": "what kind of music do i like?", "expected_brain": "MEMORY", "no_triggers": ["VISION", "RETRIEVAL"]},
        
        # Domain 2: Explicit Visual Cognition (Vision)
        {"query": "what's on my screen?", "expected_brain": "VISION", "no_triggers": []},
        {"query": "explain this physics derivation on screen", "expected_brain": "VISION", "no_triggers": []},
        {"query": "solve this graph diagram", "expected_brain": "VISION", "no_triggers": []},

        # Domain 3: Geospatial / Routes (Maps)
        {"query": "show route from Hapur to Moradabad", "expected_brain": "MAPS", "no_triggers": []},
        {"query": "celsius weather and cafes near me", "expected_brain": "MAPS", "no_triggers": []},

        # Domain 4: Live Web Retrieval
        {"query": "what is today's breaking news?", "expected_brain": "RETRIEVAL", "no_triggers": []},
        {"query": "Sensex Nifty current trading status", "expected_brain": "RETRIEVAL", "no_triggers": []},
    ]

    failed = 0

    for idx, sc in enumerate(scenarios, start=1):
        q = sc["query"]
        best_brain, confidence = router.classify(q)
        print(f"[TEST {idx}] Query: '{q}'")
        print(f"         Routed: {best_brain} | Conf: {confidence:.2f}")

        # Assert correct brain routing
        if best_brain != sc["expected_brain"]:
            print(f"  [FAIL] Expected target brain '{sc['expected_brain']}', got '{best_brain}'")
            failed += 1
            continue

        # Assert no forbidden domain triggers are present
        forbidden_triggered = [t for t in sc["no_triggers"] if t == best_brain]
        if forbidden_triggered:
            print(f"  [FAIL] Triggered forbidden escalation zones: {forbidden_triggered}")
            failed += 1
            continue

        # Verify parsed intent sanity constraints
        parsed = parse_intent(q)
        intent = parsed.get("intent")
        print(f"         Resolved Intent: {intent}")
        
        if sc["expected_brain"] == "MEMORY" and intent == "SCREEN_UNDERSTANDING":
            print(f"  [FAIL] Identity query resolved to SCREEN_UNDERSTANDING!")
            failed += 1
            continue
            
        print("  [PASS] Domain isolated securely.")
        print("-" * 50)

    print("======================================================================")
    if failed == 0:
        print("     REHEARSAL STATUS: 100% SECURE & GREEN (ALL TESTS PASSED)         ")
    else:
        print(f"     REHEARSAL STATUS: FAILED ({failed} test failures detected)      ")
    print("======================================================================")
    return failed == 0

if __name__ == "__main__":
    success = run_rehearsal_suite()
    sys.exit(0 if success else 1)
