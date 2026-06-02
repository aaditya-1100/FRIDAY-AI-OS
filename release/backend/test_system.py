"""
FRIDAY - Comprehensive Module Testing
Tests all core modules for functionality
"""

import asyncio
import sys
from datetime import datetime

test_results = []

def register_test(name):
    """Decorator for test functions (renamed to avoid pytest collection conflict)"""
    def decorator(func):
        async def wrapper():
            try:
                print(f"\n[TEST] {name}...", end=" ")
                await func()
                print("[PASS]")
                test_results.append((name, "PASS", None))
            except Exception as e:
                print(f"[FAIL] {e}")
                test_results.append((name, "FAIL", str(e)))
        return wrapper
    return decorator


@register_test("Config Module")
async def test_config():
    from config.settings import WAKE_WORDS, EXIT_WORDS, MAX_MEMORY
    assert WAKE_WORDS is not None
    assert EXIT_WORDS is not None
    assert MAX_MEMORY == 12


@register_test("Models Module")
async def test_models():
    from config.models import GROQ_MODEL
    assert GROQ_MODEL == "llama-3.1-8b-instant"


@register_test("Intent Parser - Search Query")
async def test_intent_search():
    from brain.intent_parser import parse_intent
    result = parse_intent("search for python on youtube")
    assert result["intent"] in ("SEARCH", "YOUTUBE_TOPIC_SEARCH")
    assert "python" in result["query"]


@register_test("Intent Parser - Open Query")
async def test_intent_open():
    from brain.intent_parser import parse_intent
    result = parse_intent("open spotify")
    assert result["intent"] in ("OPEN", "PLAY_MEDIA")


@register_test("Intent Parser - Play Query")
async def test_intent_play():
    from brain.intent_parser import parse_intent
    result = parse_intent("play music")
    assert result["intent"] == "PLAY_MEDIA"


@register_test("Intent Parser - Screenshot Query")
async def test_intent_screenshot():
    from brain.intent_parser import parse_intent
    result = parse_intent("take screenshot")
    assert result["intent"] == "SCREENSHOT"


@register_test("Intent Parser - System Status Query")
async def test_intent_system():
    from brain.intent_parser import parse_intent
    result = parse_intent("system status")
    assert result["intent"] == "SYSTEM_STATUS"


@register_test("Intent Parser - Unmatched Query")
async def test_intent_none():
    from brain.intent_parser import parse_intent
    result = parse_intent("tell me a joke")
    assert result["intent"] in (None, "AI_QUERY")


@register_test("Wake Word Detection - Positive")
async def test_wake_word_positive():
    from voice.wake_detector import detect_wake_word
    assert detect_wake_word("hey friday") is True


@register_test("Wake Word Detection - Negative")
async def test_wake_word_negative():
    from voice.wake_detector import detect_wake_word
    assert detect_wake_word("hello world") is False


@register_test("Short Term Memory - Basic")
async def test_memory_short_term():
    from memory.short_term import ShortTermMemory
    mem = ShortTermMemory()
    mem.add("user", "hello")
    mem.add("assistant", "hi there")
    history = mem.get()
    assert len(history) == 2
    assert history[0]["role"] == "user"


@register_test("Short Term Memory - Max Limit")
async def test_memory_max_limit():
    from memory.short_term import ShortTermMemory
    mem = ShortTermMemory()
    for i in range(20):
        mem.add("user", f"message {i}")
    history = mem.get()
    assert len(history) <= 12


@register_test("Semantic Memory - Update")
async def test_semantic_memory():
    from memory.semantic_memory import SemanticMemory
    mem = SemanticMemory()
    mem.update(subject="test", intent="SEARCH")
    assert mem.last_subject == "test"
    assert mem.last_intent == "SEARCH"


