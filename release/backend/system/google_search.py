"""
google_search.py — Real Google Search results via Serper.dev API
https://serper.dev — Free: 2,500 queries/month, no credit card.

HOW TO SET UP (one-time, 2 minutes):
1. Go to https://serper.dev
2. Sign up (free, no credit card)
3. Copy your API key
4. Set environment variable: SERPER_API_KEY=your_key_here
   OR add to .env file in FRIDAY root: SERPER_API_KEY=your_key_here

Why Serper: Returns real Google Search results including:
- Organic search results (title + snippet + link)
- Knowledge Graph (Wikipedia-style facts)
- Answer Box (direct answers Google shows at top)
- News results
- Related searches
"""

from __future__ import annotations
import os
import requests
from typing import Any


_ENDPOINT = "https://google.serper.dev/search"
_NEWS_ENDPOINT = "https://google.serper.dev/news"
_TIMEOUT = 8


def _get_api_key() -> str | None:
    """Load Serper API key from .env file or environment variable.
    Priority: .env file > environment variable."""
    # Try loading from .env file in FRIDAY root FIRST (higher priority)
    try:
        env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
        env_path = os.path.normpath(env_path)
        print(f"[SERPER] Checking .env file: {env_path}")
        if os.path.exists(env_path):
            print(f"[SERPER] .env file exists, reading...")
            with open(env_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("SERPER_API_KEY="):
                        key = line.split("=", 1)[1].strip().strip('"').strip("'")
                        masked = key[:4] + "..." + key[-4:] if len(key) > 8 else "***"
                        print(f"[SERPER] API key loaded from .env: {masked}")
                        return key
        else:
            print(f"[SERPER] .env file not found at: {env_path}")
    except Exception as e:
        print(f"[SERPER] Error reading .env file: {e}")
    
    # Fallback to environment variable
    key = os.environ.get("SERPER_API_KEY", "").strip()
    if key:
        masked = key[:4] + "..." + key[-4:] if len(key) > 8 else "***"
        print(f"[SERPER] API key loaded from environment variable (fallback): {masked}")
        return key
    
    print("[SERPER] No API key found in .env file or environment variable")
    return None


def _headers(api_key: str) -> dict:
    return {
        "X-API-KEY": api_key,
        "Content-Type": "application/json",
    }


def google_search(query: str, num: int = 6) -> dict[str, Any]:
    """
    Search Google via Serper API. Returns structured result dict with:
    - organic: list of {title, snippet, link}
    - answerBox: direct answer if available
    - knowledgeGraph: entity data if available
    - news: news results if available
    Returns empty dict if no API key or request fails.
    """
    api_key = _get_api_key()
    if not api_key:
        print("[SERPER] No API key — set SERPER_API_KEY env variable")
        return {}

    try:
        payload = {"q": query, "num": num, "gl": "in", "hl": "en"}
        print(f"[SERPER] Request: endpoint={_ENDPOINT} | query={query[:50]}... | num={num}")
        print(f"[SERPER] Headers: X-API-KEY={api_key[:4]}...{api_key[-4:]} | Content-Type=application/json")
        r = requests.post(
            _ENDPOINT,
            headers=_headers(api_key),
            json=payload,
            timeout=_TIMEOUT,
        )
        print(f"[SERPER] Response: status={r.status_code} | reason={r.reason}")
        r.raise_for_status()
        result = r.json()
        print(f"[SERPER] Success: organic={len(result.get('organic', []))} | answerBox={bool(result.get('answerBox'))} | knowledgeGraph={bool(result.get('knowledgeGraph'))}")
        return result
    except requests.exceptions.HTTPError as e:
        print(f"[SERPER HTTP ERROR] status={e.response.status_code if e.response else 'unknown'} | reason={e.response.reason if e.response else 'unknown'}")
        if e.response and e.response.status_code == 403:
            print(f"[SERPER] 403 Forbidden - API key may be invalid or expired. Check SERPER_API_KEY.")
        return {}
    except Exception as e:
        print(f"[SERPER SEARCH ERROR] {e}")
        return {}


def google_news_search(query: str, num: int = 6) -> list[dict]:
    """
    News-specific Google search via Serper API.
    Returns list of {title, snippet, date, source, link}.
    """
    api_key = _get_api_key()
    if not api_key:
        return []

    try:
        payload = {"q": query, "num": num, "gl": "in", "hl": "en"}
        r = requests.post(
            _NEWS_ENDPOINT,
            headers=_headers(api_key),
            json=payload,
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        return r.json().get("news", [])
    except Exception as e:
        print(f"[SERPER NEWS ERROR] {e}")
        return []


def extract_context_from_google(result: dict, max_organic: int = 4) -> list[str]:
    """
    Extract useful context strings from a Serper API response.
    Returns list of natural-language context strings ready for LLM synthesis.
    """
    parts: list[str] = []

    # 1. Answer Box (highest priority — direct Google answer)
    ab = result.get("answerBox", {})
    if ab:
        answer = ab.get("answer") or ab.get("snippet") or ""
        title  = ab.get("title", "")
        if answer:
            parts.append(f"Google direct answer: {answer.strip()[:300]}")
        elif title:
            parts.append(f"Google answer: {title.strip()[:200]}")

    # 2. Knowledge Graph (entity facts)
    kg = result.get("knowledgeGraph", {})
    if kg:
        desc = kg.get("description", "")
        attrs = kg.get("attributes", {})
        if desc:
            parts.append(f"Knowledge: {desc.strip()[:250]}")
        for k, v in list(attrs.items())[:4]:
            parts.append(f"{k}: {v}")

    # 3. Organic results (web pages)
    organics = result.get("organic", [])
    snippets = []
    for item in organics[:max_organic]:
        title   = item.get("title", "").strip()
        snippet = item.get("snippet", "").strip()[:200]
        date    = item.get("date", "")
        if title and snippet:
            entry = f"{title}: {snippet}"
            if date:
                entry += f" [{date}]"
            snippets.append(entry)
        elif title:
            snippets.append(title)
    if snippets:
        parts.append("Google results:\n" + "\n".join(f"• {s}" for s in snippets))

    # 4. News from organic (sometimes Google includes inline news)
    news = result.get("news", [])
    if news:
        news_items = []
        for n in news[:4]:
            t = n.get("title", "").strip()
            d = n.get("date", "")
            s = n.get("snippet", "").strip()[:120]
            if t:
                entry = t
                if d: entry += f" [{d}]"
                if s: entry += f" — {s}"
                news_items.append(entry)
        if news_items:
            parts.append("Google News:\n" + "\n".join(f"• {n}" for n in news_items))

    return parts


def is_configured() -> bool:
    """Check if Serper API key is available."""
    return bool(_get_api_key())
