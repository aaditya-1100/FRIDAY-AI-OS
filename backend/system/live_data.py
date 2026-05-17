"""
Live data fetchers: weather (Open-Meteo + geocoding), news (RSS + LLM summary),
and realtime web query (DuckDuckGo scrape + LLM summary).

Weather uses:
  1. Nominatim geocoding → lat/lon from location name
  2. Open-Meteo free API → actual real-time conditions
News uses:
  RSS feeds → LLM summarizes naturally (no raw title dumping)
Realtime:
  DuckDuckGo instant answers + snippet scraping → LLM summarizes
No API keys required for any of these.
"""
import re
import requests
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

_HEADERS = {"User-Agent": "FRIDAY-Assistant/1.0 (contact: friday@local)"}


# ─── GEOCODING ────────────────────────────────────────────────────────────────

def _geocode(location: str) -> tuple[float, float, str] | None:
    """Return (lat, lon, display_name) for a location string, or None."""
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
    """Fallback: detect location from IP using ip-api.com."""
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

def get_weather(location: str = "") -> str:
    """
    Fetch real-time weather using Open-Meteo (free, no API key).
    Returns a naturally spoken summary.
    """
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

        # Shorten Nominatim's very long display names
        parts = [p.strip() for p in place.split(",")]
        place = ", ".join(parts[:2]) if len(parts) >= 2 else parts[0]

        params = (
            f"latitude={lat}&longitude={lon}"
            "&current=temperature_2m,relative_humidity_2m,apparent_temperature,"
            "weather_code,wind_speed_10m,precipitation,uv_index"
            "&wind_speed_unit=kmh&timezone=auto"
        )
        url = f"https://api.open-meteo.com/v1/forecast?{params}"
        r = requests.get(url, timeout=8, headers=_HEADERS)
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

        now = datetime.now()
        hour = now.hour
        greeting = "good morning" if hour < 12 else ("good afternoon" if hour < 17 else "good evening")

        summary = (
            f"{greeting} sir. In {place} right now, it's {desc.lower()} "
            f"with a temperature of {temp} degrees Celsius, feeling like {feels}. "
            f"Humidity is at {humid} percent and winds are {wind} kilometres per hour."
        )
        if precip and float(precip) > 0:
            summary += f" There's {precip} millimetres of precipitation."
        if uv is not None and float(uv) >= 6:
            summary += f" UV index is {round(uv)}, so sun protection is recommended."

        return summary

    except requests.exceptions.Timeout:
        return "The weather request timed out sir."
    except Exception as e:
        print(f"[WEATHER ERROR] {e}")
        return "I was unable to retrieve the weather right now sir."


# ─── NEWS ─────────────────────────────────────────────────────────────────────

_NEWS_FEEDS = {
    ("tech", "technology", "ai", "artificial intelligence", "gadget"):
        "https://feeds.feedburner.com/TechCrunch",
    ("sport", "sports", "cricket", "football", "soccer", "ipl"):
        "https://www.espn.com/espn/rss/news",
    ("business", "finance", "economy", "stock", "market"):
        "https://feeds.bloomberg.com/markets/news.rss",
    ("india", "indian"):
        "https://timesofindia.indiatimes.com/rssfeeds/-2128936835.cms",
    ("science", "space", "nasa"):
        "https://www.sciencedaily.com/rss/all.xml",
    ("world", "international", "global"):
        "https://feeds.bbci.co.uk/news/world/rss.xml",
}


def _pick_feed(topic: str) -> str:
    topic_lower = topic.lower()
    for keywords, url in _NEWS_FEEDS.items():
        if any(k in topic_lower for k in keywords):
            return url
    return "https://feeds.bbci.co.uk/news/rss.xml"


def _extract_rss_items(xml: str, max_items: int = 6) -> list[dict]:
    """Extract title + description pairs from RSS XML."""
    # Get items between <item> tags
    items = re.findall(r"<item>(.*?)</item>", xml, re.DOTALL)
    results = []
    for item in items[:max_items]:
        title = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", item, re.DOTALL)
        desc  = re.search(r"<description>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</description>", item, re.DOTALL)
        t = title.group(1).strip() if title else ""
        d = desc.group(1).strip() if desc else ""
        # Strip HTML tags from description
        d = re.sub(r"<[^>]+>", "", d).strip()
        if t:
            results.append({"title": t, "desc": d})
    return results


