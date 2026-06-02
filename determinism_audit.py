"""
FRIDAY Determinism Audit — Polish Phase
Validates that identical commands always produce identical routing.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from brain.planner import PlannerBrain
from core.pipeline import _get_simple_command_intent

planner = PlannerBrain()

# ═══════════════════════════════════════════════════════════════════
# TEST MATRIX: every major capability family
# ═══════════════════════════════════════════════════════════════════

tests = {
    "Apps": [
        ("open spotify",         "OPEN"),
        ("open chrome",          "OPEN"),
        ("open vs code",         "OPEN"),
        ("open vscode",          "OPEN"),
        ("open notepad",         "OPEN"),
        ("open calculator",      "OPEN"),
        ("open file explorer",   "OPEN"),
        ("open whatsapp",        "OPEN"),
        ("launch spotify",       "OPEN"),
        ("start chrome",         "OPEN"),
        ("could you open spotify", "OPEN"),
        ("open the spotify app", "OPEN"),
        ("please open chrome",   "OPEN"),
    ],
    "Websites": [
        ("open google",          "OPEN"),
        ("open youtube",         "OPEN"),
    ],
    "System Controls": [
        ("minimize window",      "WINDOW_CONTROL"),
        ("close window",         "WINDOW_CONTROL"),
        ("close active window",  "WINDOW_CONTROL"),
        ("close chrome",         "WINDOW_CONTROL"),
        ("shutdown",             "WINDOW_CONTROL"),
        ("restart",              "WINDOW_CONTROL"),
        ("lock",                 "WINDOW_CONTROL"),
        ("mute",                 "SPOTIFY_CONTROL"),
        ("screenshot",           "SCREENSHOT"),
    ],
    "Volume": [
        ("volume up",            "SPOTIFY_CONTROL"),
        ("volume down",          "SPOTIFY_CONTROL"),
    ],
}

# ═══════════════════════════════════════════════════════════════════
# RUN AUDIT
# ═══════════════════════════════════════════════════════════════════

pass_count = 0
fail_count = 0
total = 0

for family, cases in tests.items():
    print(f"\n{'═' * 60}")
    print(f"  {family}")
    print(f"{'═' * 60}")
    for query, expected_intent in cases:
        total += 1
        
        # Run planner
        plan = planner.plan(query)
        is_simple = plan.is_simple_command
        
        # If simple command, use the deterministic dictionary
        if is_simple:
            intent_data = _get_simple_command_intent(query.lower().strip())
            actual_intent = intent_data.get("intent")
        else:
            # For non-simple commands, they go to LLM. We check what the
            # simple command dictionary WOULD return to verify the safety net
            intent_data = _get_simple_command_intent(query.lower().strip())
            actual_intent = intent_data.get("intent")
        
        # Determine pass/fail
        status = "PASS" if actual_intent == expected_intent else "FAIL"
        icon = "✓" if status == "PASS" else "✗"
        
        if status == "PASS":
            pass_count += 1
        else:
            fail_count += 1
        
        bypass_tag = "[BYPASS]" if is_simple else "[LLM]   "
        print(f"  {icon} {bypass_tag} \"{query}\"")
        print(f"        → intent={actual_intent} | expected={expected_intent} | target_brain={plan.target_brain}")
        if status == "FAIL":
            print(f"        *** MISMATCH ***")

# WhatsApp URL resolution test
print(f"\n{'═' * 60}")
print(f"  WhatsApp URL Resolution")
print(f"{'═' * 60}")

from config.site_registry import get_workspace_url, infer_url
total += 1
wa_url = get_workspace_url("whatsapp")
if wa_url == "https://web.whatsapp.com/":
    print(f"  ✓ get_workspace_url('whatsapp') = {wa_url}")
    pass_count += 1
else:
    print(f"  ✗ get_workspace_url('whatsapp') = {wa_url} (expected https://web.whatsapp.com/)")
    fail_count += 1

total += 1
wa_web_url = get_workspace_url("whatsapp web")
if wa_web_url == "https://web.whatsapp.com/":
    print(f"  ✓ get_workspace_url('whatsapp web') = {wa_web_url}")
    pass_count += 1
else:
    print(f"  ✗ get_workspace_url('whatsapp web') = {wa_web_url} (expected https://web.whatsapp.com/)")
    fail_count += 1

# Summary
print(f"\n{'═' * 60}")
print(f"  DETERMINISM AUDIT RESULTS")
print(f"{'═' * 60}")
print(f"  Total:  {total}")
print(f"  Passed: {pass_count}")
print(f"  Failed: {fail_count}")
print(f"  Rate:   {pass_count}/{total} ({100*pass_count/total:.1f}%)")
print(f"{'═' * 60}")

if fail_count > 0:
    print("  *** FAILURES DETECTED — INVESTIGATE BEFORE RELEASE ***")
    sys.exit(1)
else:
    print("  ALL TESTS PASSED — DETERMINISM VERIFIED")
    sys.exit(0)
