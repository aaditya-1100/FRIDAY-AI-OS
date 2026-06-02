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
YOUTUBE_TOPIC_SEARCH → search for a topic or keywords on YouTube (e.g. "search YouTube for AI news", "look up AI news on YouTube", "find AI news videos")
LATEST_CREATOR_VIDEO → play the latest long-form video upload by a specific creator (e.g. "play Mark Rober's latest video", "show Mark Rober's newest upload")
LATEST_CREATOR_SHORT → play the latest Shorts upload by a specific creator (e.g. "open latest short by Mark Rober", "show Mark Rober's newest short")
VIDEO_BY_TITLE   → play a YouTube video with a specific title (e.g. "open video titled X", "play video titled X", "find the YouTube video X", "open X on YouTube")
CHANNEL_OPEN     → open a creator's YouTube channel page (e.g. "open Mark Rober's channel")
PLAY_SEARCH_RESULT → play a specific search result index (e.g. "play the first search result", "play the second result")
SEARCH           → search on a specific platform (youtube, google, spotify)
PLAY_MEDIA       → play music, watch videos on Spotify or other music platforms.
WEB_SEARCH       → open a Google search in browser
REALTIME_QUERY   → ANY question about current/recent/upcoming events, weather, news, sports,
                   movies, people, prices, trends, live scores, latest updates, current year facts
                   — basically anything where the answer might have changed in the last year
AI_QUERY         → general conversation, opinions, coding help, explanations (timeless facts)
SCREENSHOT       → take a screenshot
SCREEN_UNDERSTANDING → explain active screen contents, derivations, graphs, code, active websites or videos currently visible on screen. Use this when the user asks "what is on my screen?", "explain this derivation", "summarize this video", "what is this webpage?", "explain this graph", "analyze this visible UI", etc.
SYSTEM_STATUS    → CPU, RAM, disk usage queries
WEATHER          → explicit weather/temperature/forecast/rain/humidity questions
NEWS             → explicit news/headlines requests
SPOTIFY_CONTROL  → play, pause, next, skip, volume up, volume down on Spotify locally
MAP_LOCATION     → display a high-tech tactical map of a specific location (e.g. "show map of Paris", "open Paris on the map", "display Paris", "show Paris location")
MAP_ROUTE        → calculate and display route/directions between origin and destination (e.g. "show route from Paris to London", "route Paris to London", "directions from Paris to London", "navigate Paris to London")
PLACE_DISCOVERY   → search for nearby places or specific place locations (e.g. "find cafes near me", "show airports near Paris")
TRAVEL_ETA        → get travel duration / ETA / distance estimation (e.g. "how long to drive to London", "how far is Paris")
MAP_FOLLOWUP     → active map session queries about traffic, zoom, satellite mode, cities crossed, ETA, or distance (e.g. "is there traffic?", "show satellite view", "how long will it take?", "what cities will I cross?")
WINDOW_CONTROL   → minimize, maximize, or close the active window, or close/exit a specific application (e.g. "close it", "close notepad", "minimize window")
MULTI_ACTION     → when the user wants TWO OR MORE distinct actions, questions, or tasks in one request
CLARIFICATION    → when a command is incomplete (e.g. "open" or "play" without a target) and needs a follow-up question.
SET_REMINDER     → remind user to do something at a specific relative time (e.g. "remind me to drink water in 5 minutes")
SET_TIMER        → start a countdown timer (e.g. "set a timer for 10 minutes")
STOPWATCH_CONTROL → start, stop, pause, resume, reset, or show stopwatch (e.g. "start stopwatch")
SET_ALARM        → set an alarm for a specific clock time (e.g. "wake me up at 6 AM")
SET_SCHEDULED_TASK → schedule a future task/reminder for a specific date (e.g. "remind me tomorrow to call mom")
SET_RECURRING_REMINDER → set a repeating daily/weekly reminder (e.g. "remind me every day at 9 AM to take vitamins")
LIST_REMINDERS   → list all active reminders, timers, and alarms (e.g. "what are my active reminders?")
CANCEL_REMINDER  → cancel/delete an active reminder or timer by description (e.g. "cancel reminder to drink water")
CASUAL_CHAT      → conversational greetings, hello, how are you, greeting check-ins, simple casual chat (e.g. "hello", "hi friday", "good morning", "friday are you there", "hello friday")

== STATEFUL & PRONOUN CONTEXT RESOLUTION ==
You are provided with CONVERSATION HISTORY showing the latest turns. Use this history to resolve pronouns ("it", "that", "there", "them", "him", "her") or contextual commands:
- For follow-up questions containing pronouns or implicit targets (e.g. "how old is he?", "what is its population?", "who is she married to?"), resolve the pronoun/implicit target against the history and fully rewrite the "query" string in your JSON response to be explicit (e.g. rewrite "how old is he?" to "how old is Keir Starmer"). This is critical for follow-up awareness.
- If the user says "open that again", look at what was opened in the history (e.g. if the assistant opened Notepad, return {"intent": "OPEN", "target": "notepad"}).
- If the user says "what's the weather there", look at the last mentioned location/city in the history and map it to {"intent": "WEATHER", "location": "<city>"}.
- If the user says "also search marvel", look at the previous platform (e.g., youtube) and combine them or route accordingly.

== SYSTEM ENVIRONMENT CONTEXT RESOLUTION ==
You are provided with SYSTEM ENVIRONMENT CONTEXT (preferred location, favorite app, relational facts, and recent episodic execution history).
- If the user says "what's the weather", and no location is mentioned, look at the "User Preferred City" (e.g., "Kashipur, Uttarakhand, India") in the environment context before falling back to empty.
- If the user says "open my favorite app" or "start it", look at the "User Mapped Favorite App" field.

