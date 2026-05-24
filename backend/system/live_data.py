"""
live_data.py — FRIDAY realtime intelligence engine v3

Web retrieval pipeline (in priority order):
  1. DDGS text search  — real web results, fresh snippets, no API key
  2. Google News RSS   — always-fresh headlines for news queries  
  3. DuckDuckGo IA API — instant answers / infobox for factual queries
  4. LLM synthesis     — synthesize gathered context naturally

No predefined sites. No fixed sources. Dynamically searches the real web.
"""
import re
import requests
import time
import math
from datetime import datetime
from urllib.parse import quote

from llm.groq_client import ask_groq, REALTIME_MODEL


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
        if loc:
            coords = _geocode(loc)
            if coords is None:
                return f"I couldn't find the location '{loc}' sir. Please try a city name."
            lat, lon, place = coords
        else:
            coords = _ip_location()
            if coords is None:
                return "I couldn't determine your location sir."
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
        is_direct = False
        if query:
            q = query.lower()
            # Factual direct weather questions should not play an assistant morning briefing monologue
            if "briefing" not in q and "my day" not in q and "morning" not in q and "evening" not in q and "afternoon" not in q:
                is_direct = True

        if is_direct:
            summary = f"In {place} right now, it's {desc.lower()} with a temperature of {temp} degrees Celsius, feeling like {feels}."
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


# ─── DDGS TEXT SEARCH ────────────────────────────────────────────────────────

def _ddgs_search(query: str, max_results: int = 5) -> list[dict]:
    """
    Real web search via DuckDuckGo (ddgs library).
    Returns list of {title, body, href} dicts.
    Falls back to empty list if unavailable.
    """
    try:
        from ddgs import DDGS
        results = list(DDGS().text(query, max_results=max_results))
        return results
    except ImportError:
        print("[DDGS] ddgs library not installed, using fallback")
        return []
    except Exception as e:
        print(f"[DDGS ERROR] {e}")
        return []


def _ddgs_news(query: str, max_results: int = 5) -> list[dict]:
    """
    DuckDuckGo news search — returns recent news articles.
    """
    try:
        from ddgs import DDGS
        results = list(DDGS().news(query, max_results=max_results))
        return results
    except Exception as e:
        print(f"[DDGS NEWS ERROR] {e}")
        return []


# ─── GOOGLE NEWS RSS (always fresh) ──────────────────────────────────────────

def _google_news_rss(query: str, max_items: int = 6) -> list[dict]:
    """Fetch Google News RSS for a query — reliably returns fresh headlines."""
    try:
        rss_url = f"https://news.google.com/rss/search?q={quote(query)}&hl=en-IN&gl=IN&ceid=IN:en"
        r = requests.get(rss_url, timeout=7, headers=_HEADERS)
        if r.status_code == 200:
            return _extract_rss_items(r.text, max_items=max_items)
    except Exception as e:
        print(f"[GNEWS RSS ERROR] {e}")
    return []


# ─── DDG INSTANT ANSWER (facts/infobox) ──────────────────────────────────────

def _ddg_instant(query: str) -> list[str]:
    """DuckDuckGo Instant Answer API — good for factual/infobox data."""
    parts = []
    try:
        ddg_url = f"https://api.duckduckgo.com/?q={quote(query)}&format=json&no_html=1&skip_disambig=1"
        r = requests.get(ddg_url, timeout=5, headers=_HEADERS)
        r.raise_for_status()
        ddg = r.json()
        answer   = (ddg.get("Answer") or "").strip()
        abstract = (ddg.get("AbstractText") or "").strip()
        if answer:
            parts.append(f"Quick fact: {answer}")
        if abstract:
            parts.append(f"Background: {abstract[:400]}")
        # Infobox may be "" (empty string) or {} or {"content": [...]}
        infobox = ddg.get("Infobox", {})
        if isinstance(infobox, dict):
            for entry in infobox.get("content", [])[:3]:
                if not isinstance(entry, dict):
                    continue
                label = entry.get("label", "")
                val   = entry.get("value", "")
                if label and val:
                    parts.append(f"{label}: {val}")
    except Exception as e:
        print(f"[DDG IA ERROR] {e}")
    return parts


# ─── IS NEWS/TRENDING QUERY (broad universal signals) ────────────────────────

_RECENCY_SIGNALS = frozenset({
    "latest", "recent", "update", "updates", "today", "now", "current",
    "trending", "news", "headlines", "happening", "new", "announce",
    "launch", "release", "reveal", "breaking", "just", "this week",
    "this month", "2026", "right now", "at the moment", "so far",
    "upcoming", "ongoing", "live", "realtime", "real-time",
})

def _is_recency_query(query: str) -> bool:
    q = query.lower()
    return any(w in q for w in _RECENCY_SIGNALS)


