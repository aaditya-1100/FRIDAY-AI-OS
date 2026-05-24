"""
FRIDAY Intent Parser — v2
- Supports MULTI_ACTION for compound commands ("open yt and search X")
- REALTIME_QUERY for anything needing live web data
- Date/time injected into every prompt so model is temporally aware
- Uses llama-3.3-70b-versatile for superior intent understanding
"""
import json
import re
from datetime import datetime

from llm.groq_client import ask_groq


def _now_context() -> str:
    """Returns a natural language datetime string injected into every prompt."""
    now = datetime.now()
    hour = now.hour
    if hour < 12:
        period = "morning"
    elif hour < 17:
        period = "afternoon"
    elif hour < 21:
        period = "evening"
    else:
        period = "night"
    return now.strftime(f"Today is %A, %B %d, %Y. Current time is %I:%M %p ({period}).")
SYSTEM_PROMPT = """\
You are FRIDAY's intent parser. Your job is to convert user requests into structured JSON.

Return ONLY valid JSON — no markdown, no explanation.

== INTENTS ==

OPEN             → open an app, website, or folder
SEARCH           → search on a specific platform (youtube, google, spotify)
PLAY_MEDIA       → play music/video
WEB_SEARCH       → open a Google search in browser
REALTIME_QUERY   → ANY question about current/recent/upcoming events, weather, news, sports,
                   movies, people, prices, trends, live scores, latest updates, current year facts
                   — basically anything where the answer might have changed in the last year
AI_QUERY         → general conversation, opinions, coding help, explanations (timeless facts)
SCREENSHOT       → take a screenshot
SYSTEM_STATUS    → CPU, RAM, disk usage queries
WEATHER          → explicit weather/temperature/forecast/rain/humidity questions
NEWS             → explicit news/headlines requests
SPOTIFY_CONTROL  → play, pause, next, skip, volume up, volume down on Spotify locally
MAP              → show or display a high-tech tactical map of a specific location
WINDOW_CONTROL   → minimize, maximize, or close the active window, or close/exit a specific application (e.g. "close it", "close notepad", "minimize window")
MULTI_ACTION     → when the user wants TWO OR MORE distinct actions, questions, or tasks in one request
CLARIFICATION    → when a command is incomplete (e.g. "open" or "play" without a target) and needs a follow-up question.

== STATEFUL & PRONOUN CONTEXT RESOLUTION ==
You are provided with CONVERSATION HISTORY showing the latest turns. Use this history to resolve pronouns ("it", "that", "there", "them", "him", "her") or contextual commands:
- If the user says "open that again", look at what was opened in the history (e.g. if the assistant opened Notepad, return {"intent": "OPEN", "target": "notepad"}).
- If the user says "what's the weather there", look at the last mentioned location/city in the history and map it to {"intent": "WEATHER", "location": "<city>"}.
- If the user says "also search marvel", look at the previous platform (e.g., youtube) and combine them or route accordingly.

== SYSTEM ENVIRONMENT CONTEXT RESOLUTION ==
You are provided with SYSTEM ENVIRONMENT CONTEXT (preferred location, favorite app, relational facts, and recent episodic execution history).
- If the user says "what's the weather", and no location is mentioned, look at the "User Preferred City" (e.g., "Kashipur, Uttarakhand, India") in the environment context before falling back to empty.
- If the user says "open my favorite app" or "start it", look at the "User Mapped Favorite App" field.

== CLARIFICATION FORMAT ==
If the user says "open" or "play" or "launch" with absolutely nothing else, return a CLARIFICATION intent:
{
  "intent": "CLARIFICATION",
  "question": "What would you like me to open sir?" or "What would you like me to play sir?"
}
Note: If they specify a general category (e.g. "play music", "play some songs", "open settings"), do NOT clarify. Route "play music" to PLAY_MEDIA, and "open settings" to OPEN.

== MULTI_ACTION FORMAT ==
Use MULTI_ACTION when the user's request contains multiple distinct actions, tasks, questions, or updates. Decompose the request into sequential atomic intents.
Example 1: "tell me weather of tokyo and latest ai news"
{
  "intent": "MULTI_ACTION",
  "actions": [
    {"intent": "WEATHER", "location": "tokyo"},
    {"intent": "REALTIME_QUERY", "query": "latest ai news"}
  ]
}
Example 2: "open notepad and show map of paris"
{
  "intent": "MULTI_ACTION",
  "actions": [
    {"intent": "OPEN", "target": "notepad"},
    {"intent": "MAP", "location": "paris"}
  ]
}
Example 3: "open chrome then what is the time?"
{
  "intent": "MULTI_ACTION",
  "actions": [
    {"intent": "OPEN", "target": "chrome"},
    {"intent": "REALTIME_QUERY", "query": "what is the time"}
  ]
}

== REALTIME_QUERY vs AI_QUERY ==
Use REALTIME_QUERY for: current events, today's date facts, upcoming releases, live scores,
latest news on any topic, "who is the current X", "what happened with X", prices, weather (general).
Use AI_QUERY for: math, coding, definitions, how-things-work, creative writing, timeless knowledge.

== WINDOW_CONTROL FORMAT ==
{ "intent": "WINDOW_CONTROL", "command": "<minimize | maximize | close>", "target": "<app name or empty string if active window>" }

== SEARCH platform detection ==
- "search X on youtube" / "search X" (default=youtube) → SEARCH platform=youtube
- "search X on google" → SEARCH platform=google  
- "search X on spotify" → SEARCH platform=spotify

== WEATHER ==
{ "intent": "WEATHER", "location": "<city or empty string if not mentioned>" }

== NEWS ==
{ "intent": "NEWS", "topic": "<topic or empty string for general news>" }

== SPOTIFY_CONTROL ==
{ "intent": "SPOTIFY_CONTROL", "command": "<play | pause | next | previous | volume_up | volume_down>" }

== MAP ==
{ "intent": "MAP", "location": "<location to display>" }

== REALTIME_QUERY ==
{ "intent": "REALTIME_QUERY", "query": "<user's full question>" }

== AI_QUERY ==
{ "intent": "AI_QUERY", "query": "<user's full question>" }

== NULL ==
If the input is pure noise/gibberish:
{ "intent": null }
"""

