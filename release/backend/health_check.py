import os
import sys
from datetime import datetime

base_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, base_dir)

print("======================================================================")
print("             FRIDAY BACKEND SYSTEM COMPREHENSIVE HEALTH CHECK")
print("======================================================================")
print(f"Timestamp: {datetime.now().isoformat()}")
print(f"Working Directory: {base_dir}")
print(f"Python Version: {sys.version}\n")

print("[STEP 1] ENVIRONMENT VARIABLES & SECRETS CONFIGURATION")
env_path = os.path.join(base_dir, ".env")
has_env = os.path.exists(env_path)
print(f"  * .env file exists: {has_env} ({env_path})")

if has_env:
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k not in os.environ:
                    os.environ[k] = v

essential_keys = ["GROQ_API_KEY", "TAVILY_API_KEY", "SERPER_API_KEY"]
for key in essential_keys:
    val = os.environ.get(key)
    if val:
        masked = val[:6] + "..." + val[-4:] if len(val) > 10 else "***"
        print(f"  * {key:20}: [ CONFIGURED ] -> {masked}")
    else:
        print(f"  * {key:20}: [ MISSING ] (Ensure it is set in .env)")

print("\n[STEP 2] PIPELINE & COMPONENT IMPORTS")
try:
    from brain.planner import PlannerBrain
    print("  * PlannerBrain import: OK")
except Exception as e:
    print(f"  * PlannerBrain import: FAIL -> {e}")

try:
    from brain.intent_parser import parse_intent
    print("  * Intent Parser import: OK")
except Exception as e:
    print(f"  * Intent Parser import: FAIL -> {e}")

try:
    from system.live_data import get_retrieval_health, realtime_web_query
    print("  * Live Data Realtime Retrieval import: OK")
except Exception as e:
    print(f"  * Live Data Realtime Retrieval import: FAIL -> {e}")

try:
    from system.temporal_engine import parse_temporal_expression
    print("  * Temporal Engine parsing import: OK")
except Exception as e:
    print(f"  * Temporal Engine parsing import: FAIL -> {e}")

try:
    from execution.action_executor import execute_action
    print("  * Action Executor import: OK")
except Exception as e:
    print(f"  * Action Executor import: FAIL -> {e}")

print("\n[STEP 3] REAL-TIME RETRIEVAL CIRCUIT HEALTH STATUS")
try:
    health = get_retrieval_health()
    print("  * Retrieval Backends Status:")
    for src, info in health.items():
        avail_str = "ACTIVE" if info.get("available") else "CIRCUIT_BROKEN"
        errs = info.get("errors", 0)
        print(f"    - {src:20}: State={avail_str:14} | Failures={errs} | Last error={info.get('last_error')}")
except Exception as e:
    print(f"  * Could not retrieve real-time search health: {e}")

print("\n[STEP 4] TEMPORAL STATE & STORAGE INTEGRITY")
state_path = os.path.join(base_dir, "data", "temporal_state.json")
print(f"  * Temporal state JSON path: {state_path}")
if os.path.exists(state_path):
    import json
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        print(f"  * Temporal state file integrity: OK (Valid JSON)")
        print(f"    - Reminders: {len(data.get('reminders', []))}")
        print(f"    - Timers: {len(data.get('timers', []))}")
        print(f"    - Alarms: {len(data.get('alarms', []))}")
        print(f"    - Stopwatches: {len(data.get('stopwatches', {}))}")
    except Exception as e:
        print(f"  * Temporal state file read failed: {e}")
else:
    print("  * Temporal state file: NOT CREATED YET (Will initialize on first reminder/timer)")

print("\n======================================================================")
print("                     HEALTH CHECK PROCESS COMPLETE")
print("======================================================================")