@register_test("Phase D - Episodic Memory Read/Write Serialization")
async def test_phase_d_episodic_memory():
    import tempfile
    import os
    from memory.episodic import EpisodicMemory
    
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        tmp_path = tmp.name
        
    try:
        mem = EpisodicMemory(file_path=tmp_path)
        mem.clear()
        
        # Log event
        mem.log_event(query="open notepad", intent="OPEN", success=True, metadata={"target": "notepad"})
        assert len(mem.events) == 1
        assert mem.get_last_event()["intent"] == "OPEN"
        
        # Load in another instance
        mem2 = EpisodicMemory(file_path=tmp_path)
        assert len(mem2.events) == 1
        assert mem2.get_last_event()["metadata"]["target"] == "notepad"
        
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@register_test("Phase D - Preference Memory Read/Write Serialization")
async def test_phase_d_preference_memory():
    import tempfile
    import os
    from memory.preference import PreferenceMemory
    
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        tmp_path = tmp.name
        
    try:
        mem = PreferenceMemory(file_path=tmp_path)
        mem.clear()
        
        # Set preference and update app count
        mem.set("default_city", "Los Angeles")
        mem.update_favorite_app("chrome")
        mem.update_favorite_app("chrome")
        mem.update_favorite_app("notepad")
        
        assert mem.get("default_city") == "Los Angeles"
        assert mem.get_favorite_app() == "chrome"
        
        # Load in another instance
        mem2 = PreferenceMemory(file_path=tmp_path)
        assert mem2.get("default_city") == "Los Angeles"
        assert mem2.get_favorite_app() == "chrome"
        
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@register_test("Phase D - Semantic Memory Read/Write Serialization")
async def test_phase_d_semantic_memory():
    import tempfile
    import os
    from memory.semantic import SemanticMemory
    
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        tmp_path = tmp.name
        
    try:
        mem = SemanticMemory(file_path=tmp_path)
        mem.clear()
        
        # Add facts
        mem.add_fact("user_home", "C:\\Users\\default")
        mem.add_fact("location", "Paris")
        
        assert mem.get_fact("user_home") == "C:\\Users\\default"
        assert mem.get_fact("location") == "Paris"
        
        # Load in another instance
        mem2 = SemanticMemory(file_path=tmp_path)
        assert mem2.get_fact("user_home") == "C:\\Users\\default"
        assert mem2.get_fact("location") == "Paris"
        
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@register_test("Phase 2 - Real-Time Retrieval Tracing & Health Logging")
async def test_phase2_retrieval_tracking():
    from system.live_data import RetrievalTracker
    tracker = RetrievalTracker()
    tracker.log_attempt("TestAPI", "SUCCESS", 5, 120.5)
    tracker.log_attempt("FallbackAPI", "HTTP_403", 0, 50.0, "Forbidden")
    
    summary = tracker.get_summary()
    assert "TestAPI: SUCCESS (5 results)" in summary
    assert "FallbackAPI: HTTP_403 (0 results) [Error: Forbidden]" in summary


@register_test("Phase 2 - Geographic Geocoding & Haversine Solver")
async def test_phase2_geographic_solver():
    from system.live_data import _resolve_geographic_query, haversine_distance
    
    # Verify mathematical haversine calculation
    # Coordinates of New York (40.7128, -74.0060) and Los Angeles (34.0522, -118.2437)
    dist = haversine_distance(40.7128, -74.0060, 34.0522, -118.2437)
    assert 3900 < dist < 4000  # approximately ~3960 km
    
    # Test geocoding and query parsing (mocked or live fallback if Nominatim is offline)
    res = _resolve_geographic_query("distance from India to Tokyo")
    assert res is not None
    assert "Calculated Geographic Context" in res
    assert "kilometers" in res


@register_test("Phase 2 - Media Intent Direct Watch-Link Router")
async def test_phase2_media_watch_link():
    from execution.action_executor import get_youtube_video_url
    
    url = get_youtube_video_url("interstellar trailer")
    assert url is not None
    assert "youtube.com" in url or "youtu.be" in url


@register_test("Phase 2 - Native Spotify Desktop Application Mapping")
async def test_phase2_native_spotify_mapping():
    from system.app_control import open_app
    import unittest.mock as mock
    
    with mock.patch("os.system") as mock_system, mock.patch("os.startfile") as mock_startfile:
        res = open_app("spotify")
        assert res is True
        # Supports both new dynamic discovery (uses os.startfile) and legacy fallback (uses os.system)
        called_startfile = mock_startfile.called
        called_system = any("spotify" in str(args[0]) for args, _ in mock_system.call_args_list)
        assert called_startfile or called_system


@register_test("Context Manager - Entity Tracking")
async def test_context_manager():
    from brain.context_manager import ContextManager
    ctx = ContextManager()
    ctx.update("check youtube videos")
    assert ctx.current_entity.lower() == "youtube"


