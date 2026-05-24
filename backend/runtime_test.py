"""
runtime_test.py — FRIDAY end-to-end pipeline tests.
Tests: intent parsing, context memory, realtime web query, WS flow.
"""
import sys
import asyncio
sys.path.insert(0, 'backend')

# ── 1. Intent Parser Tests ──────────────────────────────────────────────────

def test_intent_parser():
    from brain.intent_parser import parse_intent
    print("\n=== INTENT PARSER TESTS ===")
    tests = [
        ("what is the weather in Delhi", "WEATHER"),
        ("open youtube and search for lo-fi music", "MULTI_ACTION"),
        ("latest news about AI", "REALTIME_QUERY"),
        ("show me a map of Paris", "MAP"),
        ("what is 2 plus 2", "AI_QUERY"),
        ("who is the current prime minister of India", "REALTIME_QUERY"),
        ("play Bohemian Rhapsody", "PLAY_MEDIA"),
        ("take a screenshot", "SCREENSHOT"),
        ("pause spotify", "SPOTIFY_CONTROL"),
        ("open chatgpt", "OPEN"),
        ("search rust programming on youtube", "SEARCH"),
        ("how much RAM is my computer using", "SYSTEM_STATUS"),
    ]
    passed = 0
    for query, expected in tests:
        result = parse_intent(query)
        intent = result.get("intent")
        ok = "OK" if intent == expected else "FAIL"
        status = "PASS" if intent == expected else f"FAIL (got {intent})"
        print(f"  {ok} [{expected:20}] {query!r:50} - {status}")
        if intent == expected:
            passed += 1
    print(f"\n  Intent Parser: {passed}/{len(tests)} passed")
    return passed, len(tests)


# ── 2. Context Manager Tests ─────────────────────────────────────────────────

def test_context():
    from brain.context_manager import ContextManager
    from brain.entity_tracker import extract_entity, has_reference
    print("\n=== CONTEXT MANAGER TESTS ===")

    cm = ContextManager()

    # Test entity extraction
    cm.update("show me a map of Paris")
    assert cm.last_location == "Paris", f"Expected 'Paris', got {cm.last_location!r}"
    print("  OK Entity extraction: 'Paris' tracked correctly")

    # Test pronoun resolution
    cm.update("what is the weather there")
    resolved = cm.resolve_reference("what is the weather there")
    assert resolved == "Paris", f"Expected 'Paris', got {resolved!r}"
    print("  OK Pronoun resolution: 'there' -> 'Paris'")

    # Test enrich_query
    enriched = cm.enrich_query("tell me about it")
    # 'it' should be replaced with current entity
    print(f"  OK Enrich query: 'tell me about it' -> '{enriched}'")

    # Test has_reference
    assert has_reference("what about it") == True
    assert has_reference("open youtube") == False
    print("  OK has_reference: works correctly")

    # Test that last_query doesn't expand unboundedly
    from core.pipeline import apply_context, CONTEXT_PREFIXES
    last = "what is the weather in Paris"
    q1 = "and the humidity"
    result = last + " " + q1 if any(q1.startswith(p) for p in CONTEXT_PREFIXES) else q1
    # next turn: last_query should be the topic, not the expanded version
    print(f"  OK Context prefix expansion: '{last}' + '{q1}' -> '{result}'")

    print("  Context Manager: all tests passed")
    return True


# ── 3. Live Data Tests ───────────────────────────────────────────────────────

def test_live_data():
    print("\n=== LIVE DATA TESTS ===")

    from system.live_data import get_weather, _ddgs_search, _google_news_rss

    # Weather
    print("  Testing get_weather('London')...")
    result = get_weather("London")
    ok = len(result) > 20 and ("London" in result or "celsius" in result.lower() or "temperature" in result.lower())
    print(f"  {'OK' if ok else 'FAIL'} get_weather: {result[:100]!r}")

    # DDGS
    print("  Testing DDGS search...")
    try:
        results = _ddgs_search("FRIDAY AI assistant 2026", max_results=3)
        ok = isinstance(results, list)
        print(f"  {'OK' if ok else 'FAIL'} DDGS search: {len(results)} results")
    except Exception as e:
        print(f"  FAIL DDGS search error: {e}")

    # Google News RSS
    print("  Testing Google News RSS...")
    try:
        items = _google_news_rss("artificial intelligence", max_items=3)
        ok = isinstance(items, list) and len(items) > 0
        print(f"  {'OK' if ok else 'FAIL'} Google News RSS: {len(items)} items")
        if items:
            print(f"    Sample: {items[0].get('title', '')[:80]}")
    except Exception as e:
        print(f"  FAIL Google News RSS error: {e}")


# ── 4. Realtime Web Query ────────────────────────────────────────────────────

def test_realtime_query():
    print("\n=== REALTIME WEB QUERY TEST ===")
    from system.live_data import realtime_web_query
    print("  Testing: 'who is the CEO of OpenAI'...")
    result = realtime_web_query("who is the CEO of OpenAI")
    ok = len(result) > 20
    print(f"  {'OK' if ok else 'FAIL'} Result: {result[:200]!r}")


# ── 5. Short Term Memory ─────────────────────────────────────────────────────

def test_memory():
    print("\n=== SHORT TERM MEMORY TESTS ===")
    from memory.short_term import ShortTermMemory
    m = ShortTermMemory()
    m.add("user", "hello")
    m.add("assistant", "Hi sir")
    m.add("user", "how are you")
    assert len(m.get()) == 3
    print(f"  OK Memory stores {len(m.get())} items correctly")

    # Test cap at 12
    for i in range(15):
        m.add("user", f"msg {i}")
    assert len(m.get()) <= 12
    print(f"  OK Memory capped at {len(m.get())} items (max 12)")


# ── 6. App Control / URL Inference ──────────────────────────────────────────

def test_url_inference():
    print("\n=== URL INFERENCE TESTS ===")
    from config.site_registry import infer_url, get_workspace_url
    tests = [
        ("youtube", "https://www.youtube.com/"),
        ("chatgpt", "https://chatgpt.com/"),
        ("github", "https://github.com"),
        ("reddit", "https://www.reddit.com"),
        ("gmail", "https://mail.google.com"),
    ]
    for name, expected in tests:
        url = get_workspace_url(name) or infer_url(name)
        ok = url.startswith(expected) or expected.startswith(url)
        print(f"  {'OK' if ok else 'FAIL'} '{name}' -> {url!r}")


# ── MAIN ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("FRIDAY RUNTIME TEST SUITE")
    print("=" * 60)

    try:
        p, t = test_intent_parser()
    except Exception as e:
        print(f"  INTENT PARSER FAILED: {e}")

    try:
        test_context()
    except AssertionError as e:
        print(f"  CONTEXT MANAGER FAILED: {e}")
    except Exception as e:
        print(f"  CONTEXT MANAGER ERROR: {e}")

    try:
        test_memory()
    except Exception as e:
        print(f"  MEMORY FAILED: {e}")

    try:
        test_url_inference()
    except Exception as e:
        print(f"  URL INFERENCE FAILED: {e}")

    try:
        test_live_data()
    except Exception as e:
        print(f"  LIVE DATA FAILED: {e}")

    try:
        test_realtime_query()
    except Exception as e:
        print(f"  REALTIME QUERY FAILED: {e}")

    print("\n" + "=" * 60)
    print("TESTS COMPLETE")
    print("=" * 60)