ALLOWED_INTENTS = frozenset({
    "OPEN", "SEARCH", "PLAY_MEDIA", "WEB_SEARCH",
    "AI_QUERY", "REALTIME_QUERY", "SCREENSHOT",
    "SYSTEM_STATUS", "WEATHER", "NEWS", "MULTI_ACTION",
    "SPOTIFY_CONTROL", "MAP", "CLARIFICATION", "WINDOW_CONTROL",
})

# Universal recency/currency signals — any of these means the answer may have
# changed recently and MUST come from live retrieval, not static LLM knowledge.
_REALTIME_SIGNALS = (
    # Explicit time references
    "latest", "current", "currently", "recent", "recently", "today", "tonight",
    "this week", "this month", "this year", "right now", "now", "at the moment",
    "as of", "just now", "just released", "just launched", "just announced",
    # Recency intent words
    "new", "newest", "updated", "update", "updates", "upcoming", "soon",
    "trending", "viral", "breaking", "live", "ongoing", "active",
    # Query patterns implying currency
    "who is the", "who won", "who leads", "who heads", "what happened",
    "what's happening", "what is happening", "what are the", "what's new",
    "how is", "how are", "is it still", "did they", "have they", "has",
    # News / events
    "news", "headline", "headlines", "announcement", "launch", "launches",
    "release", "releases", "event", "events", "summit", "conference",
    # Sports / entertainment
    "score", "scores", "match", "schedule", "standings", "leaderboard",
    "box office", "season", "episode", "trailer", "premiere",
    # Tech / products
    "iphone", "samsung", "android", "ai news", "chatgpt", "gemini", "claude",
    "openai", "google", "apple", "microsoft", "meta", "tesla",
    # Finance / market
    "stock", "price", "bitcoin", "crypto", "market", "dow", "nasdaq",
    # People / politics
    "prime minister", "president", "minister", "election", "government",
    "elon", "musk", "trump", "modi", "ceo", "appointed",
    # Sports teams / leagues
    "ipl", "nba", "nfl", "cricket", "world cup", "champions league",
    # Weather (explicit)
    "weather", "temperature", "forecast", "rain", "humidity",
)


def _is_realtime(query: str) -> bool:
    q = query.lower()
    return any(sig in q for sig in _REALTIME_SIGNALS)


def extract_json(text: str) -> str | None:
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start: i + 1]
    return None


