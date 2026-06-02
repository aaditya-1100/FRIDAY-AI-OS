"""
Canonical workspace URL registry for FRIDAY.

All named sites (ChatGPT, Gemini, PW, Notion, NetMirror, Mocktail, dashboards, etc.)
must be defined ONLY here. Other modules resolve URLs via get_workspace_url().

Keys are normalized to lowercase; lookups should use normalize_site_key().
"""

from __future__ import annotations

import re
import urllib.parse


# Single source of truth: alias (lowercase) -> HTTPS URL
WORKSPACE_SITES: dict[str, str] = {
    # AI
    "chat gpt": "https://chatgpt.com/",
    "chatgpt": "https://chatgpt.com/",
    "gemini": "https://gemini.google.com/",
    "notion": "https://www.notion.so/",
    # Content
    "youtube": "https://www.youtube.com/",
    "google": "https://www.google.com/",
    "spotify": "https://open.spotify.com/playlist/4JLR7Kas2InqK6QvyTex8J",
    "instagram": "https://www.instagram.com/",
    # Messaging
    "whatsapp": "https://web.whatsapp.com/",
    "whatsapp web": "https://web.whatsapp.com/",
    # Study / personal (paths preserved from prior workspace config where applicable)
    "pw": "https://www.pw.live/study-v2/study",
    "physics wallah": "https://www.pw.live/study-v2/study",
    "mocktail": "https://www.moctale.in/explore",
    "net mirror": "https://net52.cc/home",
    "netmirror": "https://net52.cc/home",
}


def normalize_site_key(name: str) -> str:
    key = (name or "").lower().strip()
    
    # Strip common filler prefixes
    for prefix in ("my ", "the ", "go to ", "open ", "launch ", "start "):
        if key.startswith(prefix):
            key = key[len(prefix):].strip()
            
    # Strip common filler suffixes
    for suffix in (" website", " site", " app", " application", " page", " bookmark", " login"):
        if key.endswith(suffix):
            key = key[:-len(suffix)].strip()
            
    # Universal synonym mapping
    _SYNONYMS = {
        "insta": "instagram",
        "instagram": "instagram",
        "yt": "youtube",
        "gdrive": "drive",
        "google drive": "drive",
        "gmail mail": "gmail",
        "vs code": "vscode",
    }
    return _SYNONYMS.get(key, key)


def get_workspace_url(name: str) -> str | None:
    """Return URL for a registered site alias, or None if unknown."""
    key = normalize_site_key(name)
    url = WORKSPACE_SITES.get(key)
    if url is None or not str(url).strip():
        return None
    return str(url).strip()


def is_registered_site(name: str) -> bool:
    return get_workspace_url(name) is not None


def build_google_search_url(query: str) -> str:
    """Google SERP URL (opened via Chrome policy, not a workspace bookmark)."""
    q = urllib.parse.quote((query or "").strip())
    return f"https://www.google.com/search?q={q}"


def build_youtube_results_url(query: str) -> str:
    """YouTube search results URL (opened via Chrome policy)."""
    q = urllib.parse.quote((query or "").strip())
    return f"https://www.youtube.com/results?search_query={q}"


def infer_url(target: str) -> str:
    """
    Dynamically infer a URL for any target — registered site, domain, or unknown service.
    Priority:
      1. Registered workspace alias
      2. Looks like a domain already (contains dot, no spaces)
      3. Common service patterns (github, reddit, twitter/x, etc.)
      4. Google search fallback (universally works for anything)
    """
    t = (target or "").strip()
    if not t:
        return "https://www.google.com"

    # 1. Registered alias
    url = get_workspace_url(t)
    if url:
        return url

    t_lower = t.lower()

    # 2. Already looks like a domain or URL
    if "." in t and " " not in t:
        if t_lower.startswith("http"):
            return t
        return f"https://{t}"

    # 3. Common service name patterns → canonical URL
    _COMMON = {
        "github": "https://github.com",
        "reddit": "https://www.reddit.com",
        "twitter": "https://twitter.com",
        "x": "https://x.com",
        "instagram": "https://www.instagram.com",
        "linkedin": "https://www.linkedin.com",
        "facebook": "https://www.facebook.com",
        "amazon": "https://www.amazon.in",
        "flipkart": "https://www.flipkart.com",
        "netflix": "https://www.netflix.com",
        "wikipedia": "https://en.wikipedia.org",
        "whatsapp": "https://web.whatsapp.com",
        "gmail": "https://mail.google.com",
        "drive": "https://drive.google.com",
        "maps": "https://maps.google.com",
        "translate": "https://translate.google.com",
        "canva": "https://www.canva.com",
        "figma": "https://www.figma.com",
        "stackoverflow": "https://stackoverflow.com",
        "stack overflow": "https://stackoverflow.com",
        "claude": "https://claude.ai",
        "perplexity": "https://www.perplexity.ai",
        "huggingface": "https://huggingface.co",
        "hugging face": "https://huggingface.co",
    }
    for alias, url in _COMMON.items():
        # Use word-boundary match to avoid 'x' matching 'example', 'xyz' etc.
        if re.search(r'\b' + re.escape(alias) + r'\b', t_lower):
            return url

    # 4. Fallback: Google search — works for literally anything
    q = urllib.parse.quote(t.strip())
    return f"https://www.google.com/search?q={q}"


