"""
Canonical workspace URL registry for FRIDAY.

All named sites (ChatGPT, Gemini, PW, Notion, NetMirror, Mocktail, dashboards, etc.)
must be defined ONLY here. Other modules resolve URLs via get_workspace_url().

Keys are normalized to lowercase; lookups should use normalize_site_key().
"""

from __future__ import annotations

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
    # Study / personal (paths preserved from prior workspace config where applicable)
    "pw": "https://www.pw.live/study-v2/study",
    "mocktail": "https://www.moctale.in/explore",
    "net mirror": "https://net52.cc/home",
    "netmirror": "https://net52.cc/home",
}


def normalize_site_key(name: str) -> str:
    return (name or "").lower().strip()


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