def _keyword_fallback(query: str, history: list | None = None) -> dict:
    """Last-resort rule-based fallback when LLM fails."""
    q = query.lower().strip()
    
    # Screenshot fallback
    if "screenshot" in q or "take screenshot" in q or "capture screen" in q:
        return {"intent": "SCREENSHOT"}
        
    # System status fallback
    if "system status" in q or "cpu" in q or "ram" in q or "memory usage" in q or "pc status" in q:
        return {"intent": "SYSTEM_STATUS"}

    # Window controls fallback
    if "minimize window" in q or "minimize active window" in q:
        return {"intent": "WINDOW_CONTROL", "command": "minimize", "target": ""}
    if "maximize window" in q or "maximize active window" in q:
        return {"intent": "WINDOW_CONTROL", "command": "maximize", "target": ""}
    if "close it" in q or "close that" in q or "close window" in q or "close active window" in q:
        return {"intent": "WINDOW_CONTROL", "command": "close", "target": ""}
    if q.startswith("close "):
        target = q.split("close ", 1)[1].strip()
        if target not in ("it", "that", "window", "active window"):
            return {"intent": "WINDOW_CONTROL", "command": "close", "target": target}

    # Pronoun context continuation fallback ("open that again", "open it again")
    if "open that again" in q or "open it again" in q or "launch it again" in q:
        if history:
            for turn in reversed(history):
                if turn.get("role") == "user":
                    content = turn.get("content", "").lower()
                    if "open " in content:
                        target = content.split("open ")[-1].strip()
                        return {"intent": "OPEN", "target": target}
                    elif "start " in content:
                        target = content.split("start ")[-1].strip()
                        return {"intent": "OPEN", "target": target}
                    elif "launch " in content:
                        target = content.split("launch ")[-1].strip()
                        return {"intent": "OPEN", "target": target}

    if any(w in q for w in ("weather", "temperature", "forecast", "rain", "humidity")):
        loc = q.split(" in ")[-1].strip() if " in " in q else ""
        return {"intent": "WEATHER", "location": loc}
    if any(w in q for w in ("news", "headline", "what's happening")):
        return {"intent": "NEWS", "topic": ""}
    
    # Spotify controls fallback
    if "spotify" in q or "song" in q or "music" in q:
        if any(w in q for w in ("pause", "stop", "hold")):
            return {"intent": "SPOTIFY_CONTROL", "command": "pause"}
        if any(w in q for w in ("play", "resume")) and "spotify" in q:
            return {"intent": "SPOTIFY_CONTROL", "command": "play"}
        if any(w in q for w in ("next", "skip")):
            return {"intent": "SPOTIFY_CONTROL", "command": "next"}
        if any(w in q for w in ("prev", "previous", "back")):
            return {"intent": "SPOTIFY_CONTROL", "command": "previous"}
        if "volume up" in q or "louder" in q or "increase volume" in q:
            return {"intent": "SPOTIFY_CONTROL", "command": "volume_up"}
        if "volume down" in q or "quieter" in q or "decrease volume" in q:
            return {"intent": "SPOTIFY_CONTROL", "command": "volume_down"}

    # Fullscreen Map View fallback
    if "map of" in q or "show map" in q or "show me a map" in q or "location of" in q:
        loc = ""
        if "map of" in q:
            loc = q.split("map of")[-1].strip()
        elif "location of" in q:
            loc = q.split("location of")[-1].strip()
        elif "show map" in q:
            loc = q.split("show map")[-1].strip()
        loc = re.sub(r"[^\w\s]", "", loc).strip()
        return {"intent": "MAP", "location": loc}

    # Incomplete command checks
    if q.strip() in ("open", "start", "launch"):
        return {"intent": "CLARIFICATION", "question": "What would you like me to open sir?"}
    if q.strip() in ("play", "listen to"):
        return {"intent": "CLARIFICATION", "question": "What would you like me to play sir?"}

    if "open " in q and ("and search" in q or "then search" in q):
        # Simple compound: "open X and search Y"
        parts = re.split(r"\band\b|\bthen\b", q, maxsplit=1)
        target = parts[0].replace("open", "").strip()
        search_q = re.sub(r"search\s+(for\s+)?", "", parts[1]).strip() if len(parts) > 1 else ""
        return {
            "intent": "MULTI_ACTION",
            "actions": [
                {"intent": "OPEN", "target": target},
                {"intent": "SEARCH", "platform": target, "query": search_q},
            ]
        }
    if "open " in q:
        return {"intent": "OPEN", "target": q.split("open ")[-1].strip()}
    if "play " in q:
        target = q.split("play ")[-1].strip()
        if target == "spotify":
            return {"intent": "SPOTIFY_CONTROL", "command": "play"}
        return {"intent": "PLAY_MEDIA", "query": target}
    if "search " in q:
        sq = re.sub(r"search\s+(for\s+)?", "", q).strip()
        return {"intent": "SEARCH", "platform": "youtube", "query": sq}
    if _is_realtime(q):
        return {"intent": "REALTIME_QUERY", "query": query}
    return {"intent": None}


