# FRIDAY Routing Matrix

## Overview

FRIDAY uses a **REASON-FIRST** architecture:
1. Think first (classify intent and freshness)
2. Search only when necessary (live information queries)
3. Default to LLM (Groq) for general conversation

## Routing Components

### 1. IntentParser (brain/intent_parser.py)
- Classifies user query into intent categories
- Uses keyword-based pattern matching
- Determines if query requires live retrieval via `_REALTIME_SIGNALS`

### 2. PlannerBrain (brain/planner.py)
- Orchestrates routing decision
- Detects freshness signals via `_FRESHNESS_SIGNALS`
- Routes to appropriate brain based on:
  - Freshness requirements
  - Command keywords (NATIVE_OS, MEDIA, TEMPORAL, BROWSER)
  - Default fallback to LLM

### 3. RoutingManager (brain/routing_manager.py)
- Executes queries to appropriate AI engines
- Routes to Groq (default), Serper (live data), or other specialized engines

## Complete Routing Matrix

| Query Category | Examples | Intent | Freshness | Target Brain | Why |
|----------------|----------|--------|-----------|--------------|-----|
| **CASUAL CHAT** | "how are you", "hello", "hi friday", "good morning", "tell me a joke", "thank you" | AI_QUERY | FALSE | LLM (Groq) | Conversational greeting, no live data needed |
| **PERSONAL MEMORY** | "who is aaditya", "who built you", "what do you know about me" | AI_QUERY | FALSE | MEMORY | Identity/memory queries, stored knowledge |
| **LOCAL COMMANDS** | "open chrome", "open spotify", "close notepad", "launch vscode" | EXECUTE_APP | FALSE | NATIVE_OS | System control commands, no search needed |
| **WEB BROWSER** | "open google.com", "search for cats", "browse youtube" | WEB_SEARCH | FALSE | BROWSER | Direct web navigation, no retrieval needed |
| **MEDIA CONTROL** | "play music", "pause spotify", "next song", "volume up" | SPOTIFY_CONTROL | FALSE | MEDIA | Media playback control, no search needed |
| **TEMPORAL** | "set reminder", "set timer", "what time is it" | SET_REMINDER | FALSE | TEMPORAL | Time-based commands, no search needed |
| **LIVE NEWS** | "latest ai news", "breaking news", "headlines today" | REALTIME_QUERY | TRUE | RETRIEVAL (Serper → Groq) | News changes frequently, requires live data |
| **WEATHER** | "weather in delhi", "temperature in london", "forecast" | WEATHER | TRUE | RETRIEVAL (Serper → Groq) | Weather changes hourly, requires live data |
| **CURRENT EVENTS** | "who is prime minister of uk", "election results", "stock price" | REALTIME_QUERY | TRUE | RETRIEVAL (Serper → Groq) | Political/financial data changes, requires live data |
| **SPORTS LIVE** | "ipl score", "match results", "live cricket" | REALTIME_QUERY | TRUE | RETRIEVAL (Serper → Groq) | Sports scores change in real-time |
| **TECH UPDATES** | "latest iphone", "new android", "chatgpt update" | REALTIME_QUERY | TRUE | RETRIEVAL (Serper → Groq) | Product launches and updates require live data |
| **GENERAL KNOWLEDGE** | "what is photosynthesis", "explain quantum computing", "who was einstein" | AI_QUERY | FALSE | LLM (Groq) | Static knowledge, LLM has this information |
| **CODING HELP** | "write a python function", "debug this code", "explain this algorithm" | AI_QUERY | FALSE | LLM (Groq) | Technical assistance, no live data needed |
| **SCREEN UNDERSTANDING** | "what's on my screen", "explain this window", "summarize this video" | SCREEN_UNDERSTANDING | FALSE | VISION | Visual analysis, no web search needed |
| **MAPS/LOCATION** | "where is paris", "map route to delhi", "nearest coffee shop" | MAP | TRUE | RETRIEVAL (Serper → Groq) | Location data requires live maps |

## Freshness Signals (planner.py)

These signals trigger RETRIEVAL routing:
- Time references: "latest", "current", "today", "now", "right now"
- Recency words: "new", "newest", "updated", "breaking", "trending"
- News/events: "news", "headline", "announcement", "launch"
- Sports: "score", "match", "schedule", "standings"
- Tech: "iphone", "samsung", "android", "chatgpt", "gemini"
- Finance: "stock", "price", "bitcoin", "crypto", "market"
- Politics: "prime minister", "president", "election", "government"
- Weather: "weather", "temperature", "forecast", "rain"

**CRITICAL**: These signals do NOT include "how is" or "how are" to prevent casual greetings from triggering retrieval.

## Routing Logic Flow

```
User Query
    ↓
IntentParser.classify()
    ↓
PlannerBrain.plan()
    ├─ Detect freshness signals
    ├─ Detect command keywords (NATIVE_OS, MEDIA, TEMPORAL, BROWSER)
    ├─ Detect URLs
    └─ Default to LLM
    ↓
Target Brain Selection
    ├─ RETRIEVAL (if freshness required) → Serper → Groq
    ├─ NATIVE_OS (if command keywords) → System Executor
    ├─ MEDIA (if media keywords) → Media Controller
    ├─ BROWSER (if URL) → Web Browser
    ├─ MEMORY (if identity query) → Memory Store
    └─ LLM (default) → Groq
    ↓
Response Generation
```

## Validation Test Cases

| Query | Expected Intent | Expected Freshness | Expected Brain |
|-------|----------------|-------------------|----------------|
| "how are you friday" | AI_QUERY | FALSE | LLM |
| "hello" | AI_QUERY | FALSE | LLM |
| "who built you" | AI_QUERY | FALSE | MEMORY |
| "open chrome" | EXECUTE_APP | FALSE | NATIVE_OS |
| "latest ai news" | REALTIME_QUERY | TRUE | RETRIEVAL |
| "who is prime minister of uk" | REALTIME_QUERY | TRUE | RETRIEVAL |
| "weather in delhi" | WEATHER | TRUE | RETRIEVAL |
| "tell me a joke" | AI_QUERY | FALSE | LLM |
| "what is photosynthesis" | AI_QUERY | FALSE | LLM |
| "ipl score" | REALTIME_QUERY | TRUE | RETRIEVAL |

## Key Principles

1. **REASON-FIRST**: Classify intent before deciding to search
2. **MINIMAL SEARCH**: Only use SERPER for truly time-sensitive queries
3. **FAST RESPONSE**: Casual chat should be instant (LLM only)
4. **ACCURATE**: Live data queries must use retrieval
5. **ROBUST**: Default to LLM if classification is uncertain
