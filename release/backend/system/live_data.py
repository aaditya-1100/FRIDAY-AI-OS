"""
live_data.py — FRIDAY realtime intelligence engine v5

Web retrieval pipeline (simplified):
  0. Geographic solver — Haversine distance, geocoding
  1. Serper Google     — real Google results via Serper.dev
  2. LLM synthesis     — synthesize gathered context naturally

All sources use a circuit-breaker pattern: after a failure, the source
is skipped for 120 seconds to avoid repeated timeouts.
"""
import re
import os
import requests
import time
import math
import threading
from datetime import datetime
from urllib.parse import quote

from llm.groq_client import ask_groq, REALTIME_MODEL
from system.retrieval_utils import rewrite_query, rank_and_filter, verify_results


# ─── SOURCE HEALTH REGISTRY — circuit breaker pattern ─────────────────────────
_SOURCE_HEALTH = {}  # {"source_name": {"last_failure": timestamp, "consecutive_failures": int}}
_HEALTH_LOCK = threading.Lock()
_CIRCUIT_BREAK_SECONDS = 120  # skip source for 120s after failure


def _source_available(name: str) -> bool:
    """Check if a source is currently available (not circuit-broken)."""
    with _HEALTH_LOCK:
        info = _SOURCE_HEALTH.get(name)
        if not info:
            return True
        elapsed = time.time() - info.get("last_failure", 0)
        return elapsed > _CIRCUIT_BREAK_SECONDS


def _mark_source_failure(name: str):
    """Record a failure for a source, advancing the circuit breaker."""
    with _HEALTH_LOCK:
        info = _SOURCE_HEALTH.setdefault(name, {"last_failure": 0, "consecutive_failures": 0})
        info["last_failure"] = time.time()
        info["consecutive_failures"] += 1


def _mark_source_success(name: str):
    """Clear failure history for a source on success."""
    with _HEALTH_LOCK:
        _SOURCE_HEALTH.pop(name, None)




# ─── WMO weather code → human description ────────────────────────────────────
_WMO_CODES = {
    0:  "Clear sky",
    1:  "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Foggy", 48: "Icy fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
    77: "Snow grains",
    80: "Light showers", 81: "Moderate showers", 82: "Heavy showers",
    85: "Light snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Thunderstorm with heavy hail",
}

_HEADERS = {"User-Agent": "FRIDAY-Assistant/2.0 (contact: friday@local)"}


# =========================================
# REALTIME RETRIEVAL TRACKER & UTILITIES
# =========================================