== CONVERSATIONAL IMPLICATIONS & IMPLICIT INTENTS ==
Analyze natural conversational implications to map implicit phrases to their correct action intents rather than treating them literally:
- "it is too loud" / "turn it down" / "make it quiet" -> {"intent": "SPOTIFY_CONTROL", "command": "volume_down"}
- "it is too quiet" / "turn it up" / "make it louder" -> {"intent": "SPOTIFY_CONTROL", "command": "volume_up"}
- "write this down" / "take a note" / "open a blank page" -> {"intent": "OPEN", "target": "notepad"}
- "show me the screen" / "capture the screen" / "take a picture of this" -> {"intent": "SCREENSHOT"}
- "how is my pc doing" / "check computer resources" / "is my cpu hot" -> {"intent": "SYSTEM_STATUS"}
- "show me the map" / "where is this place" -> {"intent": "MAP_LOCATION", "location": "<location>"}

== UNCONVENTIONAL PHRASING, FUZZY COMMANDS & CONTINUITY ==
Fuzzy commands, slang, and conversational corrections must be resolved with absolute semantic accuracy:
- If the user corrects themselves (e.g. "actually scratch that, close this window" or "no wait, open chrome instead"), resolve the latest corrected command as the target (e.g., {"intent": "OPEN", "target": "chrome"}).
- If fumbled speech or interruptions occur (e.g. "open spoti- spoti... wait, open Spotify"), resolve the core intended target as Spotify: {"intent": "OPEN", "target": "spotify"}.
- Unconventional music requests (e.g. "play some Subh vibe" or "put on Karan Aujla's latest") map to PLAY_MEDIA with the resolved query (e.g. {"intent": "PLAY_MEDIA", "query": "Subh"}).
- Pronoun corrections (e.g. "no wait, show map of Delhi instead of Mumbai") must ignore the earlier location and resolve Delhi: {"intent": "MAP_LOCATION", "location": "Delhi"}.

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
    {"intent": "MAP_LOCATION", "location": "paris"}
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

== PLAY_MEDIA FORMAT ==
{
  "intent": "PLAY_MEDIA",
  "creator": "<creator, artist, or band name, or null>",
  "title": "<song or video title, or null>",
  "platform": "spotify",
  "query": "<clean query>"
}

== YOUTUBE CAPABILITIES ==
- YOUTUBE_TOPIC_SEARCH: { "intent": "YOUTUBE_TOPIC_SEARCH", "query": "<search query>" }
- LATEST_CREATOR_VIDEO: { "intent": "LATEST_CREATOR_VIDEO", "creator": "<creator name>" }
- LATEST_CREATOR_SHORT: { "intent": "LATEST_CREATOR_SHORT", "creator": "<creator name>" }
- VIDEO_BY_TITLE: { "intent": "VIDEO_BY_TITLE", "title": "<video title>", "creator": "<creator name or null>" }
- CHANNEL_OPEN: { "intent": "CHANNEL_OPEN", "creator": "<creator name>" }
- PLAY_SEARCH_RESULT: { "intent": "PLAY_SEARCH_RESULT", "query": "<search query>", "index": <0-based index> }

== WEATHER ==
{ "intent": "WEATHER", "location": "<city or empty string if not mentioned>" }

== NEWS ==
{ "intent": "NEWS", "topic": "<topic or empty string for general news>" }

== SPOTIFY_CONTROL ==
{ "intent": "SPOTIFY_CONTROL", "command": "<play | pause | next | previous | volume_up | volume_down>" }

== MAP_LOCATION ==
{ "intent": "MAP_LOCATION", "location": "<location to display>" }
== MAP_ROUTE ==
{ "intent": "MAP_ROUTE", "origin": "<city or empty string>", "destination": "<destination city>", "mode": "<driving | walking | bicycling | transit>" }
== PLACE_DISCOVERY ==
{ "intent": "PLACE_DISCOVERY", "query": "<what to find>", "location": "<where>", "place_type": "<type e.g. cafe, airport>" }
== TRAVEL_ETA ==
{ "intent": "TRAVEL_ETA", "origin": "<origin>", "destination": "<destination>", "mode": "<mode>" }
== MAP_FOLLOWUP ==
{ "intent": "MAP_FOLLOWUP", "action": "<eta | distance | cities_crossed | fastest_route | traffic | satellite_view | street_view | zoom_in | zoom_out | nearby_places>" }

== TEMPORAL SYSTEMS ==
- SET_REMINDER: { "intent": "SET_REMINDER", "text": "<what to remind>", "time_expr": "<natural time expression e.g. 'in 5 minutes'>" }
- SET_TIMER: { "intent": "SET_TIMER", "duration_expr": "<duration e.g. '10 minutes'>" }
- STOPWATCH_CONTROL: { "intent": "STOPWATCH_CONTROL", "command": "<start | stop | pause | resume | reset | status>" }
- SET_ALARM: { "intent": "SET_ALARM", "time_expr": "<alarm time e.g. '6 AM'>" }
- SET_SCHEDULED_TASK: { "intent": "SET_SCHEDULED_TASK", "task": "<task/event description>", "time_expr": "<target date/time expression e.g. 'tomorrow at 5 PM'>" }
- SET_RECURRING_REMINDER: { "intent": "SET_RECURRING_REMINDER", "text": "<reminder text>", "recurrence": "<daily | weekly>", "time_expr": "<time expression e.g. '9 AM'>" }
- LIST_REMINDERS: { "intent": "LIST_REMINDERS" }
- CANCEL_REMINDER: { "intent": "CANCEL_REMINDER", "target": "<text of reminder/timer to delete>" }
- CASUAL_CHAT: { "intent": "CASUAL_CHAT", "query": "<user's query>" }

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
    "SET_REMINDER", "SET_TIMER", "STOPWATCH_CONTROL", "SET_ALARM",
    "SET_SCHEDULED_TASK", "SET_RECURRING_REMINDER", "LIST_REMINDERS",
    "CANCEL_REMINDER", "MAP_ROUTE", "PLACE_DISCOVERY", "TRAVEL_ETA",
    "SCREEN_UNDERSTANDING", "MAP_FOLLOWUP",
    "YOUTUBE_TOPIC_SEARCH", "LATEST_CREATOR_VIDEO", "LATEST_CREATOR_SHORT",
    "VIDEO_BY_TITLE", "CHANNEL_OPEN", "PLAY_SEARCH_RESULT", "MAP_LOCATION",
    "CASUAL_CHAT"
})