def parse_intent(query: str, history: list | None = None, preferences: dict | None = None, semantic_facts: dict | None = None, recent_episodes: list | None = None) -> dict:
    try:
        now_ctx = _now_context()
        
        # 1. Format Conversation History
        history_ctx = ""
        if history:
            history_ctx = "== CONVERSATION HISTORY (LATEST TURNS) ==\n"
            for turn in history[-4:]:
                role = "User" if turn.get("role") == "user" else "FRIDAY"
                history_ctx += f"{role}: {turn.get('content')}\n"
            history_ctx += "=========================================\n\n"

        # 2. Format Environment Context
        env_ctx = ""
        if preferences or semantic_facts or recent_episodes:
            env_ctx = "== SYSTEM ENVIRONMENT CONTEXT ==\n"
            if preferences:
                default_city = preferences.get("default_city", "New York")
                favorite_apps = preferences.get("favorite_apps", {})
                fav_app = max(favorite_apps, key=favorite_apps.get) if favorite_apps else "None"
                env_ctx += f"- User Preferred City: {default_city}\n"
                env_ctx += f"- User Mapped Favorite App: {fav_app}\n"
            if semantic_facts:
                env_ctx += "- Relational Facts:\n"
                for k, v in list(semantic_facts.items())[:6]:
                    env_ctx += f"  * {k}: {v}\n"
            if recent_episodes:
                env_ctx += "- Recent Actions Taken:\n"
                for ev in recent_episodes[-3:]:
                    ts = ev.get("timestamp", "")[:19].replace("T", " ")
                    status = "SUCCESS" if ev.get("success") else "FAILED"
                    env_ctx += f"  * [{ts}] Query: {ev.get('query')} -> Intent: {ev.get('intent')} ({status})\n"
            env_ctx += "=================================\n\n"

        prompt = f"""{now_ctx}Usage: {history_ctx}{env_ctx}User Request:
{query}

Return only JSON."""

        response = ask_groq(
            prompt,
            system_prompt=SYSTEM_PROMPT,
            model="llama-3.3-70b-versatile",
        )

        if not response:
            res = _keyword_fallback(query, history)
            res["query"] = query
            return res

        # Strip markdown fences
        response = response.strip().replace("```json", "").replace("```", "").strip()

        clean_json = extract_json(response)
        if not clean_json:
            print("[INTENT] No JSON found, using fallback")
            res = _keyword_fallback(query, history)
            res["query"] = query
            return res

        parsed = json.loads(clean_json)

        if not isinstance(parsed, dict):
            res = _keyword_fallback(query, history)
            res["query"] = query
            return res

        intent = parsed.get("intent")

        # Validate intent
        if intent is not None and intent not in ALLOWED_INTENTS:
            print(f"[INTENT] Unknown intent '{intent}', reclassifying")
            if _is_realtime(query):
                parsed["intent"] = "REALTIME_QUERY"
                parsed["query"] = query
            else:
                parsed["intent"] = "AI_QUERY"
                parsed["query"] = query

        # Upgrade AI_QUERY to REALTIME_QUERY if signals detected
        if parsed.get("intent") == "AI_QUERY" and _is_realtime(query):
            parsed["intent"] = "REALTIME_QUERY"

        # Trim strings
        for key in ("query", "target", "platform", "location", "topic", "question"):
            if key in parsed and isinstance(parsed[key], str):
                parsed[key] = parsed[key].strip()

        # Validate MULTI_ACTION has actions list
        if parsed.get("intent") == "MULTI_ACTION":
            if not isinstance(parsed.get("actions"), list) or len(parsed["actions"]) < 2:
                print("[INTENT] MULTI_ACTION missing actions, using fallback")
                res = _keyword_fallback(query, history)
                res["query"] = query
                return res

        # Always inject the raw query into parsed intent
        parsed["query"] = query
        print(f"[INTENT] {parsed}")
        return parsed

    except Exception as e:
        print(f"[INTENT PARSER ERROR] {e}")
        res = _keyword_fallback(query, history)
        res["query"] = query
        return res