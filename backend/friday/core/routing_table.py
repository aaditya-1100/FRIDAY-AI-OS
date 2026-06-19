from typing import Dict, Optional, Set

# Constant string for multi action intent
MULTI_ACTION_INTENT: str = "MULTI_ACTION"

# Set of intents that map to None (no agent dispatch)
DIRECT_LLM_INTENTS: Set[str] = {
    "CASUAL_CHAT",
    "AI_QUERY",
    "CLARIFICATION"
}

# Routing table mapping intent strings to agent type names
INTENT_TO_AGENT: Dict[str, Optional[str]] = {
    # Web search vs Browser automation
    # WEB_SEARCH: API retrieval only — no browser launch, no Playwright
    # BROWSER_SEARCH: opens browser and navigates — explicit browser task
    "WEB_SEARCH": "WEB_AGENT",  # API retrieval only (Serper API or DuckDuckGo) — no browser launch, no Playwright
    "SEARCH": "WEB_AGENT",      # API retrieval only (Serper API or DuckDuckGo) — no browser launch, no Playwright
    
    # Browser automation
    "BROWSER_OPEN": "WEB_AGENT",
    "BROWSER_SEARCH": "WEB_AGENT",
    "BROWSER_FILL": "WEB_AGENT",
    "BROWSER_CLICK": "WEB_AGENT",
    "BROWSER_SCREENSHOT": "WEB_AGENT",
    "BROWSER_CLOSE": "WEB_AGENT",

    "YOUTUBE_TOPIC_SEARCH": "WEB_AGENT",
    "LATEST_CREATOR_VIDEO": "WEB_AGENT",
    "LATEST_CREATOR_SHORT": "WEB_AGENT",
    "VIDEO_BY_TITLE": "WEB_AGENT",
    "CHANNEL_OPEN": "WEB_AGENT",
    "PLAY_SEARCH_RESULT": "WEB_AGENT",
    "PLAY_MEDIA": "WEB_AGENT",

    # App controls & Window controls
    "OPEN_APP": "PC_AGENT",
    "CLOSE_APP": "PC_AGENT",
    "OPEN": "PC_AGENT",
    "WINDOW_CONTROL": "PC_AGENT",

    # File / System
    "FILE_SYSTEM": "PC_AGENT",
    "OPEN_FOLDER": "PC_AGENT",
    "FILE_READ": "PC_AGENT",
    "FILE_WRITE": "PC_AGENT",
    "SYSTEM_STATUS": "PC_AGENT",
    "SCREENSHOT": "PC_AGENT",
    "SCREEN_UNDERSTANDING": "PC_AGENT",
    "SCREEN_READ": "VISION_AGENT",
    "SCREEN_FIND": "VISION_AGENT",
    "SCREEN_SCREENSHOT": "VISION_AGENT",
    "SCREEN_DESCRIBE": "VISION_AGENT",

    # Time-based OS tasks
    "SET_REMINDER": "PC_AGENT",
    "SET_ALARM": "PC_AGENT",
    "SET_TIMER": "PC_AGENT",
    "STOPWATCH_CONTROL": "PC_AGENT",
    "SET_SCHEDULED_TASK": "PC_AGENT",
    "SET_RECURRING_REMINDER": "PC_AGENT",
    "LIST_REMINDERS": "PC_AGENT",
    "CANCEL_REMINDER": "PC_AGENT",

    # Spotify local controls
    "SPOTIFY_CONTROL": "PC_AGENT",

    # Maps and Location (executed via action_executor in PC_AGENT)
    "MAP": "PC_AGENT",
    "MAP_LOCATION": "PC_AGENT",
    "MAP_ROUTE": "PC_AGENT",
    "MAP_DISCOVERY": "PC_AGENT",
    "PLACE_DISCOVERY": "PC_AGENT",
    "TRAVEL_ETA": "PC_AGENT",
    "MAP_FOLLOWUP": "PC_AGENT",

    # Weather & News
    "WEATHER": "PC_AGENT",
    "NEWS": "PC_AGENT",

    # Memory / facts
    "SET_FACT": "PC_AGENT",

    # Realtime queries (web search + LLM summarize, executed via action_executor)
    "REALTIME_QUERY": "PC_AGENT",

    # Direct LLM / Conversational
    "CASUAL_CHAT": None,
    "AI_QUERY": None,
    "CLARIFICATION": None,

    # MULTI_ACTION
    "MULTI_ACTION": "MULTI"
}

# "SEARCH" intent: routing TBD — platform-specific search
# (Spotify/YouTube = PC_AGENT, web search = WEB_AGENT)
# Pending decision before adding to table.

