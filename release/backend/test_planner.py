"""Quick validation for brain.planner module."""
import sys
sys.path.insert(0, ".")

from brain.planner import PlannerBrain, PlannerDecision

planner = PlannerBrain()
passed = 0
total = 0


def check(label, condition, detail=""):
    global passed, total
    total += 1
    if condition:
        passed += 1
        print(f"  PASS  {label}  {detail}")
    else:
        print(f"  FAIL  {label}  {detail}")


# 1 - Import
check("Import", True, "PlannerBrain and PlannerDecision imported")

# 2 - Dataclass defaults
d = PlannerDecision()
check("Defaults", d.target_brain == "LLM" and d.priority == "NORMAL" and d.freshness_signals == [])

# 3 - NATIVE_OS routing
r = planner.plan("open notepad")
check("NATIVE_OS", r.target_brain == "NATIVE_OS", f"got {r.target_brain}")

# 4 - RETRIEVAL routing
r = planner.plan("what is the latest news on AI?")
check("RETRIEVAL", r.target_brain == "RETRIEVAL" and r.requires_freshness, f"got {r.target_brain}, fresh={r.requires_freshness}")

# 5 - MEDIA routing
r = planner.plan("play some lofi music")
check("MEDIA", r.target_brain == "MEDIA", f"got {r.target_brain}")

# 6 - BROWSER URL
r = planner.plan("go to https://github.com")
check("BROWSER_URL", r.target_brain == "BROWSER", f"got {r.target_brain}")

# 7 - BROWSER domain
r = planner.plan("check out stackoverflow.com for answers")
check("BROWSER_DOMAIN", r.target_brain == "BROWSER", f"got {r.target_brain}")

# 8 - Ambiguity bare command
r = planner.plan("open")
check("AMBIGUITY", r.requires_clarification is True, f"clarify={r.requires_clarification}")

# 9 - Multi-task
r = planner.plan("open notepad and then check the weather")
check("MULTI_TASK", r.is_multi_task is True, f"multi={r.is_multi_task}")

# 10 - Empty query
r = planner.plan("")
check("EMPTY_QUERY", r.requires_clarification and r.priority == "LOW")

# 11 - MEMORY
r = planner.plan("do it again")
check("MEMORY", r.target_brain == "MEMORY", f"got {r.target_brain}")

# 12 - LLM fallback
r = planner.plan("explain how photosynthesis works")
check("LLM", r.target_brain == "LLM", f"got {r.target_brain}")

# 13 - Priority HIGH for freshness
r = planner.plan("latest bitcoin price")
check("PRIORITY_HIGH", r.priority == "HIGH", f"got {r.priority}")

# 14 - Priority HIGH for NATIVE_OS
r = planner.plan("take screenshot")
check("PRIORITY_NATIVE", r.priority == "HIGH" and r.target_brain == "NATIVE_OS", f"brain={r.target_brain}, prio={r.priority}")

# 15 - Freshness signals populated
r = planner.plan("what is the current temperature forecast for today")
check("SIGNALS", len(r.freshness_signals) >= 2, f"signals={r.freshness_signals}")

# 16 - Weather RETRIEVAL
r = planner.plan("will it rain tomorrow")
check("WEATHER", r.target_brain == "RETRIEVAL", f"got {r.target_brain}")

# 17 - System status NATIVE_OS
r = planner.plan("show me cpu usage")
check("SYS_STATUS", r.target_brain == "NATIVE_OS", f"got {r.target_brain}")

# 18 - Browse to website
r = planner.plan("browse to the website")
check("BROWSE_KW", r.target_brain == "BROWSER", f"got {r.target_brain}")

# 19 - Gibberish fallback to LLM
r = planner.plan("asdfghjkl qwerty zxcvbn")
check("GIBBERISH", r.target_brain == "LLM", f"got {r.target_brain}")

# 20 - Whitespace-only
r = planner.plan("   ")
check("WHITESPACE", r.requires_clarification is True)

print()
print("=" * 50)
print(f"Results: {passed}/{total} passed")
if passed == total:
    print("ALL TESTS PASSED")
else:
    print(f"FAILURES: {total - passed}")
print("=" * 50)