class RetrievalTracker:
    def __init__(self):
        self.logs = []

    def log_attempt(self, source: str, status: str, results_count: int, latency_ms: float, error_detail: str = None):
        log_entry = {
            "source": source,
            "status": status,
            "results_count": results_count,
            "latency_ms": latency_ms,
            "error": error_detail
        }
        self.logs.append(log_entry)
        print(f"[RETRIEVAL TRACKER] Source: {source} | Status: {status} | Count: {results_count} | Latency: {latency_ms:.1f}ms" + (f" | Error: {error_detail}" if error_detail else ""))

    def get_summary(self) -> str:
        parts = []
        for entry in self.logs:
            p = f"{entry['source']}: {entry['status']} ({entry['results_count']} results)"
            if entry['error']:
                p += f" [Error: {entry['error']}]"
            parts.append(p)
        return "\n".join(f"- {p}" for p in parts)


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two GPS coordinates using Haversine formula."""
    R = 6371.0 # Radius of the Earth in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.asin(math.sqrt(a))
    return R * c


def _simplify_query(query: str) -> str:
    """Simplify a query to improve fallback search hits if initial searches fail."""
    q = query.lower().strip()
    # 1. Strip punctuation and question marks
    q = re.sub(r"[?.,\/#!$%\^&\*;:{}=\-_`~()]", "", q)
    # 2. Strip standard fillers/conversational words
    words = q.split()
    fillers = {"what", "is", "the", "latest", "current", "news", "about", "who", "won", "show", "me", "recent", "trending", "2026", "distance", "between", "from", "to", "how", "far", "coordinates"}
    cleaned_words = [w for w in words if w not in fillers]
    simplified = " ".join(cleaned_words).strip()
    return simplified if simplified else query


def _resolve_geographic_query(query: str) -> str | None:
    """Detect and mathematically solve geographic distance, coordinate, and timezone queries."""
    q = query.lower()
    
    # 1. Distance between X and Y
    m1 = re.search(r"distance (?:from|between)\s+(.+?)\s+(?:to|and)\s+(.+)", q)
    m2 = re.search(r"how far is\s+(.+?)\s+from\s+(.+)", q)
    
    loc1, loc2 = None, None
    if m1:
        loc1 = m1.group(1).strip()
        loc2 = m1.group(2).strip()
    elif m2:
        loc1 = m2.group(1).strip()
        loc2 = m2.group(2).strip()
        
    if loc1 and loc2:
        # Strip trailing question marks/punctuation
        loc1 = re.sub(r"[?.,]", "", loc1).strip()
        loc2 = re.sub(r"[?.,]", "", loc2).strip()
        
        coords1 = _geocode(loc1)
        coords2 = _geocode(loc2)
        
        if coords1 and coords2:
            lat1, lon1, name1 = coords1
            lat2, lon2, name2 = coords2
            dist = haversine_distance(lat1, lon1, lat2, lon2)
            return (
                f"Calculated Geographic Context:\n"
                f"- Location 1: {name1} (Latitude: {lat1:.4f}, Longitude: {lon1:.4f})\n"
                f"- Location 2: {name2} (Latitude: {lat2:.4f}, Longitude: {lon2:.4f})\n"
                f"- The calculated great-circle distance between them is approximately {dist:.1f} kilometers "
                f"({dist * 0.621371:.1f} miles)."
            )
            
    # 2. Coordinates or location lookup
    m3 = re.search(r"(?:where is|coordinates of|location of)\s+(.+)", q)
    if m3:
        loc = m3.group(1).strip()
        loc = re.sub(r"[?.,]", "", loc).strip()
        coords = _geocode(loc)
        if coords:
            lat, lon, name = coords
            return (
                f"Calculated Geographic Context:\n"
                f"- Target Location: {name}\n"
                f"- Coordinates: Latitude {lat:.4f}, Longitude {lon:.4f}"
            )
            
    return None


# ─── GEOCODING ────────────────────────────────────────────────────────────────

def _geocode(location: str) -> tuple[float, float, str] | None:
    try:
        url = f"https://nominatim.openstreetmap.org/search?q={quote(location)}&format=json&limit=1"
        r = requests.get(url, timeout=6, headers=_HEADERS)
        r.raise_for_status()
        results = r.json()
        if not results:
            return None
        hit = results[0]
        return float(hit["lat"]), float(hit["lon"]), hit.get("display_name", location)
    except Exception as e:
        print(f"[GEOCODE ERROR] {e}")
        return None


def _ip_location() -> tuple[float, float, str] | None:
    try:
        r = requests.get("http://ip-api.com/json/?fields=lat,lon,city,country", timeout=5, headers=_HEADERS)
        r.raise_for_status()
        d = r.json()
        lat, lon = d["lat"], d["lon"]
        city = d.get("city", "")
        country = d.get("country", "")
        name = f"{city}, {country}" if city else "your location"
        return lat, lon, name
    except Exception as e:
        print(f"[IP LOCATION ERROR] {e}")
        return None


# ─── WEATHER ─────────────────────────────────────────────────────────────────

def get_weather(location: str = "", query: str = "") -> str:
    try:
        loc = location.strip()
        # Default empty, general, or local locations to Kashipur, Uttarakhand, India unconditionally
        if not loc or loc.lower() in ("my location", "here", "current location", "me"):
            loc = "Kashipur, Uttarakhand, India"

        coords = _geocode(loc)
        if coords is None:
            return f"I couldn't find the location '{loc}' sir. Please try a city name."
        lat, lon, place = coords

        parts = [p.strip() for p in place.split(",")]
        place = ", ".join(parts[:2]) if len(parts) >= 2 else parts[0]

        params = (
            f"latitude={lat}&longitude={lon}"
            "&current=temperature_2m,relative_humidity_2m,apparent_temperature,"
            "weather_code,wind_speed_10m,precipitation,uv_index"
            "&daily=temperature_2m_max,temperature_2m_min,weather_code"
            "&wind_speed_unit=kmh&timezone=auto"
        )
        r = requests.get(f"https://api.open-meteo.com/v1/forecast?{params}", timeout=8, headers=_HEADERS)
        r.raise_for_status()
        data = r.json()

        cur    = data["current"]
        temp   = round(cur["temperature_2m"])
        feels  = round(cur["apparent_temperature"])
        humid  = cur["relative_humidity_2m"]
        wind   = round(cur["wind_speed_10m"])
        code   = cur.get("weather_code", 0)
        desc   = _WMO_CODES.get(code, "conditions unknown")
        precip = cur.get("precipitation", 0)
        uv     = cur.get("uv_index")

        daily     = data.get("daily", {})
        today_max = round(daily["temperature_2m_max"][0]) if daily and "temperature_2m_max" in daily else None
        today_min = round(daily["temperature_2m_min"][0]) if daily and "temperature_2m_min" in daily else None

        tomorrow_desc = None
        tomorrow_max  = None
        if daily and len(daily.get("time", [])) >= 2:
            tom_code = daily["weather_code"][1]
            tomorrow_desc = _WMO_CODES.get(tom_code, "conditions unknown").lower()
            tomorrow_max  = round(daily["temperature_2m_max"][1])

        # ── Query-Aware speak styles ──
        is_briefing = False
        if query:
            q = query.lower()
            if "briefing" in q or "my day" in q or "report" in q:
                is_briefing = True

        if not is_briefing:
            summary = f"In {place} right now, it's {desc.lower()} with a temperature of {temp} degrees Celsius, feeling like {feels}."
            if today_max is not None and today_min is not None:
                summary += f" Today will see a high of {today_max} and a low of {today_min}."
            if precip and float(precip) > 0:
                summary += f" There's {precip} millimetres of precipitation."
            return summary

        now = datetime.now()
        hour = now.hour
        greeting = "good morning" if hour < 12 else ("good afternoon" if hour < 17 else "good evening")

        summary = (
            f"{greeting} sir. In {place} right now, it's {desc.lower()} "
            f"with a temperature of {temp} degrees Celsius, feeling like {feels}. "
            f"Humidity is at {humid} percent and winds are {wind} kilometres per hour."
        )
        if today_max is not None and today_min is not None:
            summary += f" Today will see a high of {today_max} and a low of {today_min}."
        if tomorrow_desc and tomorrow_max is not None:
            summary += f" Tomorrow is forecast to be {tomorrow_desc} with a high of {tomorrow_max}."
        if precip and float(precip) > 0:
            summary += f" There's {precip} millimetres of precipitation currently."
        if uv is not None and float(uv) >= 6:
            summary += f" UV index is {round(uv)}, sun protection recommended."

        return summary

    except requests.exceptions.Timeout:
        return "The weather request timed out sir."
    except Exception as e:
        print(f"[WEATHER ERROR] {e}")
        return "I was unable to retrieve the weather right now sir."


# ─── NEWS ─────────────────────────────────────────────────────────────────────

_NEWS_FEEDS = {
    ("tech", "technology", "ai", "artificial intelligence", "gadget", "software"):
        "https://feeds.feedburner.com/TechCrunch",
    ("sport", "sports", "cricket", "football", "soccer", "ipl", "nba"):
        "https://www.espn.com/espn/rss/news",
    ("business", "finance", "economy", "stock", "market", "startup"):
        "https://feeds.bloomberg.com/markets/news.rss",
    ("india", "indian", "bollywood"):
        "https://timesofindia.indiatimes.com/rssfeeds/-2128936835.cms",
    ("science", "space", "nasa", "research"):
        "https://www.sciencedaily.com/rss/all.xml",
    ("world", "international", "global", "politics"):
        "https://feeds.bbci.co.uk/news/world/rss.xml",
}


def _pick_feed(topic: str) -> str:
    topic_lower = topic.lower()
    for keywords, url in _NEWS_FEEDS.items():
        if any(k in topic_lower for k in keywords):
            return url
    return "https://feeds.bbci.co.uk/news/rss.xml"


def _extract_rss_items(xml: str, max_items: int = 6) -> list[dict]:
    items = re.findall(r"<item>(.*?)</item>", xml, re.DOTALL)
    results = []
    for item in items[:max_items]:
        title = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", item, re.DOTALL)
        desc  = re.search(r"<description>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</description>", item, re.DOTALL)
        t = title.group(1).strip() if title else ""
        d = desc.group(1).strip() if desc else ""
        d = re.sub(r"<[^>]+>", "", d).strip()
        if t:
            results.append({"title": t, "desc": d})
    return results


def get_news(topic: str = "") -> str:
    try:
        feed_url = _pick_feed(topic)
        resp = requests.get(feed_url, timeout=8, headers=_HEADERS)
        resp.raise_for_status()
        items = _extract_rss_items(resp.text, max_items=6)

        if not items:
            return "I couldn't find any news right now sir."

        raw = "\n".join(
            f"- {it['title']}" + (f": {it['desc'][:120]}" if it["desc"] else "")
            for it in items
        )
        topic_label = topic if topic else "general"
        now_str = datetime.now().strftime("%A, %B %d, %Y at %I:%M %p")

        prompt = f"""You are FRIDAY, a smart AI assistant. Current time: {now_str}.

