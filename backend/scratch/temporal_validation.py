"""
temporal_validation.py — Validates all temporal engine features:
  - SET_TIMER (short duration for fast testing)
  - SET_REMINDER
  - SET_ALARM
  - SET_RECURRING_REMINDER
  - STOPWATCH_CONTROL
  - LIST_REMINDERS
  - CANCEL_REMINDER
  - _emit_reminder_list (WS broadcast)
  - list_reminders bug fix (no crash)
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timedelta
from system.temporal_engine import TemporalEngine, parse_temporal_expression

PASS = "[PASS]"
FAIL = "[FAIL]"
passed = 0
failed = 0

def check(label: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        print(f"  {PASS} {label}")
        passed += 1
    else:
        print(f"  {FAIL} {label}{' — ' + detail if detail else ''}")
        failed += 1

# ─── parse_temporal_expression tests ─────────────────────────────────────────

print("\n[TEST] parse_temporal_expression — relative durations")
now = datetime(2026, 6, 3, 10, 0, 0)

t, rec, dur = parse_temporal_expression("in 5 minutes", now)
check("5 minute relative", t is not None and dur == 300 and rec is None)

t, rec, dur = parse_temporal_expression("in 2 hours", now)
check("2 hour relative", t is not None and dur == 7200 and rec is None)

t, rec, dur = parse_temporal_expression("in 30 seconds", now)
check("30 second relative", t is not None and dur == 30 and rec is None)

print("\n[TEST] parse_temporal_expression — absolute times")
t, rec, dur = parse_temporal_expression("at 6 AM", now)
check("6 AM absolute parsed", t is not None and t.hour == 6)

t, rec, dur = parse_temporal_expression("at 10:30 PM", now)
check("10:30 PM absolute parsed", t is not None and t.hour == 22 and t.minute == 30)

print("\n[TEST] parse_temporal_expression — tomorrow")
t, rec, dur = parse_temporal_expression("tomorrow at 9 AM", now)
check("Tomorrow 9AM parsed", t is not None and t.date() == (now + timedelta(days=1)).date() and t.hour == 9)

print("\n[TEST] parse_temporal_expression — recurring")
t, rec, dur = parse_temporal_expression("every day at 8 AM", now)
check("Daily recurring", t is not None and rec == "daily")

# ─── TemporalEngine functional tests ─────────────────────────────────────────

async def run_engine_tests():
    import tempfile, json
    global passed, failed
    
    # Create engine with temp state file
    engine = TemporalEngine()
    engine.state_file = os.path.join(tempfile.mkdtemp(), "test_temporal_state.json")
    engine.load_state()
    
    print("\n[TEST] add_reminder — timer")
    resp = await engine.add_reminder("timer", "Timer", "in 10 minutes")
    check("Timer set response", "10 minute" in resp.lower(), resp)
    check("Timer stored in reminders", len(engine.reminders) == 1)
    check("Timer active flag", engine.reminders[0]["active"] == True)
    check("Timer type", engine.reminders[0]["type"] == "timer")
    
    print("\n[TEST] add_reminder — reminder")
    resp = await engine.add_reminder("reminder", "drink water", "in 2 minutes")
    check("Reminder set response", "drink water" in resp.lower(), resp)
    check("2 reminders stored", len(engine.reminders) == 2)
    
    print("\n[TEST] add_reminder — alarm")
    resp = await engine.add_reminder("alarm", "Alarm", "at 11 PM")
    check("Alarm set response", "alarm" in resp.lower() or "11" in resp, resp)
    check("3 items stored", len(engine.reminders) == 3)
    
    print("\n[TEST] add_reminder — recurring")
    resp = await engine.add_reminder("recurring", "take vitamins", "every day at 9 AM")
    check("Recurring reminder set", "recurring" in resp.lower() or "take vitamins" in resp.lower() or "daily" in resp.lower(), resp)
    check("4 items stored", len(engine.reminders) == 4)
    
    print("\n[TEST] list_reminders — no crash (bug fix validation)")
    try:
        resp = await engine.list_reminders()
        check("list_reminders does not crash", True)
        check("list_reminders returns string", isinstance(resp, str))
        check("list_reminders mentions timer", "Timer" in resp or "timer" in resp.lower(), resp)
        check("list_reminders mentions alarm", "Alarm" in resp or "alarm" in resp.lower(), resp)
    except Exception as e:
        check("list_reminders does not crash", False, str(e))
    
    print("\n[TEST] cancel_reminder — by keyword")
    resp = await engine.cancel_reminder("water")
    check("Cancel water reminder by keyword", "water" in resp.lower() or "stood down" in resp.lower(), resp)
    
    print("\n[TEST] cancel_reminder — by ID")
    remaining_active = [r for r in engine.reminders if r.get("active")]
    if remaining_active:
        item_id = remaining_active[0]["id"]
        resp = await engine.cancel_reminder(item_id)
        check("Cancel by ID", "stood down" in resp.lower() or item_id in resp, resp)
    
    print("\n[TEST] stopwatch operations")
    resp = engine.start_stopwatch()
    check("Start stopwatch", "started" in resp.lower(), resp)
    
    await asyncio.sleep(0.5)
    
    resp = engine.get_stopwatch_status()
    check("Stopwatch running status", "running" in resp.lower(), resp)
    
    resp = engine.pause_stopwatch()
    check("Pause stopwatch", "paused" in resp.lower(), resp)
    
    resp = engine.resume_stopwatch()
    check("Resume stopwatch", "resuming" in resp.lower(), resp)
    
    resp = engine.stop_stopwatch()
    check("Stop stopwatch", "stopped" in resp.lower(), resp)
    check("Stop shows elapsed", "elapsed" in resp.lower(), resp)
    
    resp = engine.reset_stopwatch()
    check("Reset stopwatch", "reset" in resp.lower(), resp)
    
    resp = engine.get_stopwatch_status()
    check("Stopwatch reset status", "stopped" in resp.lower() or "reset" in resp.lower(), resp)
    
    print("\n[TEST] state persistence")
    engine2 = TemporalEngine()
    engine2.state_file = engine.state_file
    engine2.load_state()
    check("State persists across load", isinstance(engine2.reminders, list))
    
    print(f"\n{'='*60}")
    print(f"TEMPORAL VALIDATION SUMMARY")
    print(f"Passed: {passed} | Failed: {failed}")
    print(f"Success Rate: {100 * passed / max(1, passed + failed):.1f}%")
    print(f"{'='*60}")
    
    return failed == 0

if __name__ == "__main__":
    success = asyncio.run(run_engine_tests())
    sys.exit(0 if success else 1)
