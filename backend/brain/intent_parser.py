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
MULTI_ACTION     → when the user wants TWO OR MORE distinct actions in one request

== MULTI_ACTION FORMAT ==
When the user says something like "open youtube and search marvel comics" or
"open spotify then play lo-fi music", return:
{
  "intent": "MULTI_ACTION",
  "actions": [
    {"intent": "OPEN", "target": "youtube"},
    {"intent": "SEARCH", "platform": "youtube", "query": "marvel comics"}
  ]
}

== REALTIME_QUERY vs AI_QUERY ==
Use REALTIME_QUERY for: current events, today's date facts, upcoming releases, live scores,
latest news on any topic, "who is the current X", "what happened with X", prices, weather (general).
Use AI_QUERY for: math, coding, definitions, how-things-work, creative writing, timeless knowledge.

== SEARCH platform detection ==
- "search X on youtube" / "search X" (default=youtube) → SEARCH platform=youtube
- "search X on google" → SEARCH platform=google  
- "search X on spotify" → SEARCH platform=spotify

== WEATHER ==
{ "intent": "WEATHER", "location": "<city or empty string if not mentioned>" }

== NEWS ==
{ "intent": "NEWS", "topic": "<topic or empty string for general news>" }

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
})

# Keywords that signal a realtime/live query regardless of LLM decision
_REALTIME_SIGNALS = (
    "latest", "current", "today", "tonight", "this week", "right now", "live",
    "upcoming", "next match", "schedule", "score", "trending", "recently",
    "new movie", "new release", "just released", "who won", "who is the",
    "best phone", "iphone", "samsung", "ai news", "cricket", "ipl", "world cup",
    "stock price", "bitcoin", "crypto", "election", "prime minister", "president",
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


def _keyword_fallback(query: str) -> dict:
    """Last-resort rule-based fallback when LLM fails."""
    q = query.lower()
    if any(w in q for w in ("weather", "temperature", "forecast", "rain", "humidity")):
        loc = q.split(" in ")[-1].strip() if " in " in q else ""
        return {"intent": "WEATHER", "location": loc}
    if any(w in q for w in ("news", "headline", "what's happening")):
        return {"intent": "NEWS", "topic": ""}
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
        return {"intent": "PLAY_MEDIA", "query": q.split("play ")[-1].strip()}
    if "search " in q:
        sq = re.sub(r"search\s+(for\s+)?", "", q).strip()
        return {"intent": "SEARCH", "platform": "youtube", "query": sq}
    if _is_realtime(q):
        return {"intent": "REALTIME_QUERY", "query": query}
    return {"intent": None}


def parse_intent(query: str) -> dict:
    try:
        now_ctx = _now_context()
        prompt = f"""{now_ctx}

User Request:
{query}

Return only JSON."""

        response = ask_groq(
            prompt,
            system_prompt=SYSTEM_PROMPT,
            model="llama-3.3-70b-versatile",
        )

        if not response:
            return _keyword_fallback(query)

        # Strip markdown fences
        response = response.strip().replace("```json", "").replace("```", "").strip()

        clean_json = extract_json(response)
        if not clean_json:
            print("[INTENT] No JSON found, using fallback")
            return _keyword_fallback(query)

        parsed = json.loads(clean_json)

        if not isinstance(parsed, dict):
            return _keyword_fallback(query)

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
        for key in ("query", "target", "platform", "location", "topic"):
            if key in parsed and isinstance(parsed[key], str):
                parsed[key] = parsed[key].strip()

        # Validate MULTI_ACTION has actions list
        if parsed.get("intent") == "MULTI_ACTION":
            if not isinstance(parsed.get("actions"), list) or len(parsed["actions"]) < 2:
                print("[INTENT] MULTI_ACTION missing actions, using fallback")
                return _keyword_fallback(query)

        print(f"[INTENT] {parsed}")
        return parsed

    except Exception as e:
        print(f"[INTENT PARSER ERROR] {e}")
        return _keyword_fallback(query)