@register_test("Entity Tracker - Positive")
async def test_entity_tracker():
    from brain.entity_tracker import extract_entity
    entity = extract_entity("search india news")
    assert entity == ("india", "topic")


@register_test("Entity Tracker - Negative")
async def test_entity_tracker_none():
    from brain.entity_tracker import extract_entity
    entity = extract_entity("what is the weather")
    assert entity is None


@register_test("Chrome opener - resolve")
async def test_chrome_opener():
    from system.chrome_opener import resolve_chrome_executable
    p = resolve_chrome_executable()
    assert p is None or p.is_file()


@register_test("Browser Agent Functions - Import")
async def test_browser_agent():
    from browser.browser_agent import search_google, search_youtube, open_url, youtube_search
    assert callable(search_google)
    assert callable(search_youtube)
    assert callable(open_url)
    assert callable(youtube_search)


@register_test("Site registry - lookup")
async def test_site_registry():
    from config.site_registry import get_workspace_url
    assert get_workspace_url("gemini")
    assert get_workspace_url("chatgpt")
    assert get_workspace_url("notion")


@register_test("Action Executor - Import")
async def test_action_executor():
    from execution.action_executor import execute_action
    assert callable(execute_action)


@register_test("Action Executor - None Intent")
async def test_action_executor_none():
    from execution.action_executor import execute_action
    result = await execute_action({"intent": None})
    assert result is None


@register_test("Groq Client - Import")
async def test_groq_client():
    from llm.groq_client import ask_groq, get_groq_client
    assert callable(ask_groq)
    assert callable(get_groq_client)


@register_test("Response Generator - Import")
async def test_response_generator():
    from llm.response_generator import generate_response
    assert callable(generate_response)


@register_test("System Control - Import")
async def test_system_control():
    from execution.system_control import (
        get_system_status,
        clear_temp,
        shutdown_pc,
        restart_pc
    )
    assert callable(get_system_status)
    # Don't test these as they would perform actual actions


@register_test("App Control - Import")
async def test_app_control():
    from system.app_control import open_app
    assert callable(open_app)


@register_test("Main Module - Imports")
async def test_main_imports():
    # This tests that main.py can be imported without errors
    import main
    assert hasattr(main, 'main')
    assert asyncio.iscoroutinefunction(main.main)


@register_test("Phase A - Native OS Drive & Path Routing")
async def test_phase_a_native_routing():
    from system.app_control import open_app
    import unittest.mock as mock
    import os
    
    with mock.patch("os.startfile") as mock_startfile, mock.patch("os.system") as mock_system:
        # 1. Drive matching "c drive" -> C:\
        res = open_app("c drive")
        assert res is True
        mock_startfile.assert_any_call("C:\\")

        # 2. Explorer command -> explorer.exe
        res = open_app("explorer")
        assert res is True
        mock_system.assert_any_call("start explorer.exe")

        # 3. Special folder mapping "downloads" -> Path.home() / Downloads
        res = open_app("downloads")
        assert res is True
        # downloads should have triggered standard folder launch
        assert mock_startfile.call_count >= 1


@register_test("Phase A - Stateful Pronoun Context Continuation")
async def test_phase_a_context_pronouns():
    from brain.intent_parser import parse_intent
    
    # Simulate history: previously opened notepad
    history = [
        {"role": "user", "content": "open notepad"},
        {"role": "assistant", "content": "Opening Notepad sir"}
    ]
    
    # Query "open that again" -> resolves to notepad
    res = parse_intent("open that again", history)
    assert res["intent"] == "OPEN"
    assert res["target"] == "notepad"


@register_test("Phase A - Clarification Routing for Incomplete Commands")
async def test_phase_a_clarification():
    from brain.intent_parser import parse_intent
    
    # Parameterless command "open" -> clarification question
    res = parse_intent("open")
    assert res["intent"] == "CLARIFICATION"
    assert "question" in res
    assert "open" in res["question"].lower()


@register_test("Phase B - Freshness Routing and Realtime News Synthesis")
async def test_phase_b_freshness_routing():
    from system.live_data import _is_recency_query, realtime_web_query
    
    # 1. Freshness detection triggers
    assert _is_recency_query("latest tech news") is True
    assert _is_recency_query("what is the weather today") is True
    assert _is_recency_query("timeless coding guidelines") is False

    # 2. Verify synthesis pipeline runs cleanly
    res = realtime_web_query("OpenAI launches 2026")
    assert isinstance(res, str)
    assert len(res) > 5