Here are the latest {topic_label} news headlines:
{raw}

Summarize the top 3-4 most important stories in a natural, conversational way as if briefing your boss.
Be concise (under 80 words). Don't list numbers or say "headline 1". 
Don't mention source names. Speak naturally. Start with "Here's what's happening" or similar."""

        summary = ask_groq(prompt, model=REALTIME_MODEL)
        return summary if summary else f"I found some {topic_label} news but couldn't summarize it sir."

    except requests.exceptions.Timeout:
        return "The news feed timed out sir. Please try again."
    except Exception as e:
        print(f"[NEWS ERROR] {e}")
        return "I was unable to fetch the news right now sir."




# ─── IS NEWS/TRENDING QUERY (broad universal signals) ────────────────────────

_RECENCY_SIGNALS = frozenset({
    "latest", "recent", "update", "updates", "today", "now", "current",
    "trending", "news", "headlines", "happening", "new", "announce",
    "launch", "release", "reveal", "breaking", "just", "this week",
    "this month", "right now", "at the moment", "so far",
    "upcoming", "ongoing", "live", "realtime", "real-time",
})

def _is_recency_query(query: str) -> bool:
    q = query.lower()
    return any(w in q for w in _RECENCY_SIGNALS)




# ─── REALTIME WEB QUERY (SERPER only) ───────────────────────────────────────