def get_news(topic: str = "") -> str:
    """
    Fetch live headlines via RSS, then summarize naturally with LLM.
    No raw headline dumping.
    """
    try:
        feed_url = _pick_feed(topic)
        resp = requests.get(feed_url, timeout=8, headers=_HEADERS)
        resp.raise_for_status()
        items = _extract_rss_items(resp.text, max_items=6)

        if not items:
            return "I couldn't find any news right now sir."

        # Format raw data for the LLM
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


# ─── REALTIME WEB QUERY ──────────────────────────────────────────────────────

def realtime_web_query(query: str) -> str:
    """
    Answer a realtime/current-events question by:
    1. Fetching DuckDuckGo instant answer (no API key)
    2. Scraping top Google result snippet (lightweight)
    3. Summarizing with LLM
    Falls back gracefully if scraping fails.
    """
    now_str = datetime.now().strftime("%A, %B %d, %Y at %I:%M %p")
    context_parts = []

    # ── Step 1: DuckDuckGo Instant Answer API ──────────────────────────────
    try:
        ddg_url = f"https://api.duckduckgo.com/?q={quote(query)}&format=json&no_html=1&skip_disambig=1"
        r = requests.get(ddg_url, timeout=6, headers=_HEADERS)
        r.raise_for_status()
        ddg = r.json()

        abstract = ddg.get("AbstractText", "").strip()
        answer   = ddg.get("Answer", "").strip()
        infobox  = ddg.get("Infobox", {})

        if answer:
            context_parts.append(f"Quick answer: {answer}")
        if abstract:
            context_parts.append(f"Summary: {abstract[:400]}")
        if infobox and isinstance(infobox, dict):
            for entry in infobox.get("content", [])[:3]:
                label = entry.get("label", "")
                val   = entry.get("value", "")
                if label and val:
                    context_parts.append(f"{label}: {val}")
    except Exception as e:
        print(f"[DDG ERROR] {e}")

    # ── Step 2: Google search snippet scrape ──────────────────────────────
    try:
        search_url = f"https://www.google.com/search?q={quote(query)}&num=3"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/124.0.0.0 Safari/537.36"
        }
        r = requests.get(search_url, timeout=7, headers=headers)
        if r.status_code == 200:
            text = r.text
            # Extract visible snippets from Google result
            snippets = re.findall(
                r'<div[^>]*class="[^"]*(?:VwiC3b|BNeawe)[^"]*"[^>]*>(.*?)</div>',
                text, re.DOTALL
            )
            clean = []
            for s in snippets[:4]:
                s = re.sub(r"<[^>]+>", "", s).strip()
                if len(s) > 30 and s not in clean:
                    clean.append(s[:200])
            if clean:
                context_parts.append("Web results: " + " | ".join(clean))
    except Exception as e:
        print(f"[GOOGLE SCRAPE ERROR] {e}")

    # ── Step 3: LLM summarize ─────────────────────────────────────────────
    if context_parts:
        context_block = "\n".join(context_parts)
        prompt = f"""You are FRIDAY, a smart AI assistant. Current time: {now_str}.

The user asked: "{query}"

Here is live web data retrieved right now:
{context_block}

Answer the user's question naturally and concisely (under 60 words) based on this data.
Be direct. Speak like a knowledgeable assistant briefing their boss.
If the data doesn't fully answer the question, say what you found and note the limitation."""
    else:
        # No web data — use model's knowledge with date awareness
        prompt = f"""You are FRIDAY, a smart AI assistant. Current time: {now_str}.

The user asked: "{query}"

Answer based on your best knowledge. Be honest if information may be outdated.
Keep it under 60 words. Speak naturally."""

    result = ask_groq(prompt, model=REALTIME_MODEL)
    return result if result else "I couldn't retrieve live information for that right now sir."