@register_test("Phase C - Post-Execution Action Verification")
async def test_phase_c_action_verification():
    from execution.verifier import verify_app_running, verify_action
    import unittest.mock as mock
    
    # 1. Check process scanning
    # Test verify_app_running against explorer.exe (always runs on Windows)
    is_explorer = verify_app_running("explorer.exe")
    assert is_explorer is True
    
    # Test verify_app_running against non-existent app
    is_dummy = verify_app_running("completely_fake_and_nonexistent_process_xyz.exe")
    assert is_dummy is False

    # 2. Check verify_action for a file check
    with mock.patch("os.path.exists", return_value=True):
        res = verify_action({"intent": "OPEN", "target": "C:\\some_existing_file.txt"}, True)
        assert res is True

    # 3. Check verify_action for unlisted / fallback intent
    res = verify_action({"intent": "DUMMY"}, True)
    assert res is True


@register_test("Phase C - Self-Correcting Planner-Retry Loop")
async def test_phase_c_retry_loop():
    from execution.action_executor import execute_action
    import unittest.mock as mock

    calls = 0

    # We mock _execute_single to keep track of calls
    async def mock_execute_single(intent_data, loop, memory=None):
        nonlocal calls
        calls += 1
        # First attempt returns False (fails), second attempt returns True (succeeds)
        return {"type": "ai_response", "response": "Success!"} if calls > 1 else False

    # We mock verify_action to succeed only if execution is successful
    def mock_verify_action(intent_data, success):
        return success

    with mock.patch("execution.action_executor._execute_single", side_effect=mock_execute_single), \
         mock.patch("execution.verifier.verify_action", side_effect=mock_verify_action):
         
        # Execute an action that fails initially but succeeds on retry
        res = await execute_action({"intent": "AI_QUERY", "query": "hello"})
        
        # Verify it retried
        assert calls == 2
        assert res == {"type": "ai_response", "response": "Success!"}


async def run_all_tests():
    """Run all tests"""
    print("\n" + "="*60)
    print("FRIDAY AI ASSISTANT - COMPREHENSIVE TEST SUITE")
    print("="*60)
    print(f"Starting tests at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("-"*60)

    # Collect all test functions
    tests = [
        test_config(),
        test_models(),
        test_intent_search(),
        test_intent_open(),
        test_intent_play(),
        test_intent_screenshot(),
        test_intent_system(),
        test_intent_none(),
        test_wake_word_positive(),
        test_wake_word_negative(),
        test_memory_short_term(),
        test_memory_max_limit(),
        test_semantic_memory(),
        test_context_manager(),
        test_entity_tracker(),
        test_entity_tracker_none(),
        test_chrome_opener(),
        test_browser_agent(),
        test_site_registry(),
        test_action_executor(),
        test_action_executor_none(),
        test_groq_client(),
        test_response_generator(),
        test_system_control(),
        test_app_control(),
        test_main_imports(),
        test_phase_a_native_routing(),
        test_phase_a_context_pronouns(),
        test_phase_a_clarification(),
        test_phase_b_freshness_routing(),
        test_phase_c_action_verification(),
        test_phase_c_retry_loop(),
        test_phase_d_episodic_memory(),
        test_phase_d_preference_memory(),
        test_phase_d_semantic_memory(),
        test_phase2_retrieval_tracking(),
        test_phase2_geographic_solver(),
        test_phase2_media_watch_link(),
        test_phase2_native_spotify_mapping(),
    ]

    # Run all tests
    await asyncio.gather(*tests)

    # Summary
    print("\n" + "-"*60)
    print("TEST SUMMARY")
    print("-"*60)

    total = len(test_results)
    passed = sum(1 for _, status, _ in test_results if status == "PASS")
    failed = sum(1 for _, status, _ in test_results if status == "FAIL")

    print(f"Total Tests: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Success Rate: {(passed/total)*100:.1f}%")

    if failed > 0:
        print("\nFailed Tests:")
        for name, status, error in test_results:
            if status == "FAIL":
                print(f"  - {name}: {error}")

    print("\n" + "="*60)
    print(f"Tests completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)

    return failed == 0


if __name__ == "__main__":
    try:
        success = asyncio.run(run_all_tests())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n[TESTS] Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n[TESTS] Fatal error: {e}")
        sys.exit(1)