def _tavily_search(query: str, max_results: int = 5) -> list[str]:
    """Retrieve clean, curated search results from Tavily if API key is set."""
    import os
    api_key = os.environ.get("TAVILY_API_KEY", "").strip()
    if not api_key:
        return []
    try:
        url = "https://api.tavily.com/search"
        payload = {
            "api_key": api_key,
            "query": query,
            "search_depth": "basic",
            "max_results": max_results
        }
        r = requests.post(url, json=payload, timeout=6)
        if r.status_code == 200:
            results = r.json().get("results", [])
            out = []
            for res in results:
                title = res.get("title", "")
                content = res.get("content", "")
                if title and content:
                    out.append(f"• {title}: {content}")
            if out:
                return ["Tavily search results:\n" + "\n".join(out)]
    except Exception as e:
        print(f"[TAVILY SEARCH ERROR] {e}")
    return []


# ─── REALTIME WEB QUERY (universal — any topic, any query) ───────────────────

def realtime_web_query(query: str) -> str:
    """
    Universal live web intelligence — works for ANY topic or query.
    Employs the 9-Brain Realtime Retrieval pipeline with tracing,
    self-healing simplified retries, and geographic distance solver logic.
    """
    now = datetime.now()
    now_str = now.strftime("%A, %B %d, %Y at %I:%M %p")
    year = now.year  # 2026

    tracker = RetrievalTracker()
    context_parts: list[str] = []
    is_recency = _is_recency_query(query)

    print(f"[REALTIME] Query: {query!r} | recency={is_recency} | year={year}")

    # ── Layer -1: Geographic Distance and Coordinate Solver ────────────────
    t_start = time.perf_counter()
    try:
        geo_context = _resolve_geographic_query(query)
        if geo_context:
            context_parts.append(geo_context)
            tracker.log_attempt("GeographicSolver", "SUCCESS", 1, (time.perf_counter() - t_start) * 1000)
    except Exception as e:
        tracker.log_attempt("GeographicSolver", "ERROR", 0, (time.perf_counter() - t_start) * 1000, str(e))

    # ── Layer 0: Tavily Search (If API Key is available) ────────────────────
    t_start = time.perf_counter()
    try:
        tav_results = _tavily_search(query)
        if tav_results:
            context_parts.extend(tav_results)
            tracker.log_attempt("TavilyAPI", "SUCCESS", len(tav_results), (time.perf_counter() - t_start) * 1000)
        else:
            tracker.log_attempt("TavilyAPI", "EMPTY_OR_UNCONFIGURED", 0, (time.perf_counter() - t_start) * 1000)
    except Exception as e:
        tracker.log_attempt("TavilyAPI", "ERROR", 0, (time.perf_counter() - t_start) * 1000, str(e))

    # ── Layer 1: Google Search via Serper.dev ────────────────────────────────
    t_start = time.perf_counter()
    try:
        from system.google_search import google_search, google_news_search, \
            extract_context_from_google, is_configured
        if is_configured():
            g_result = google_search(query, num=6)
            g_parts = extract_context_from_google(g_result, max_organic=4)
            if g_parts:
                context_parts.extend(g_parts)
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
        tracker.log_attempt("SerperGoogle", "ERROR", 0, (time.perf_counter() - t_start) * 1000, str(e))

    # ── Self-Healing: Query Simplification Check ────────────────────────────
    effective_query = query
    if len(context_parts) == 0:
        effective_query = _simplify_query(query)
        if effective_query != query:
            print(f"[REALTIME FAILOVER] First-line search empty. Retrying fallbacks with simplified query: {effective_query!r}")

    # ── Layer 2: DDGS News (timelimit=week) ──────────────────────────────────
    t_start = time.perf_counter()
    try:
        from ddgs import DDGS
        news_results = list(DDGS().news(effective_query, max_results=6, timelimit='w'))
        if news_results:
            items = []
            for n in news_results:
                title = n.get("title", "").strip()
                body  = (n.get("body") or n.get("snippet") or "")[:150].strip()
                date  = (n.get("date") or "")[:10]
                if title:
                    entry = title
                    if date: entry += f" [{date}]"
                    if body: entry += f" — {body}"
                    items.append(entry)
            if items:
                context_parts.append(f"Recent news (past week):\n" + "\n".join(f"• {i}" for i in items))
                tracker.log_attempt("DDGSNews", "SUCCESS", len(items), (time.perf_counter() - t_start) * 1000)
            else:
                tracker.log_attempt("DDGSNews", "EMPTY", 0, (time.perf_counter() - t_start) * 1000)
        else:
            tracker.log_attempt("DDGSNews", "EMPTY", 0, (time.perf_counter() - t_start) * 1000)
    except Exception as e:
        tracker.log_attempt("DDGSNews", "ERROR", 0, (time.perf_counter() - t_start) * 1000, str(e))

    # ── Layer 3: DDGS Text Search (timelimit=month) ──────────────────────────
    t_start = time.perf_counter()
    try:
        from ddgs import DDGS
        tlimit = 'w' if is_recency else 'm'
        web_results = list(DDGS().text(effective_query, max_results=5, timelimit=tlimit))
        if web_results:
            snippets = []
            for r in web_results:
                title = r.get("title", "").strip()
                body  = (r.get("body") or r.get("snippet") or "")[:200].strip()
                if title and body:
                    snippets.append(f"{title}: {body}")
                elif title:
                    snippets.append(title)
            if snippets:
                context_parts.append(f"Web articles (past {'week' if tlimit == 'w' else 'month'}):\n" + "\n".join(f"• {s}" for s in snippets))
                tracker.log_attempt("DDGSText", "SUCCESS", len(snippets), (time.perf_counter() - t_start) * 1000)
            else:
                tracker.log_attempt("DDGSText", "EMPTY", 0, (time.perf_counter() - t_start) * 1000)
        else:
            tracker.log_attempt("DDGSText", "EMPTY", 0, (time.perf_counter() - t_start) * 1000)
    except Exception as e:
        tracker.log_attempt("DDGSText", "ERROR", 0, (time.perf_counter() - t_start) * 1000, str(e))

    # ── Layer 4: Google News RSS ─────────────────────────────────────────────
    t_start = time.perf_counter()
    if len(context_parts) < 2 or is_recency:
        try:
            rss_items = _google_news_rss(effective_query, max_items=5)
            if rss_items:
                rss_lines = [
                    it["title"] + (f": {it['desc'][:120]}" if it.get("desc") else "")
                    for it in rss_items
                ]
                context_parts.append("Google News:\n" + "\n".join(f"• {l}" for l in rss_lines))
                tracker.log_attempt("GoogleRSS", "SUCCESS", len(rss_items), (time.perf_counter() - t_start) * 1000)
            else:
                tracker.log_attempt("GoogleRSS", "EMPTY", 0, (time.perf_counter() - t_start) * 1000)
        except Exception as e:
            tracker.log_attempt("GoogleRSS", "ERROR", 0, (time.perf_counter() - t_start) * 1000, str(e))

    # ── Layer 5: DDG Instant Answer ──────────────────────────────────────────
    t_start = time.perf_counter()
    try:
        ia_parts = _ddg_instant(effective_query)
        if ia_parts:
            context_parts.extend(ia_parts)
            tracker.log_attempt("DDGInstant", "SUCCESS", len(ia_parts), (time.perf_counter() - t_start) * 1000)
        else:
            tracker.log_attempt("DDGInstant", "EMPTY", 0, (time.perf_counter() - t_start) * 1000)
    except Exception as e:
        tracker.log_attempt("DDGInstant", "ERROR", 0, (time.perf_counter() - t_start) * 1000, str(e))

    # Print a summary log of the full retrieval sequence
    print(f"[REALTIME FINISHED] Active Context Parts: {len(context_parts)}")
    print(tracker.get_summary())

    # ── Layer 6: LLM synthesis ────────────────────────────────────────────────
    if context_parts:
        context_block = "\n\n".join(context_parts)
        prompt = f"""You are FRIDAY, an advanced AI assistant operating in {year}.
Current date/time: {now_str}

The user asked: "{query}"

Below is LIVE data just retrieved from the web right now in {year}:
---
{context_block}
---

CRITICAL RULES:
- Your training data may be outdated. Trust the live data above over your own memory.
- Answer confidently based on what the live data says.
- Respond naturally in 2–4 sentences (under 80 words).
- Speak like a knowledgeable assistant briefing their boss.
- Do NOT list URLs, domain names, or source names.
- Do NOT use bullet points or numbered lists.
- If multiple sources agree, synthesize them into one clear answer.
- If the data doesn't fully answer the question, say what you found concisely."""

    else:
        # No web data — honest fallback with explicit block warning (No hallucination)
        prompt = f"""You are FRIDAY, an advanced AI assistant operating in {year}.
Current date/time: {now_str}

The user asked: "{query}"

IMPORTANT: Live web retrieval services (Tavily, Serper, and DuckDuckGo) were completely unavailable or rate-limited for this query.
Do NOT guess or hallucinate any live facts. State directly and transparently to the user that you attempted a real-time lookup but all web search backends are currently unreachable or rate-limited, and offer to explain from your standard knowledge if they wish.
Keep it under 60 words. Be direct, professional, and clear."""

    result = ask_groq(prompt, model=REALTIME_MODEL)
    return result if result else "I couldn't retrieve live information for that right now, sir. All web retrieval interfaces are currently unreachable."

