"""
URL helpers for media/search. All opens go through system.chrome_opener (real Chrome).
Search URL templates live in config.site_registry (single policy surface).
"""

from __future__ import annotations

from config.site_registry import build_google_search_url, build_youtube_results_url, get_workspace_url
from system.chrome_opener import open_url_in_chrome


def open_url(url: str) -> bool:
    return open_url_in_chrome(url)


def open_youtube() -> bool:
    url = get_workspace_url("youtube") or "https://www.youtube.com/"
    return open_url_in_chrome(url)


def search_google(query: str) -> bool:
    return open_url_in_chrome(build_google_search_url(query))


def search_youtube(query: str) -> bool:
    return youtube_search(query)


def youtube_search(query: str) -> bool:
    try:
        return open_url_in_chrome(build_youtube_results_url(query))
    except Exception as e:
        print(f"[YOUTUBE ERROR] {e}")
        return False
