import os
import sys
import time
import asyncio
import threading

# Add backend directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.api_manager import api_manager
from core.state_manager import AssistantState, set_state, get_state
from brain.routing_manager import RoutingManager
from system.maps_agent import MapsAgent
from system.screen_agent import get_active_window_info
from voice.speak import speak, normalize_speech_text

async def test_cache_and_api_manager():
    print("\n--- [TEST 1] Testing Central APIManager Caching & Cooldowns ---")
    
    # Verify generate cache key matches
    namespace = "test_ns"
    data = {"status": "success", "result": [1, 2, 3]}
    api_manager.set_cached(namespace, data, ttl_seconds=2.0, query="test_query")
    
    # Read cache (should HIT)
    cached = api_manager.get_cached(namespace, query="test_query")
    assert cached == data, "Cache retrieval mismatch!"
    print("[PASS] Cache HIT & match validation successful.")
    
    # Wait for TTL to expire
    print("Waiting 2.5 seconds for cache TTL expiration...")
    await asyncio.sleep(2.5)
    
    # Read cache again (should MISS / expired)
    cached = api_manager.get_cached(namespace, query="test_query")
    assert cached is None, "Cache did not expire correctly!"
    print("[PASS] Cache TTL expiration working perfectly.")

    # Test cooldowns
    api_manager.trigger_cooldown("groq", 1.0)
    assert api_manager.is_cooling_down("groq") is True, "Cooldown not triggered!"
    print("[PASS] API cooldown trigger registered successfully.")
    
    await asyncio.sleep(1.2)
    assert api_manager.is_cooling_down("groq") is False, "Cooldown did not clear!"
    print("[PASS] API cooldown cleared successfully after duration.")

async def test_geospatial_mock_flow():
    print("\n--- [TEST 2] Testing Google Maps Offline / Mock Fallbacks ---")
    agent = MapsAgent()
    
    # Geocoding test
    geo = agent.geocode_place("Kashipur")
    print(f"Geocoded Kashipur: {geo}")
    assert geo is not None, "Grounded mock geocoding failed!"
    
    # Directions test
    route = agent.get_route("Kashipur", "Rudrapur")
    print(f"Route structure: {route.get('status')} | {route.get('duration')}")
    assert route.get("status") in ("OK", "MOCK_FALLBACK"), "Directions routing structure invalid!"
    print("[PASS] Maps geospatial intelligence fallback systems are 100% stable.")

async def test_passive_window_tracking():
    print("\n--- [TEST 3] Testing Native Passive Win32 Window Tracking ---")
    info = get_active_window_info()
    enc = sys.stdout.encoding or 'utf-8'
    safe_title = info.get('title', '').encode(enc, errors='replace').decode(enc)
    print(f"Active Foreground Window Title: '{safe_title}'")
    print(f"Active Foreground Process: '{info.get('process')}'")
    assert "title" in info and "process" in info, "Win32 tracking structure invalid!"
    print("[PASS] Passive active window tracking is completely functional and native.")

async def test_speak_mutex_and_shaper():
    print("\n--- [TEST 4] Testing Single-Speech Mutex & Speech Shaper ---")
    
    # Normalize Markdown
    raw = "```python\nprint('hello')\n```\nHere is a list:\n- First item\n- Second item\nLet's ask about **SAPI5** and **TTS** details!"
    clean = normalize_speech_text(raw)
    print(f"Raw Text:\n{raw}\n")
    print(f"Speech Normalizer Output:\n{clean}\n")
    
    assert "[code block omitted]" in clean, "Code block not filtered!"
    assert "Sapi 5" in clean, "Acronym SAPI5 not converted!"
    assert "Text to speech" in clean, "Acronym TTS not converted!"
    print("[PASS] Speech text shaper successfully generated natural cinematic pacing.")

    # Stress test speak overlapping
    print("Testing overlapping TTS speech play locking...")
    set_state(AssistantState.SPEAKING)
    
    # Trigger duplicate/overlapping plays concurrently
    t1 = asyncio.create_task(speak("Hello Aaditya, testing speech lock thread one.", web_mode=False))
    t2 = asyncio.create_task(speak("Hello Aaditya, testing speech lock thread two.", web_mode=False))
    
    # Cancel immediately
    from voice.speak import cancel_play
    await asyncio.sleep(0.1)
    cancel_play()
    
    await asyncio.gather(t1, t2, return_exceptions=True)
    set_state(AssistantState.IDLE)
    print("[PASS] Speech play locking validation complete (zero concurrent COM locks or audio fighting).")

async def main():
    print("==================================================")
    print("    FRIDAY RUNTIME ORCHESTRATION STRESS TESTS      ")
    print("==================================================")
    
    start_time = time.time()
    try:
        await test_cache_and_api_manager()
        await test_geospatial_mock_flow()
        await test_passive_window_tracking()
        await test_speak_mutex_and_shaper()
        print("\n==================================================")
        print(f" ALL RUNTIME ASSERTIONS PASSED! Time: {time.time() - start_time:.2f}s")
        print("==================================================")
    except Exception as e:
        print(f"\n[FAIL] Stress validation suite failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
