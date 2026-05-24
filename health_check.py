"""
FRIDAY Backend Health Check — uses correct module APIs
"""
import sys
sys.path.insert(0, 'backend')

results = []

# 1. Intent Parser (functional API)
try:
    from brain.intent_parser import parse_intent
    r = parse_intent('what is the weather in Delhi')
    intent = r.get('intent', 'unknown') if isinstance(r, dict) else str(r)
    results.append(('[OK]', 'parse_intent', 'intent=' + intent))
except Exception as e:
    results.append(('[FAIL]', 'parse_intent', str(e)))

# 2. Context Manager
try:
    from brain.context_manager import ContextManager
    cm = ContextManager()
    cm.update('Open Spotify', 'OPEN_APP')
    entity = cm.current_entity
    results.append(('[OK]', 'ContextManager', 'entity=' + str(entity)))
except Exception as e:
    results.append(('[FAIL]', 'ContextManager', str(e)))

# 3. App Control (functional API, no class)
try:
    from system.app_control import open_app, scan_installed_apps, _APP_DISCOVERY_INDEX
    count = len(_APP_DISCOVERY_INDEX)
    results.append(('[OK]', 'app_control', 'indexed ' + str(count) + ' apps'))
except Exception as e:
    results.append(('[FAIL]', 'app_control', str(e)))

# 4. Preference Memory
try:
    from memory.preference import PreferenceMemory
    pm = PreferenceMemory()
    city = pm.get('default_city')
    results.append(('[OK]', 'PreferenceMemory', 'city=' + str(city)))
except Exception as e:
    results.append(('[FAIL]', 'PreferenceMemory', str(e)))

# 5. Groq Client (functional API, uses ask_groq)
try:
    from llm.groq_client import ask_groq, DEFAULT_MODEL
    results.append(('[OK]', 'groq_client', 'default_model=' + str(DEFAULT_MODEL)))
except Exception as e:
    results.append(('[FAIL]', 'groq_client', str(e)))

# 6. Pipeline (functional API, uses process_transcript)
try:
    from core.pipeline import process_transcript
    results.append(('[OK]', 'pipeline', 'process_transcript importable'))
except Exception as e:
    results.append(('[FAIL]', 'pipeline', str(e)))

# 7. Live Data
try:
    from system.live_data import get_weather
    results.append(('[OK]', 'live_data', 'get_weather importable'))
except Exception as e:
    results.append(('[FAIL]', 'live_data', str(e)))

# 8. Action Executor
try:
    from execution.action_executor import execute_action
    results.append(('[OK]', 'action_executor', 'execute_action importable'))
except Exception as e:
    results.append(('[FAIL]', 'action_executor', str(e)))

# 9. TTS (Edge TTS)
try:
    import edge_tts
    results.append(('[OK]', 'edge_tts', 'available'))
except ImportError:
    results.append(('[WARN]', 'edge_tts', 'not installed — TTS will fail'))

# 10. FastAPI server
try:
    import fastapi, uvicorn, websockets
    results.append(('[OK]', 'server_deps', 'fastapi/uvicorn/websockets available'))
except ImportError as e:
    results.append(('[FAIL]', 'server_deps', str(e)))

# Print results
print()
print('=' * 60)
print('  FRIDAY BACKEND HEALTH CHECK')
print('=' * 60)
for status, module, detail in results:
    print(f'  {status} {module}: {detail}')

failures = [r for r in results if r[0] == '[FAIL]']
print('=' * 60)
if failures:
    print(f'  RESULT: {len(failures)}/{len(results)} FAILURES')
    sys.exit(1)
else:
    print(f'  RESULT: ALL {len(results)} CHECKS PASSED')
print()