# Universal recency/currency signals — any of these means the answer may have
# changed recently and MUST come from live retrieval, not static LLM knowledge.
# CRITICAL: These signals MUST NOT trigger on casual greetings or conversational queries.
_REALTIME_SIGNALS = (
    # Explicit time references
    "latest", "current", "currently", "recent", "recently", "today", "tonight",
    "this week", "this month", "this year", "right now", "now", "at the moment",
    "as of", "just now", "just released", "just launched", "just announced",
    # Recency intent words
    "new", "newest", "updated", "update", "updates", "upcoming", "soon",
    "trending", "viral", "breaking", "live", "ongoing", "active",
    # Query patterns implying currency (EXCLUDING casual greetings)
    "who is the", "who won", "who leads", "who heads", "what happened",
    "what's happening", "what is happening", "what are the", "what's new",
    # REMOVED: "how is", "how are" - these trigger on casual greetings like "how are you"
    "is it still", "did they", "have they", "has",
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
    
    # ── Casual Greetings / Chat Fallbacks ───────────────────────────────────
    greeting_words = {"hello", "hi", "hey", "sup", "yo", "good morning", "good afternoon", "good evening", "good night", "friday are you there", "are you there", "are you awake", "you there", "hello friday", "hi friday", "hey friday"}
    if q in greeting_words or q.replace("?", "").strip() in greeting_words or q.rstrip("!").strip() in greeting_words:
        return {"intent": "CASUAL_CHAT", "query": query}
    
    # ── Temporal Systems Fallbacks ──────────────────────────────────────────
    # Recurring reminder
    if "every day" in q or "daily" in q or "every week" in q:
        if "remind" in q:
            text = q.split("to ", 1)[1].strip() if "to " in q else q
            time_expr = q.split("to ", 1)[0].replace("remind me", "").replace("remind", "").strip()
            return {"intent": "SET_RECURRING_REMINDER", "text": text, "recurrence": "daily", "time_expr": time_expr}

    # Scheduled task / Tomorrow
    if "tomorrow" in q or "next " in q:
        if "remind" in q:
            task = q.split("to ", 1)[1].strip() if "to " in q else q
            time_expr = q.split("to ", 1)[0].replace("remind me", "").replace("remind", "").strip()
            return {"intent": "SET_SCHEDULED_TASK", "task": task, "time_expr": time_expr}

    # General reminder
    if "remind me" in q or "remind" in q:
        text = q.split("to ", 1)[1].strip() if "to " in q else q
        time_expr = ""
        for word in ("in ", "at ", "after "):
            if word in text:
                parts = text.rsplit(word, 1)
                text = parts[0].strip()
                time_expr = word + parts[1].strip()
                break
        if not time_expr:
            time_expr = "in 1 minute"
        return {"intent": "SET_REMINDER", "text": text, "time_expr": time_expr}

    # Timer countdown
    if "timer for" in q or "timer of" in q:
        dur = q.split("for ", 1)[1].strip() if "for " in q else (q.split("of ", 1)[1].strip() if "of " in q else "5 minutes")
        return {"intent": "SET_TIMER", "duration_expr": dur}
    elif q.startswith("timer ") or q.endswith(" timer"):
        dur = q.replace("timer", "").strip()
        if dur:
            return {"intent": "SET_TIMER", "duration_expr": dur}

    # Alarm
    if "wake me up" in q or "alarm for" in q or "alarm at" in q:
        time_expr = "9 AM"
        for word in ("at ", "for "):
            if word in q:
                time_expr = q.split(word, 1)[1].strip()
                break
        return {"intent": "SET_ALARM", "time_expr": time_expr}

    # Stopwatch
    if "stopwatch" in q or "stop watch" in q:
        cmd = "start"
        if any(w in q for w in ("stop", "end")):
            cmd = "stop"
        elif any(w in q for w in ("pause", "hold")):
            cmd = "pause"
        elif any(w in q for w in ("resume", "continue")):
            cmd = "resume"
        elif any(w in q for w in ("reset", "clear")):
            cmd = "reset"
        elif "status" in q or "show" in q or "elapsed" in q:
            cmd = "status"
        return {"intent": "STOPWATCH_CONTROL", "command": cmd}

    # List reminders
    if any(w in q for w in ("list reminders", "list my reminders", "what are my reminders", "show reminders", "show timers", "list timers")):
        return {"intent": "LIST_REMINDERS"}

    # Cancel reminder
    if "cancel reminder" in q or "delete reminder" in q or "cancel timer" in q or "delete timer" in q:
        target = ""
        for word in ("cancel reminder ", "delete reminder ", "cancel timer ", "delete timer "):
            if word in q:
                target = q.split(word, 1)[1].strip()
                break
        return {"intent": "CANCEL_REMINDER", "target": target}

    # Screenshot fallback
    if "screenshot" in q or "take screenshot" in q:
        return {"intent": "SCREENSHOT"}

    # Screen understanding fallback
    screen_words = {"what's on my screen", "what is on my screen", "explain my screen", "explain this derivation", "explain this graph", "summarize this video", "what is this website", "what's on screen", "explain what's on my screen", "explain what you see on my screen"}
    if any(w in q for w in screen_words):
        return {"intent": "SCREEN_UNDERSTANDING"}
        
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

    # ── MAPS & YOUTUBE CAPABILITY MATCHING ──────────────────────────────────
    q_clean = q.replace("'s", "").replace("’s", "").strip()
    
    # 1. MAPS ROUTING CAPABILITY MATCHING
    # Phrasings: "Show route from Paris to London", "Route Paris to London", "Directions from Paris to London", "Navigate Paris to London"
    route_keywords = {"route", "directions", "navigate", "way to", "drive to", "path from", "from "}
    is_route = any(k in q_clean for k in route_keywords) and " to " in q_clean
    if is_route:
        origin = ""
        destination = ""
        # Match "from X to Y"
        from_to_match = re.search(r"from\s+(.+?)\s+to\s+(.+)", q_clean, re.IGNORECASE)
        if from_to_match:
            origin = from_to_match.group(1).strip()
            destination = from_to_match.group(2).strip()
        else:
            # Match "X to Y"
            to_match = re.search(r"(?:route|navigate|directions|way|drive|path)?\s*(.+?)\s+to\s+(.+)", q_clean, re.IGNORECASE)
            if to_match:
                origin = to_match.group(1).strip()
                destination = to_match.group(2).strip()
                
        # Clean up any leftover route action verbs from origin
        for verb in ("show route", "route", "directions", "navigate", "way", "drive", "path"):
            origin = re.sub(rf"\b{verb}\b", "", origin, flags=re.IGNORECASE).strip()
            
        destination = re.sub(r"[^\w\s]", "", destination).strip()
        origin = re.sub(r"[^\w\s]", "", origin).strip()
        
        if destination:
            return {
                "intent": "MAP_ROUTE",
                "origin": origin,
                "destination": destination,
                "mode": "driving"
            }

    # 2. MAPS LOCATION CAPABILITY MATCHING
    # Phrasings: "Show map of Paris", "Open Paris on the map", "Display Paris", "Take me to Paris on the map", "Show Paris location", "Where is Paris"
    map_keywords = {"map of", "on the map", "location of", "show map", "display", "where is", "take me to", "openstreetmap"}
    is_map = any(k in q_clean for k in map_keywords) or (("location" in q_clean or "map" in q_clean) and any(w in q_clean for w in ("show", "open", "display", "where", "find")))
    if is_map:
        loc = q_clean
        for word in ("show map of", "show map", "show location of", "location of", "open", "display", "take me to", "on the map", "where is", "show me a map of", "show me", "show", "map", "location"):
            loc = re.sub(rf"\b{word}\b", "", loc, flags=re.IGNORECASE)
        loc = re.sub(r"[^\w\s]", "", loc).strip()
        if loc:
            return {"intent": "MAP_LOCATION", "location": loc}

    # ── MAP_FOLLOWUP zero-LLM fast-path ──────────────────────────────────────
    try:
        from core.pipeline import context_manager
        is_followup, followup_action, followup_extra = context_manager.detect_map_followup(query)
        if is_followup and followup_action:
            result = {"intent": "MAP_FOLLOWUP", "action": followup_action}
            result.update(followup_extra)
            print(f"[INTENT FAST-PATH] MAP_FOLLOWUP detected: action={followup_action}")
            return result
    except Exception as _mfe:
        pass

    # Incomplete command checks
    if q.strip() in ("open", "start", "launch"):
        return {"intent": "CLARIFICATION", "question": "What would you like me to open sir?"}
    if q.strip() in ("play", "listen to"):
        return {"intent": "CLARIFICATION", "question": "What would you like me to play sir?"}

    # 3. YOUTUBE CAPABILITY MATCHING
    is_youtube = any(w in q_clean for w in ("youtube", "yt", "video", "short", "shorts", "reel", "channel", "play", "watch", "look up", "upload", "uploads", "lecture", "lectures", "song", "songs", "clip", "clips", "highlight", "highlights", "trailer", "trailers", "tutorial", "tutorials", "show me"))
    if is_youtube:
        # A. Shorts Capability
        if any(w in q_clean for w in ("short", "shorts", "reel")):
            creator = q_clean
            for term in ("open latest short by", "show", "newest short", "play latest shorts upload from", "play latest short by", "latest short by", "newest short of", "shorts", "short", "reel", "play", "open", "show me"):
                creator = re.sub(rf"\b{term}\b", "", creator, flags=re.IGNORECASE)
            creator = re.sub(r"[^\w\s]", "", creator).strip()
            return {"intent": "LATEST_CREATOR_SHORT", "creator": creator}

        # B. Latest Creator Video Capability
        elif any(w in q_clean for w in ("latest", "newest", "recent")) and any(w in q_clean for w in ("video", "upload", "content")):
            creator = q_clean
            for term in ("open latest video by", "show", "newest upload", "play", "latest video of", "newest video from", "newest video of", "latest upload of", "latest video by", "video", "upload", "latest", "newest", "recent", "open", "show me"):
                creator = re.sub(rf"\b{term}\b", "", creator, flags=re.IGNORECASE)
            creator = re.sub(r"[^\w\s]", "", creator).strip()
            return {"intent": "LATEST_CREATOR_VIDEO", "creator": creator}

        # C. Video By Title Capability
        elif "titled" in q_clean or "called" in q_clean or "named" in q_clean or q_clean.startswith("play video ") or q_clean.startswith("open video ") or "youtube video" in q_clean:
            title = q_clean
            creator = None
            by_match = re.search(r"(?:titled|called|named)\s+(.+?)\s+\b(by|from)\s+(.+)", q_clean, re.IGNORECASE)
            if by_match:
                title = by_match.group(1).strip()
                creator = by_match.group(3).strip()
            else:
                for term in ("play video titled", "open video titled", "play video called", "open video called", "play video named", "open video named", "play video", "open video", "play the youtube video", "play youtube video", "youtube video", "find the", "find", "titled", "called", "named"):
                    title = re.sub(rf"\b{term}\b", "", title, flags=re.IGNORECASE)
            title = re.sub(r"[^\w\s]", "", title).strip()
            return {"intent": "VIDEO_BY_TITLE", "title": title, "creator": creator}

        # D. Channel Open Capability
        elif "channel" in q_clean or "page" in q_clean:
            creator = q_clean
            for term in ("open", "go to", "show", "channel", "page", "youtube channel", "youtube page"):
                creator = re.sub(rf"\b{term}\b", "", creator, flags=re.IGNORECASE)
            creator = re.sub(r"[^\w\s]", "", creator).strip()
            return {"intent": "CHANNEL_OPEN", "creator": creator}

        # E. Play Search Result Capability
        elif any(w in q_clean for w in ("first", "second", "third", "1st", "2nd", "3rd")) and "result" in q_clean:
            idx = 0
            if "second" in q_clean or "2nd" in q_clean:
                idx = 1
            elif "third" in q_clean or "3rd" in q_clean:
                idx = 2
            return {"intent": "PLAY_SEARCH_RESULT", "query": q_clean, "index": idx}

        # F. YouTube Topic Search Capability
        else:
            clean_search = q_clean
            verbs = [
                "open youtube results for", "search youtube for", "videos covering",
                "search youtube", "videos about", "youtube for", "on youtube",
                "videos of", "videos on", "video about", "video of", "video on",
                "show me", "look up", "videos", "search", "video", "find", "show"
            ]
            for verb in sorted(verbs, key=len, reverse=True):
                clean_search = re.sub(rf"\b{verb}\b", "", clean_search, flags=re.IGNORECASE)
            clean_search = re.sub(r"[^\w\s]", "", clean_search).strip()
            return {"intent": "YOUTUBE_TOPIC_SEARCH", "query": clean_search}

    # 4. GENERAL OPEN / PLAY / SEARCH FALLBACKS
    # Simple compound: "open X and search Y"
    if "open " in q and ("and search" in q or "then search" in q):
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
        target = q.split("open ")[-1].strip()
        if any(term in target.lower() for term in ("video", "song", "music", "youtube")):
            return {"intent": "PLAY_MEDIA", "query": target}
        return {"intent": "OPEN", "target": target}
    if "play " in q:
        target = q.split("play ")[-1].strip()
        if target == "spotify":
            return {"intent": "SPOTIFY_CONTROL", "command": "play"}
        return {"intent": "PLAY_MEDIA", "query": target}
    if "search " in q:
        sq = re.sub(r"^search\s+(for\s+)?", "", q).strip()
        platform = "youtube"  # default
        for _p in ("youtube", "yt", "google", "spotify"):
            if sq.lower().startswith(_p):
                platform = "youtube" if _p in ("youtube", "yt") else _p
                sq = re.sub(rf"^{_p}\s+(for\s+)?", "", sq, flags=re.IGNORECASE).strip()
                break
        return {"intent": "SEARCH", "platform": platform, "query": sq}

    # ── GENERAL KEYWORD FALLBACKS (LOW-PRIORITY) ───────────────────────────
    if any(w in q for w in ("weather", "temperature", "forecast", "rain", "humidity")):
        loc = q.split(" in ")[-1].strip() if " in " in q else ""
        return {"intent": "WEATHER", "location": loc}
    if any(w in q for w in ("news", "headline", "what's happening")):
        from brain.entity_tracker import extract_all_entities
        entities = extract_all_entities(query)
        topic = ""
        # 1. Named Entity Extraction & Topic Classification
        for ent_text, ent_type in entities:
            if ent_type in ("topic", "person", "location") and ent_text.lower() not in ("news", "headline", "headlines", "briefing", "what's happening"):
                topic = ent_text
                break
        # 2. Universal keyword-stripping fallback
        if not topic:
            topic = q
            for remove in ("news", "headlines", "headline", "what's happening", "what is happening", "today's", "today", "latest", "hot", "current", "about", "on", "for"):
                topic = re.sub(rf"\b{remove}\b", "", topic, flags=re.IGNORECASE)
            topic = re.sub(r"[^\w\s]", "", topic).strip()
        
        return {"intent": "NEWS", "topic": topic.title() if topic else ""}
    
    # Spotify / Volume controls fallback
    if "spotify" in q or "song" in q or "music" in q or any(w in q for w in ("volume", "loud", "quiet", "louder", "quieter", "turn it up", "turn it down")):
        if any(w in q for w in ("link", "connect", "authorize")):
            return {"intent": "SPOTIFY_CONTROL", "command": "link"}
        if any(w in q for w in ("pause", "stop", "hold")):
            return {"intent": "SPOTIFY_CONTROL", "command": "pause"}
        if any(w in q for w in ("play", "resume")) and "spotify" in q:
            return {"intent": "SPOTIFY_CONTROL", "command": "play"}
        if any(w in q for w in ("next", "skip")):
            return {"intent": "SPOTIFY_CONTROL", "command": "next"}
        if any(w in q for w in ("prev", "previous", "back")):
            return {"intent": "SPOTIFY_CONTROL", "command": "previous"}
        if any(w in q for w in ("up", "louder", "increase", "quietest", "too quiet", "turn it up")):
            return {"intent": "SPOTIFY_CONTROL", "command": "volume_up"}
        if any(w in q for w in ("down", "quieter", "decrease", "loudest", "too loud", "turn it down")):
            return {"intent": "SPOTIFY_CONTROL", "command": "volume_down"}

    # Note / write this down fallback
    if any(w in q for w in ("write this down", "take a note", "open a blank page", "open notepad", "start notepad")):
        return {"intent": "OPEN", "target": "notepad"}

    # Safe default fallback instead of returning None
    if _is_realtime(query):
        return {"intent": "REALTIME_QUERY", "query": query}
    return {"intent": "AI_QUERY", "query": query}


def parse_intent(query: str, history: list | None = None, preferences: dict | None = None, semantic_facts: dict | None = None, recent_episodes: list | None = None, planner_hint: str | None = None) -> dict:
    try:
        # Direct check for Memory/Identity routing bypass
        if planner_hint == "MEMORY":
            print("[INTENT FAST-PATH] Direct Memory-First Gate matched. Routing to AI_QUERY.")
            return {"intent": "AI_QUERY", "query": query}

        # MAP_FOLLOWUP fast-path check (before LLM, inside parse_intent)
        try:
            from core.pipeline import context_manager
            is_followup, followup_action, followup_extra = context_manager.detect_map_followup(query)
            if is_followup and followup_action:
                result = {"intent": "MAP_FOLLOWUP", "action": followup_action, "query": query}
                result.update(followup_extra)
                print(f"[INTENT FAST-PATH] MAP_FOLLOWUP inside parse_intent: action={followup_action}")
                return result
        except Exception:
            pass

        # Unconditionally enrich self-referential pronouns first
        self_replacements = {
            r"\byourself\b": "FRIDAY",
            r"\byou\b": "FRIDAY",
            r"\byour\b": "FRIDAY's",
            r"\byou're\b": "FRIDAY is",
            r"\bthe\s+assistant\b": "FRIDAY",
        }
        for pattern, replacement in self_replacements.items():
            query = re.sub(pattern, replacement, query, flags=re.IGNORECASE)

        # Direct check for opening PW or Physics Wallah (excluding multi-actions)
        norm_q = query.lower().strip().rstrip("?!. ")
        has_conjunction = any(c in norm_q for c in (" and ", " then ", " also ", ", "))
        if not has_conjunction:
            match = re.search(r"\b(open|start|launch|go\s+to|show|view)?\s*\b(pw|physics\s+wallah)\b", norm_q)
            if match:
                is_question = any(w in norm_q for w in ("what", "how", "who", "why", "where", "info", "about"))
                if not is_question:
                    matched_target = match.group(2).lower().strip()
                    target = "physics wallah" if "physics" in matched_target else "pw"
                    print(f"[INTENT FAST-PATH] Direct PW/Physics Wallah open intercepted: {target}")
                    return {"intent": "OPEN", "target": target, "query": query}

        # Direct check for Spotify linking
        if not has_conjunction:
            if norm_q in ("link spotify", "connect spotify", "authorize spotify", "connect to spotify", "link to spotify"):
                print("[INTENT FAST-PATH] Spotify link request intercepted.")
                return {"intent": "SPOTIFY_CONTROL", "command": "link", "query": query}

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
                default_city = preferences.get("default_city", "Kashipur, Uttarakhand, India")
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

        hint_ctx = ""
        if planner_hint:
            hint_ctx = f"== PLANNER PRE-ROUTING HINT ==\nThe system pre-routing planner suggests this request relates to: {planner_hint}.\nUse this to guide your intent classification.\n===============================\n\n"

        pronoun_reminder = ""
        if history_ctx:
            pronoun_reminder = "\nCRITICAL: If the User Request uses pronouns (he, she, it, they, him, her, there) or refers contextually to a previous topic, you MUST resolve them against the CONVERSATION HISTORY and rewrite the \"query\" field in your JSON response to be fully explicit (e.g. rewrite \"how old is he?\" to \"how old is Keir Starmer\").\n"

        prompt = f"""{now_ctx}Usage: {history_ctx}{env_ctx}{hint_ctx}{pronoun_reminder}User Request:
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

        # If Groq returned a quota exhaustion message, fall back to keyword routing
        # so commands still work (open, play, search) even during quota limits
        if "short breather" in response or "rate_limit_exceeded" in response.lower():
            print(f"[INTENT QUOTA FALLBACK] Groq quota hit — routing via keyword fallback for: '{query}'")
            res = _keyword_fallback(query, history)
            res["query"] = query
            # Mark as quota-limited so pipeline can relay the quota message to TTS
            res["_quota_limited"] = True
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

        # Only inject the raw query if the LLM didn't already populate/rewrite a query field.
        if "query" not in parsed or not parsed["query"]:
            parsed["query"] = query
            
        parsed = validate_intent_sanity(parsed, query)
        print(f"[INTENT] {parsed}")
        return parsed

    except Exception as e:
        print(f"[INTENT PARSER ERROR] {e}")
        res = _keyword_fallback(query, history)
        res["query"] = query
        res = validate_intent_sanity(res, query)
        return res


def validate_intent_sanity(intent_data: dict, query: str) -> dict:
    """
    Validates the resolved intent against the raw query.
    Protects against false positives and dangerous actions (e.g. closing window on brightness query).
    Safe fallbacks to AI_QUERY or CLARIFICATION on mismatch.
    Calculates command confidence and intercepts vague/low-confidence commands.
    """
    intent = intent_data.get("intent")
    if not intent:
        return intent_data
        
    q = query.lower().strip()
    
    # Conversational follow-up safety override
    conversational_followup_indicators = [
        r"\b(wasn'?t|isn'?t|doesn'?t|didn'?t|aren'?t|weren'?t|don'?t|won'?t|couldn'?t|shouldn'?t|wouldn'?t|is|was|does|did|has|had|are|were)\s+(it|that|this|there|he|she|they|them|his|her)\b",
        r"\b(founded\s+by|created\s+by|born\s+in|located\s+in|near\s+the|close\s+to)\b",
        r"\b(wasn'?t\s+that|isn'?t\s+that|wasn'?t\s+it|isn'?t\s+it)\b"
    ]
    is_followup = any(re.search(pat, q) for pat in conversational_followup_indicators)
    if is_followup:
        print(f"[SANITY INTENT FILTER] Conversational follow-up query detected: '{query}'")
        target_intent = "REALTIME_QUERY" if _is_realtime(query) else "AI_QUERY"
        return {"intent": target_intent, "query": query}
    
    # ── Universal Command Confidence System ─────────────────────────────
    command_intents = {"OPEN", "WINDOW_CONTROL", "SPOTIFY_CONTROL", "PLAY_MEDIA", "MAP", "SET_REMINDER", "SET_TIMER", "SET_ALARM"}
    if intent in command_intents:
        # Calculate Target Clarity
        target_clarity = 1.0
        vague_targets = {"that thing", "it", "something", "this", "that", "page", "application", "program", "folder", "drive", "file"}
        
        target = ""
        if intent == "OPEN":
            target = intent_data.get("target", "").lower().strip()
        elif intent == "PLAY_MEDIA":
            target = intent_data.get("query", "").lower().strip()
        elif intent == "MAP":
            target = intent_data.get("location", "").lower().strip()
        elif intent == "WINDOW_CONTROL":
            target = intent_data.get("target", "").lower().strip()
            
        if intent in ("OPEN", "PLAY_MEDIA", "MAP"):
            if not target or target in vague_targets:
                target_clarity = 0.0
                
        # Calculate Verb Clarity
        verb_clarity = 1.0
        command_verbs = {"open", "launch", "start", "close", "quit", "exit", "minimize", "maximize", "play", "pause", "resume", "set", "lock", "shutdown", "restart", "sleep", "mute", "unmute"}
        if not any(v in q for v in command_verbs):
            verb_clarity = 0.5
            
        confidence = target_clarity * verb_clarity
        
        # If low confidence, intercept
        if confidence < 0.7:
            # If no command verb was actually in the query, it was a misclassification -> fallback to AI_QUERY
            if verb_clarity == 0.5:
                print(f"[SANITY INTENT FILTER] Misclassified query '{query}' as command intent '{intent}' -> Falling back to AI_QUERY")
                return {"intent": "AI_QUERY", "query": query}
            
            print(f"[SANITY INTENT FILTER] Low confidence command detected ({confidence:.2f}) for '{query}' -> CLARIFICATION")
            action_verbs = {
                "OPEN": "open",
                "PLAY_MEDIA": "play",
                "MAP": "show on the map",
                "WINDOW_CONTROL": "close or control"
            }
            verb = action_verbs.get(intent, "execute")
            return {
                "intent": "CLARIFICATION",
                "question": f"What would you like me to {verb}, sir?"
            }

    # 1. WINDOW_CONTROL Sanity checks
    if intent == "WINDOW_CONTROL":
        cmd = intent_data.get("command", "")
        # Close active window validation
        if cmd == "close":
            close_words = {"close", "exit", "quit", "kill", "terminate", "stop", "end", "shutdown", "shut", "dismiss", "remove"}
            if not any(w in q for w in close_words):
                print(f"[SANITY INTENT FILTER] Rejected WINDOW_CONTROL 'close' for query '{query}'")
                return {"intent": "AI_QUERY", "query": query}
        elif cmd == "minimize":
            min_words = {"minimize", "hide", "shrink", "collapse", "iconify", "down"}
            if not any(w in q for w in min_words):
                print(f"[SANITY INTENT FILTER] Rejected WINDOW_CONTROL 'minimize' for query '{query}'")
                return {"intent": "AI_QUERY", "query": query}
        elif cmd == "maximize":
            max_words = {"maximize", "expand", "enlarge", "fullscreen", "grow", "up"}
            if not any(w in q for w in max_words):
                print(f"[SANITY INTENT FILTER] Rejected WINDOW_CONTROL 'maximize' for query '{query}'")
                return {"intent": "AI_QUERY", "query": query}
                
    # 2. SPOTIFY_CONTROL Sanity checks
    if intent == "SPOTIFY_CONTROL":
        music_words = {"spotify", "music", "song", "playlist", "track", "volume", "loud", "quiet", "louder", "turn", "next", "skip", "pause", "resume", "play", "previous", "prev", "mute", "unmute"}
        if not any(w in q for w in music_words):
            print(f"[SANITY INTENT FILTER] Rejected SPOTIFY_CONTROL for query '{query}'")
            return {"intent": "AI_QUERY", "query": query}

    # 3. YOUTUBE CAPABILITIES DETERMINISTIC ROUTING & SEPARATION
    youtube_intents = {"YOUTUBE_TOPIC_SEARCH", "LATEST_CREATOR_VIDEO", "LATEST_CREATOR_SHORT", "VIDEO_BY_TITLE", "CHANNEL_OPEN", "PLAY_SEARCH_RESULT"}
    if intent in youtube_intents or any(w in q for w in ("youtube", "yt", "video", "short", "shorts", "reel", "channel", "play", "watch")):
        # Let's clean the query for classification
        q_clean = q.replace("'s", "").replace("’s", "").strip()
        
        # A. Shorts Capability Separation
        if any(w in q_clean for w in ("short", "shorts", "reel")):
            # Extract creator
            creator = q_clean
            for term in ("open latest short by", "show", "newest short", "play latest shorts upload from", "play latest short by", "latest short by", "newest short of", "shorts", "short", "reel", "play", "open", "show me"):
                creator = re.sub(rf"\b{term}\b", "", creator, flags=re.IGNORECASE)
            creator = re.sub(r"[^\w\s]", "", creator).strip()
            if creator:
                print(f"[SANITY INTENT FILTER] Re-routed to LATEST_CREATOR_SHORT: creator='{creator}'")
                return {"intent": "LATEST_CREATOR_SHORT", "creator": creator, "query": query}
                
        # B. Latest Creator Video Capability Separation
        elif any(w in q_clean for w in ("latest", "newest", "recent")) and any(w in q_clean for w in ("video", "upload", "content")):
            # Extract creator
            creator = q_clean
            for term in ("open latest video by", "show", "newest upload", "play", "latest video of", "newest video from", "newest video of", "latest upload of", "latest video by", "video", "upload", "latest", "newest", "recent", "open", "show me"):
                creator = re.sub(rf"\b{term}\b", "", creator, flags=re.IGNORECASE)
            creator = re.sub(r"[^\w\s]", "", creator).strip()
            if creator:
                print(f"[SANITY INTENT FILTER] Re-routed to LATEST_CREATOR_VIDEO: creator='{creator}'")
                return {"intent": "LATEST_CREATOR_VIDEO", "creator": creator, "query": query}
                
        # C. Video By Title Capability Separation
        elif "titled" in q_clean or "called" in q_clean or "named" in q_clean or q_clean.startswith("play video ") or q_clean.startswith("open video ") or "youtube video" in q_clean:
            title = q_clean
            creator = None
            by_match = re.search(r"(?:titled|called|named)\s+(.+?)\s+\b(by|from)\s+(.+)", q_clean, re.IGNORECASE)
            if by_match:
                title = by_match.group(1).strip()
                creator = by_match.group(3).strip()
            else:
                for term in ("play video titled", "open video titled", "play video called", "open video called", "play video named", "open video named", "play video", "open video", "play the youtube video", "play youtube video", "youtube video", "find the", "find", "titled", "called", "named"):
                    title = re.sub(rf"\b{term}\b", "", title, flags=re.IGNORECASE)
            title = re.sub(r"[^\w\s]", "", title).strip()
            if title:
                print(f"[SANITY INTENT FILTER] Re-routed to VIDEO_BY_TITLE: title='{title}', creator='{creator}'")
                return {"intent": "VIDEO_BY_TITLE", "title": title, "creator": creator, "query": query}
                
        # D. Channel Open Capability Separation
        elif "channel" in q_clean or "page" in q_clean:
            creator = q_clean
            for term in ("open", "go to", "show", "channel", "page", "youtube channel", "youtube page"):
                creator = re.sub(rf"\b{term}\b", "", creator, flags=re.IGNORECASE)
            creator = re.sub(r"[^\w\s]", "", creator).strip()
            if creator:
                print(f"[SANITY INTENT FILTER] Re-routed to CHANNEL_OPEN: creator='{creator}'")
                return {"intent": "CHANNEL_OPEN", "creator": creator, "query": query}
                
        # E. Play Search Result Capability Separation
        elif any(w in q_clean for w in ("first", "second", "third", "1st", "2nd", "3rd")) and "result" in q_clean:
            idx = 0
            if "second" in q_clean or "2nd" in q_clean:
                idx = 1
            elif "third" in q_clean or "3rd" in q_clean:
                idx = 2
            print(f"[SANITY INTENT FILTER] Re-routed to PLAY_SEARCH_RESULT: query='{query}', index={idx}")
            return {"intent": "PLAY_SEARCH_RESULT", "query": query, "index": idx}
            
        # F. YouTube Topic Search Capability Separation (Open search results only)
        else:
            # Check if this is a search intent or contains youtube/yt search keywords
            if intent == "YOUTUBE_TOPIC_SEARCH" or any(w in q_clean for w in ("youtube", "yt", "search", "find", "videos", "show")):
                print(f"[SANITY INTENT FILTER] Re-routed to YOUTUBE_TOPIC_SEARCH: query='{query}'")
                return {"intent": "YOUTUBE_TOPIC_SEARCH", "query": query}


    if intent == "OPEN":
        target = intent_data.get("target", "").strip()
        if not target:
            return {
                "intent": "CLARIFICATION",
                "question": "What would you like me to open, sir?"
            }

        # Sole ownership rule: If target or query contains media/video keywords, re-route to PLAY_MEDIA
        media_keywords = ("video", "song", "music", "youtube", "upload", "play", "spotify")
        if any(w in target.lower() or w in q for w in media_keywords):
            print(f"[SANITY INTENT FILTER] Re-routing media-centric OPEN intent to PLAY_MEDIA: target='{target}'")
            return {
                "intent": "PLAY_MEDIA",
                "query": target,
                "platform": "spotify" if "spotify" in target.lower() or "spotify" in q else "youtube"
            }

        open_words = {"open", "start", "launch", "run", "execute", "go to", "show", "view", "visit", "bring up"}
        if not any(w in q for w in open_words) and any(w in q for w in ("what", "how", "why", "who", "where", "define")):
            print(f"[SANITY INTENT FILTER] Rejected OPEN for generic question query '{query}'")
            return {"intent": "AI_QUERY", "query": query}

    # 4. SCREEN_UNDERSTANDING Sanity checks (CRITICAL VISUAL ISOLATION LAYER)
    if intent == "SCREEN_UNDERSTANDING":
        is_memory = any(w in q for w in ("about me", "who am i", "my name", "creator", "aaditya", "who are you", "what is my JEE", "my class"))
        screen_indicators = {
            "screen", "display", "monitor", "page", "window", "graph", "derivation", "equation", "diagram",
            "this webpage", "this app", "this code", "this graph", "this derivation", "whats on", "what is on",
            "whats currently on", "explain this", "analyze this", "summarize this", "solve this", "read this", "screenshot"
        }
        has_screen_indicator = any(w in q for w in screen_indicators)
        if is_memory or not has_screen_indicator:
            print(f"[SANITY INTENT FILTER] Rejected SCREEN_UNDERSTANDING for non-visual/memory query '{query}' -> AI_QUERY")
            return {"intent": "AI_QUERY", "query": query}

    # 5. NEWS intent dynamic topic extraction
    if intent == "NEWS":
        topic = intent_data.get("topic", "").strip()
        if not topic:
            from brain.entity_tracker import extract_all_entities
            entities = extract_all_entities(query)
            for ent_text, ent_type in entities:
                if ent_type in ("topic", "person", "location") and ent_text.lower() not in ("news", "headline", "headlines", "briefing", "what's happening"):
                    topic = ent_text
                    break
            if not topic:
                cleaned = q
                for word in ("today's", "today", "latest", "hot", "current", "news", "headline", "headlines", "what's happening", "briefing", "stories", "story", "about", "on", "for"):
                    cleaned = re.sub(rf"\b{word}\b", "", cleaned, flags=re.IGNORECASE)
                cleaned = re.sub(r"[^\w\s]", "", cleaned).strip()
                if len(cleaned) > 2:
                    topic = cleaned
            if topic:
                print(f"[SANITY INTENT FILTER] Extracted news topic '{topic}' from query '{query}'")
                intent_data["topic"] = topic.title()

    # 6. MAP_ROUTE intent sanitization
    if intent == "MAP_ROUTE":
        origin = intent_data.get("origin", "")
        dest = intent_data.get("destination", "")
        if origin:
            for term in ("show me map route for", "show me map for", "show me route for", "show route from", "directions from", "route from", "map of", "map for", "navigate from", "go from", "path from", "how to go from", "directions to", "show me", "map"):
                origin = re.sub(rf"\b{term}\b", "", origin, flags=re.IGNORECASE)
            origin = re.sub(r"[^\w\s]", "", origin).strip()
            intent_data["origin"] = origin.title() if origin else ""
        if dest:
            for term in ("show me map route to", "show me map to", "show me route to", "show route to", "directions to", "route to", "map of", "map to", "navigate to", "go to", "path to", "how to go to", "show me", "map"):
                dest = re.sub(rf"\b{term}\b", "", dest, flags=re.IGNORECASE)
            dest = re.sub(r"[^\w\s]", "", dest).strip()
            intent_data["destination"] = dest.title() if dest else ""

    if intent_data.get("intent") == "AI_QUERY" and _is_realtime(query):
        intent_data["intent"] = "REALTIME_QUERY"
    return intent_data