def realtime_web_query(query: str, memory_context: str | None = None) -> str:
    """
    Live web intelligence using SERPER only.
    Simple, fast, deterministic routing.
    """
    now = datetime.now()
    year = now.year
    now_str = now.strftime("%A, %B %d, %Y at %I:%M %p")

    tracker = RetrievalTracker()
    context_parts: list[str] = []
    is_recency = _is_recency_query(query)

    print(f"[REALTIME] Query: {query!r} | recency={is_recency}")

    # ── Geographic Solver (if applicable) ───────────────────────────────────
    geo_context = _resolve_geographic_query(query)
    if geo_context:
        context_parts.append(geo_context)
        tracker.log_attempt("GeographicSolver", "SUCCESS", 1, 0)

    # ── SERPER Search ────────────────────────────────────────────────────────
    if _source_available("SerperGoogle"):
        t_start = time.perf_counter()
        try:
            from system.google_search import google_search, google_news_search, \
                extract_context_from_google, is_configured
            if is_configured():
                # Get optimized search queries
                search_queries = rewrite_query(query)
                g_parts = []
                for sq in search_queries:
                    g_result = google_search(sq, num=6)
                    sq_parts = extract_context_from_google(g_result, max_organic=4)
                    g_parts.extend(sq_parts)
                
                # Dedup g_parts while keeping order
                seen_snippets = set()
                deduped_parts = []
                for gp in g_parts:
                    gp_norm = gp.lower().strip()
                    if gp_norm not in seen_snippets:
                        seen_snippets.add(gp_norm)
                        deduped_parts.append(gp)
                g_parts = deduped_parts

                if g_parts:
                    context_parts.extend(g_parts)
                    _mark_source_success("SerperGoogle")
                    tracker.log_attempt("SerperGoogle", "SUCCESS", len(g_parts), (time.perf_counter() - t_start) * 1000)
                else:
                    tracker.log_attempt("SerperGoogle", "EMPTY_OR_FAIL", 0, (time.perf_counter() - t_start) * 1000)

                # Also fetch news specifically for recency queries
                if is_recency:
                    t_news = time.perf_counter()
                    g_news = google_news_search(query, num=5)
                    if g_news:
                        news_lines = []
                        for n in g_news[:5]:
                            t = n.get("title", "").strip()
                            d = n.get("date", "")
                            s = n.get("snippet", "").strip()[:120]
                            if t:
                                entry = t
                                if d: entry += f" [{d}]"
                                if s: entry += f" — {s}"
                                news_lines.append(entry)
                        if news_lines:
                            context_parts.append("Google News (live):\n" + "\n".join(f"• {l}" for l in news_lines))
                            tracker.log_attempt("SerperNews", "SUCCESS", len(news_lines), (time.perf_counter() - t_news) * 1000)
            else:
                tracker.log_attempt("SerperGoogle", "UNCONFIGURED", 0, 0)
        except Exception as e:
            _mark_source_failure("SerperGoogle")
            tracker.log_attempt("SerperGoogle", "ERROR", 0, (time.perf_counter() - t_start) * 1000, str(e))
    else:
        tracker.log_attempt("SerperGoogle", "CIRCUIT_BROKEN", 0, 0)

    # Print a summary log of the retrieval sequence
    print(f"[REALTIME] Raw context parts: {len(context_parts)}")
    print(tracker.get_summary())

    # ── Ranking & Verification ────────────────────────────────────────────────
    context_parts = rank_and_filter(context_parts, query)
    context_parts = verify_results(context_parts, query)
    print(f"[REALTIME FINISHED] Ranked/verified parts: {len(context_parts)}")

    # ── Layer 6: LLM synthesis ────────────────────────────────────────────────
    memory_block = f"\nConversational Context:\n{memory_context}\n" if memory_context else ""
    
    # Get contextual identity slices
    try:
        from brain.identity_manager import IdentityManager
        id_mgr = IdentityManager()
        identity_slices = id_mgr.get_contextual_slices(query)
    except Exception as e_id:
        print(f"[IDENTITY WARNING] Failed to resolve identity slices in realtime: {e_id}")
        identity_slices = None

    identity_block = ""
    if identity_slices:
        identity_block = "\nAuthoritative Structured Identity Slices:\n"
        for category, data in identity_slices.items():
            if isinstance(data, dict):
                identity_block += f"- [{category}]:\n"
                for field, val in data.items():
                    identity_block += f"  * {field}: {val}\n"
            else:
                identity_block += f"- [{category}]: {data}\n"

    if context_parts:
        context_block = "\n\n".join(context_parts)
        prompt = f"""You are FRIDAY, a premium, highly advanced Jarvis-style OS companion — alive, highly aware, and exceptionally intelligent, operating in {year}.
Current date/time: {now_str}
{memory_block}{identity_block}
The user asked: "{query}"

Below is the live, verified data just retrieved from the web right now in {year}:
---
{context_block}
---

CRITICAL COMPANION BRIEFING RULES:
1. NO SEARCH PREFIXES: Strictly forbid all introductory clauses, search source prefixes, or meta-commentary. Never say things like "According to the latest search results...", "Based on my real-time lookups...", "Here is what I found...", "Local reports state...", "According to Google News...", or "Based on retrieved data...".
2. DIRECT FACTUAL BRIEFING: State the synthesized intelligence directly as your own verified knowledge, naturally integrated into a single cohesive response.
3. DIRECT ANSWER FIRST & JARVIS PERSONA: Talk conversationally, confidently, and naturally, like a brilliant personal advisor briefing their boss. Always deliver the direct answer first in the very first sentence. Absolutely no introductory filler, context setup, or background exposition unless "explain", "compare", "analyze", "detail", or "why" are explicitly requested. Keep the entire response highly concise and under 50 words with zero fluff, using "Sir" (always capitalized) naturally and casually.
4. SYNTHESIS QUALITY: Focus on freshness, official updates, and verified details. Synthesize conflicting data intelligently based on the latest timestamps/dates.
5. STRICT QUESTION GROUNDING: Your entire response must stay 100% focused on answering the user's specific query (e.g., identifying the exact rocket used in SpaceX's latest launch). Do not drift into generic discussions, company history, or background details unless explicitly requested. If the retrieved data mentions the specific entity or answer, state it directly and concisely."""

    else:
        # No web data — honest fallback with explicit block warning (No hallucination)
        prompt = f"""You are FRIDAY, a premium, advanced Jarvis-style OS companion operating in {year}.
Current date/time: {now_str}
{memory_block}{identity_block}
The user asked: "{query}"

IMPORTANT: Live web retrieval service (SERPER) was completely unavailable or rate-limited for this query.
Do NOT guess or hallucinate any live facts. State directly, naturally, and transparently as a trusted companion that you attempted a real-time lookup but the search backend is unreachable or rate-limited.
Keep it under 40 words. Be natural, casual, and brief (e.g., "I tried pulling that live for you Sir, but search is down. I can check my internal knowledge or try again in a bit."). Avoid robotic AI helper preambles."""

    result = ask_groq(prompt, model=REALTIME_MODEL)
    return result if result else "I couldn't retrieve live information for that right now, sir. All web retrieval interfaces are currently unreachable."


def get_retrieval_health() -> dict:
    """Return current source health status for debugging/logging."""
    with _HEALTH_LOCK:
        return {
            k: {**v, "available": _source_available(k)}
            for k, v in _SOURCE_HEALTH.items()
        }

