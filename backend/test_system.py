"""
FRIDAY - Comprehensive Module Testing
Tests all core modules for functionality
"""

import asyncio
import sys
from datetime import datetime

test_results = []

def test(name):
    """Decorator for test functions"""
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


@test("Config Module")
async def test_config():
    from config.settings import WAKE_WORDS, EXIT_WORDS, MAX_MEMORY
    assert WAKE_WORDS is not None
    assert EXIT_WORDS is not None
    assert MAX_MEMORY == 12


@test("Models Module")
async def test_models():
    from config.models import GROQ_MODEL
    assert GROQ_MODEL == "llama-3.1-8b-instant"


@test("Intent Parser - Search Query")
async def test_intent_search():
    from brain.intent_parser import parse_intent
    result = parse_intent("search for python on youtube")
    assert result["intent"] == "SEARCH"
    assert result["platform"] == "youtube"
    assert "python" in result["query"]


@test("Intent Parser - Open Query")
async def test_intent_open():
    from brain.intent_parser import parse_intent
    result = parse_intent("open spotify")
    assert result["intent"] == "OPEN"
    assert result["target"] == "spotify"


@test("Intent Parser - Play Query")
async def test_intent_play():
    from brain.intent_parser import parse_intent
    result = parse_intent("play music")
    assert result["intent"] == "PLAY_MEDIA"


@test("Intent Parser - Screenshot Query")
async def test_intent_screenshot():
    from brain.intent_parser import parse_intent
    result = parse_intent("take screenshot")
    assert result["intent"] == "SCREENSHOT"


@test("Intent Parser - System Status Query")
async def test_intent_system():
    from brain.intent_parser import parse_intent
    result = parse_intent("system status")
    assert result["intent"] == "SYSTEM_STATUS"


@test("Intent Parser - Unmatched Query")
async def test_intent_none():
    from brain.intent_parser import parse_intent
    result = parse_intent("tell me a joke")
    assert result["intent"] is None


@test("Wake Word Detection - Positive")
async def test_wake_word_positive():
    from voice.wake_detector import detect_wake_word
    assert detect_wake_word("hey friday") is True


@test("Wake Word Detection - Negative")
async def test_wake_word_negative():
    from voice.wake_detector import detect_wake_word
    assert detect_wake_word("hello world") is False


@test("Short Term Memory - Basic")
async def test_memory_short_term():
    from memory.short_term import ShortTermMemory
    mem = ShortTermMemory()
    mem.add("user", "hello")
    mem.add("assistant", "hi there")
    history = mem.get()
    assert len(history) == 2
    assert history[0]["role"] == "user"


@test("Short Term Memory - Max Limit")
async def test_memory_max_limit():
    from memory.short_term import ShortTermMemory
    mem = ShortTermMemory()
    for i in range(20):
        mem.add("user", f"message {i}")
    history = mem.get()
    assert len(history) <= 12


@test("Semantic Memory - Update")
async def test_semantic_memory():
    from memory.semantic_memory import SemanticMemory
    mem = SemanticMemory()
    mem.update(subject="test", intent="SEARCH")
    assert mem.last_subject == "test"
    assert mem.last_intent == "SEARCH"


@test("Context Manager - Entity Tracking")
async def test_context_manager():
    from brain.context_manager import ContextManager
    ctx = ContextManager()
    ctx.update("check youtube videos")
    assert ctx.current_entity == "youtube"


@test("Entity Tracker - Positive")
async def test_entity_tracker():
    from brain.entity_tracker import extract_entity
    entity = extract_entity("search india news")
    assert entity == "india"


@test("Entity Tracker - Negative")
async def test_entity_tracker_none():
    from brain.entity_tracker import extract_entity
    entity = extract_entity("what is the weather")
    assert entity is None


@test("Chrome opener - resolve")
async def test_chrome_opener():
    from system.chrome_opener import resolve_chrome_executable
    p = resolve_chrome_executable()
    assert p is None or p.is_file()


@test("Browser Agent Functions - Import")
async def test_browser_agent():
    from browser.browser_agent import search_google, search_youtube, open_url, youtube_search
    assert callable(search_google)
    assert callable(search_youtube)
    assert callable(open_url)
    assert callable(youtube_search)


@test("Site registry - lookup")
async def test_site_registry():
    from config.site_registry import get_workspace_url
    assert get_workspace_url("gemini")
    assert get_workspace_url("chatgpt")
    assert get_workspace_url("notion")


@test("Action Executor - Import")
async def test_action_executor():
    from execution.action_executor import execute_action
    assert callable(execute_action)


@test("Action Executor - None Intent")
async def test_action_executor_none():
    from execution.action_executor import execute_action
    result = await execute_action({"intent": None})
    assert result is None


@test("Groq Client - Import")
async def test_groq_client():
    from llm.groq_client import ask_groq, get_groq_client
    assert callable(ask_groq)
    assert callable(get_groq_client)


@test("Response Generator - Import")
async def test_response_generator():
    from llm.response_generator import generate_response
    assert callable(generate_response)


@test("System Control - Import")
async def test_system_control():
    from execution.system_control import (
        get_system_status,
        clear_temp,
        shutdown_pc,
        restart_pc
    )
    assert callable(get_system_status)
    # Don't test these as they would perform actual actions


@test("App Control - Import")
async def test_app_control():
    from execution.app_control import open_app
    assert callable(open_app)


@test("Main Module - Imports")
async def test_main_imports():
    # This tests that main.py can be imported without errors
    import main
    assert hasattr(main, 'main')
    assert asyncio.iscoroutinefunction(main.main)


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
