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


def get_youtube_video_url(query: str) -> str | None:
    """Scrape the YouTube search results page directly to resolve the direct watch URL."""
    try:
        import urllib.parse
        import requests
        import re
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"}
        url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}"
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            # Look for watch?v= format in the page source
            matches = re.findall(r"/watch\?v=[a-zA-Z0-9_-]{11}", r.text)
            if matches:
                # Deduplicate and return first complete watch URL
                video_id = matches[0]
                return f"https://www.youtube.com{video_id}"
    except Exception as e:
        print(f"[YOUTUBE RESOLVER ERROR] Scraper failed: {e}")
    return None


# =========================================
# EXECUTE SINGLE ACTION (recursive)
# =========================================

async def _execute_single(intent_data: dict, loop, memory=None) -> any:
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
        query = intent_data.get("query", "")
        if query:
            video_url = get_youtube_video_url(query)
            if video_url:
                sep = "&" if "?" in video_url else "?"
                autoplay_url = f"{video_url}{sep}autoplay=1"
                print(f"[MEDIA ROUTER] Found direct YouTube video: '{video_url}'. Opening with autoplay.")
                return open_url_in_chrome(autoplay_url)
        return youtube_search(query)

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
        if not location:
            from memory.preference import PreferenceMemory
            location = PreferenceMemory().get("default_city", "Kashipur, Uttarakhand, India")
        summary  = await loop.run_in_executor(
            None, functools.partial(get_weather, location, intent_data.get("query", ""))
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
        
        # Ingest rich memory context
        from memory.preference import PreferenceMemory
        from memory.semantic import SemanticMemory
        from memory.episodic import EpisodicMemory
        
        pref_mem = PreferenceMemory()
        sem_mem = SemanticMemory()
        epi_mem = EpisodicMemory()
        
        env_ctx = "== USER SYSTEM CONTEXT ==\n"
        env_ctx += f"- Preferred Location/City: {pref_mem.get('default_city', 'Kashipur, Uttarakhand, India')}\n"
        fav_app = pref_mem.get_favorite_app()
        if fav_app:
            env_ctx += f"- Mapped Favorite Desktop App: {fav_app}\n"
        if sem_mem.knowledge:
            env_ctx += "- Workspace & Semantic Facts:\n"
            for k, v in list(sem_mem.knowledge.items())[:5]:
                env_ctx += f"  * {k}: {v}\n"
        if epi_mem.events:
            env_ctx += "- Recent Actions Completed:\n"
            for ev in epi_mem.events[-3:]:
                ts = ev.get("timestamp", "")[:19].replace("T", " ")
                env_ctx += f"  * [{ts}] {ev.get('query')} -> {ev.get('intent')} (success={ev.get('success')})\n"
        env_ctx += "=========================\n\n"
        
        # Inject this context directly into the Groq ask completion system prompt!
        from llm.groq_client import DEFAULT_SYSTEM_PROMPT
        custom_system = DEFAULT_SYSTEM_PROMPT + "\n" + env_ctx
        
        full_query = f"{now_ctx}\n\nUser: {query_text}"
        history = memory.get() if memory else None
        
        response   = await loop.run_in_executor(
            None, functools.partial(ask_groq, full_query, custom_system, DEFAULT_MODEL, history)
        )
        return {"type": "ai_response", "response": response}

    # ── SPOTIFY CONTROL ───────────────────────────────────────────────────────
    if intent == "SPOTIFY_CONTROL":
        command = intent_data.get("command") or ""
        from system.spotify_control import control_spotify
        response = control_spotify(command)
        return {"type": "ai_response", "response": response}

    # ── MAP ───────────────────────────────────────────────────────────────────
    if intent == "MAP":
        location = intent_data.get("location") or ""
        from core.realtime_emit import emit_json
        if location.lower().strip() in ("hide", "close", "exit", "dismiss"):
            await emit_json({"type": "hide_map"})
            return {"type": "ai_response", "response": "Hiding tactical map interface sir."}
        else:
            await emit_json({"type": "show_map", "location": location})
            return {"type": "ai_response", "response": f"Displaying tactical holographic map of {location or 'your location'} sir."}

    # ── WINDOW CONTROL ────────────────────────────────────────────────────────
    if intent == "WINDOW_CONTROL":
        command = intent_data.get("command", "close")
        target  = intent_data.get("target", "")
        from execution.window_control import close_active_window, minimize_active_window, maximize_active_window, focus_window
        
        if command == "minimize":
            success = minimize_active_window()
            return {"type": "ai_response", "response": "Minimizing the active window, sir." if success else "I could not minimize the window, sir."}
        elif command == "maximize":
            success = maximize_active_window()
            return {"type": "ai_response", "response": "Maximizing the active window, sir." if success else "I could not maximize the window, sir."}
        else: # close
            if target and target.lower() not in ("it", "that", "window", "active window"):
                focus_window(target)
            success = close_active_window()
            return {"type": "ai_response", "response": "Closing the active window, sir." if success else "I could not close the active window, sir."}

    # ── CLARIFICATION ─────────────────────────────────────────────────────────
    if intent == "CLARIFICATION":
        question = intent_data.get("question") or "Could you clarify that, sir?"
        return {"type": "ai_response", "response": question}

    if intent is None:
        return None
    return False


# =========================================
# EXECUTE ACTION (public entry point)
# =========================================

async def execute_action(intent_data: dict, memory=None):
    try:
        loop   = asyncio.get_running_loop()
        intent = intent_data.get("intent")
        if intent is None:
            return None
        
        # Import active action verification
        from execution.verifier import verify_action

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
                result = None
                success = False
                # Self-checking attempt loop (up to 2 times)
                for attempt in range(2):
                    result = await _execute_single(action, loop, memory)
                    success = verify_action(action, bool(result))
                    if success:
                        break
                    print(f"[RETRY LOOP] Sub-action verification failed (attempt {attempt + 1}/2): {action}")
                    await asyncio.sleep(0.5)

                if isinstance(result, dict) and result.get("type") == "ai_response":
                    responses.append(result["response"])
                elif not success:
                    print(f"[MULTI_ACTION] Sub-action failed permanently: {action}")

            if responses:
                return {"type": "ai_response", "response": " ".join(responses)}
            return True

        # Single Action: Self-checking attempt loop (up to 2 times)
        result = None
        success = False
        for attempt in range(2):
            result = await _execute_single(intent_data, loop, memory)
            success = verify_action(intent_data, bool(result))
            if success:
                break
            print(f"[RETRY LOOP] Action verification failed (attempt {attempt + 1}/2): {intent_data}")
            await asyncio.sleep(0.5)

        return result if success else False

    except Exception as e:
        print(f"[ACTION ERROR] {e}")
        return False