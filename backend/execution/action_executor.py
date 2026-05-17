import asyncio
import functools
from datetime import datetime

from config.site_registry import build_google_search_url, build_youtube_results_url, get_workspace_url
from system.app_control import open_app
from system.chrome_opener import open_url_in_chrome
from execution.system_control import get_system_status
from system.screenshot import take_screenshot
from system.live_data import get_weather, get_news, realtime_web_query
from browser.browser_agent import youtube_search, search_google
from llm.groq_client import ask_groq, DEFAULT_MODEL


# =========================================
# WEB SEARCH (opens browser)
# =========================================

def web_search(query: str) -> bool:
    return open_url_in_chrome(build_google_search_url(query))


def _platform_search(platform: str, query: str) -> bool:
    """Route a SEARCH intent to the correct platform."""
    p = (platform or "youtube").lower().strip()
    if p in ("youtube", "yt"):
        return youtube_search(query)
    if p in ("google",):
        return search_google(query)
    if p in ("spotify",):
        url = f"https://open.spotify.com/search/{query.replace(' ', '%20')}"
        return open_url_in_chrome(url)
    # Fallback: YouTube
    return youtube_search(query)


# =========================================
# DATETIME CONTEXT
# =========================================

def _now_context() -> str:
    now = datetime.now()
    hour = now.hour
    period = "morning" if hour < 12 else ("afternoon" if hour < 17 else ("evening" if hour < 21 else "night"))
    return now.strftime(f"Today is %A, %B %d, %Y. Current time is %I:%M %p ({period}).")


# =========================================
# EXECUTE SINGLE ACTION (recursive)
# =========================================

async def _execute_single(intent_data: dict, loop) -> any:
    """Execute one atomic intent. Used by both direct calls and MULTI_ACTION."""
    intent = intent_data.get("intent")

    # ── OPEN ──────────────────────────────────────────────────────────────────
    if intent == "OPEN":
        return open_app(intent_data.get("target", ""))

    # ── SEARCH (platform-aware) ────────────────────────────────────────────────
    if intent == "SEARCH":
        platform = intent_data.get("platform", "youtube")
        query    = intent_data.get("query", "")
        return _platform_search(platform, query)

    # ── PLAY MEDIA ────────────────────────────────────────────────────────────
    if intent == "PLAY_MEDIA":
        return youtube_search(intent_data.get("query", ""))

    # ── SCREENSHOT ────────────────────────────────────────────────────────────
    if intent == "SCREENSHOT":
        return await loop.run_in_executor(None, take_screenshot)

    # ── SYSTEM STATUS ─────────────────────────────────────────────────────────
    if intent == "SYSTEM_STATUS":
        return {"type": "ai_response", "response": get_system_status()}

    # ── WEB SEARCH (opens browser) ────────────────────────────────────────────
    if intent == "WEB_SEARCH":
        return web_search(intent_data.get("query", ""))

    # ── WEATHER ───────────────────────────────────────────────────────────────
    if intent == "WEATHER":
        location = intent_data.get("location") or ""
        summary  = await loop.run_in_executor(
            None, functools.partial(get_weather, location)
        )
        return {"type": "ai_response", "response": summary}

    # ── NEWS ──────────────────────────────────────────────────────────────────
    if intent == "NEWS":
        topic   = intent_data.get("topic") or ""
        summary = await loop.run_in_executor(
            None, functools.partial(get_news, topic)
        )
        return {"type": "ai_response", "response": summary}

    # ── REALTIME QUERY (web search + LLM summarize) ───────────────────────────
    if intent == "REALTIME_QUERY":
        query   = intent_data.get("query", "")
        summary = await loop.run_in_executor(
            None, functools.partial(realtime_web_query, query)
        )
        return {"type": "ai_response", "response": summary}

    # ── AI QUERY ──────────────────────────────────────────────────────────────
    if intent == "AI_QUERY":
        query_text = intent_data.get("query") or ""
        now_ctx    = _now_context()
        full_query = f"{now_ctx}\n\nUser: {query_text}"
        response   = await loop.run_in_executor(
            None, functools.partial(ask_groq, full_query, None, DEFAULT_MODEL)
        )
        return {"type": "ai_response", "response": response}

    return False


# =========================================
# EXECUTE ACTION (public entry point)
# =========================================

async def execute_action(intent_data: dict):
    try:
        loop   = asyncio.get_running_loop()
        intent = intent_data.get("intent")

        # ── MULTI_ACTION: execute sub-actions sequentially ─────────────────────
        if intent == "MULTI_ACTION":
            actions = intent_data.get("actions", [])
            responses = []

            # ── Smart deduplication: if OPEN + SEARCH target the same platform,
            #    skip the OPEN — the search URL already navigates there directly.
            _PLATFORM_ALIASES = {
                "yt": "youtube", "youtube": "youtube",
                "spotify": "spotify",
                "google": "google",
            }

            def _normalize_platform(name: str) -> str:
                return _PLATFORM_ALIASES.get((name or "").lower().strip(), (name or "").lower().strip())

            filtered = []
            for i, action in enumerate(actions):
                if action.get("intent") == "OPEN":
                    target = _normalize_platform(action.get("target", ""))
                    # Check if any subsequent action searches on the same platform
                    next_actions = actions[i + 1:]
                    will_search_same = any(
                        a.get("intent") == "SEARCH" and _normalize_platform(a.get("platform", "")) == target
                        for a in next_actions
                    )
                    if will_search_same:
                        print(f"[MULTI_ACTION] Skipping OPEN '{target}' — SEARCH follows on same platform")
                        continue
                filtered.append(action)

            for action in filtered:
                result = await _execute_single(action, loop)
                if isinstance(result, dict) and result.get("type") == "ai_response":
                    responses.append(result["response"])
                elif result is False:
                    print(f"[MULTI_ACTION] Sub-action failed: {action}")

            if responses:
                return {"type": "ai_response", "response": " ".join(responses)}
            return True

        return await _execute_single(intent_data, loop)

    except Exception as e:
        print(f"[ACTION ERROR] {e}")
        return False