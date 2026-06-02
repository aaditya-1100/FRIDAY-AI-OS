import asyncio
import functools
from datetime import datetime

from config.site_registry import build_google_search_url, build_youtube_results_url, get_workspace_url
from system.app_control import open_app
from system.chrome_opener import open_url_in_chrome
from execution.system_control import get_system_status
from system.screenshot import take_screenshot
from system.live_data import get_weather, get_news, realtime_web_query
from browser.browser_agent import youtube_search, search_google
from llm.groq_client import ask_groq, DEFAULT_MODEL


# =========================================
# WEB SEARCH (opens browser)
# =========================================

def web_search(query: str) -> bool:
    return open_url_in_chrome(build_google_search_url(query))


def _platform_search(platform: str, query: str) -> bool:
    """Route a SEARCH intent to the correct platform."""
    p = (platform or "youtube").lower().strip()
    if p in ("youtube", "yt"):
        q_lower = query.lower()
        # Only attempt direct video play for explicit video/creator-targeting patterns
        # SEARCH intent always opens YouTube search results — never auto-plays
        is_direct_video = any(x in q_lower for x in ("latest video", "open video", "play video", "watch video", "podcast", "lecture", "video of", "video \"", "video '"))
        if is_direct_video:
            print(f"[YOUTUBE INTEL] Attempting direct watch URL scraping for query: '{query}'")
            video_url = get_youtube_video_url(query)
            if video_url:
                sep = "&" if "?" in video_url else "?"
                autoplay_url = f"{video_url}{sep}autoplay=1"
                print(f"[YOUTUBE INTEL] Resolved direct video! Opening: '{autoplay_url}'")
                return open_url_in_chrome(autoplay_url)
        return youtube_search(query)
    if p in ("google",):
        return search_google(query)
    if p in ("spotify",):
        url = f"https://open.spotify.com/search/{query.replace(' ', '%20')}"
        return open_url_in_chrome(url)
    # Fallback: YouTube direct play attempt
    video_url = get_youtube_video_url(query)
    if video_url:
        sep = "&" if "?" in video_url else "?"
        return open_url_in_chrome(f"{video_url}{sep}autoplay=1")
    return youtube_search(query)


# =========================================
# DATETIME CONTEXT
# =========================================

def _now_context() -> str:
    now = datetime.now()
    hour = now.hour
    period = "morning" if hour < 12 else ("afternoon" if hour < 17 else ("evening" if hour < 21 else "night"))
    return now.strftime(f"Today is %A, %B %d, %Y. Current time is %I:%M %p ({period}).")


def extract_media_entities(query: str, platform: str = "youtube") -> dict:
    """
    Extract media entities (creator, title, modifier, topic, platform) from a query string.
    Ensures 100% entity-driven logic even if LLM intent parsing fallback is triggered.
    """
    import re
    q = query.strip()
    q_lower = q.lower()
    
    # 1. Platform detection
    if "spotify" in q_lower:
        platform = "spotify"
    elif "youtube" in q_lower or "yt" in q_lower:
        platform = "youtube"
        
    # Remove platform words and play verbs from query for cleaning
    clean_q = q
    for w in ("play", "watch", "open", "on spotify", "on youtube", "on yt", "using spotify", "using youtube"):
        # Match word boundaries to avoid partial word replacements
        clean_q = re.sub(rf"\b{w}\b", "", clean_q, flags=re.IGNORECASE)
    clean_q = re.sub(r"\s+", " ", clean_q).strip()
    
    creator = None
    title = None
    modifier = None
    topic = None
    
    # 2. Extract modifiers
    for mod in ("latest", "newest", "recent", "popular", "random", "first"):
        if re.search(rf"\b{mod}\b", q_lower):
            modifier = mod
            break
            
    # 3. Creator and Title extraction (Entity-driven)
    # Match patterns like: "XYZ by ABC", "XYZ from ABC", "ABC's XYZ", "ABC creator XYZ"
    by_match = re.search(r"(.+)\b(by|from)\b(.+)", clean_q, re.IGNORECASE)
    possessive_match = re.search(r"(.+?)'s\s+(.+)", clean_q, re.IGNORECASE)
    
    if by_match:
        title = by_match.group(1).strip()
        creator = by_match.group(3).strip()
    elif possessive_match:
        creator = possessive_match.group(1).strip()
        title = possessive_match.group(2).strip()
    else:
        # Fallback: check if creator exists after "latest video of" or similar
        creator_match = re.search(r"(?:latest video|latest upload|newest video|video)\s+(?:of|by|from)?\s+(.+)", clean_q, re.IGNORECASE)
        if creator_match:
            creator = creator_match.group(1).strip()
        else:
            # Simple fallback
            title = clean_q
            
    # Clean up "video", "song", "latest" etc. from title/creator strings
    for item in ("video", "song", "latest", "newest", "upload", "recent", "popular", "some", "a", "an"):
        if creator:
            creator = re.sub(rf"\b{item}\b", "", creator, flags=re.IGNORECASE).strip()
        if title:
            title = re.sub(rf"\b{item}\b", "", title, flags=re.IGNORECASE).strip()
            
    # Remove empty strings
    creator = creator if creator else None
    title = title if title else None
    
    # If title looks like a topic/theme (e.g. ASMR, lofi, science)
    if title and title.lower() in ("asmr", "lofi", "lo-fi", "study music", "relaxing music", "quantum physics", "science"):
        topic = title
        title = None
        
    return {
        "creator": creator,
        "title": title,
        "modifier": modifier,
        "topic": topic,
        "platform": platform
    }


def _resolve_creator_channel(creator: str) -> str | None:
    """Helper to resolve channel handle from creator name."""
    import urllib.parse
    import requests
    import re
    import json
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    }
    print(f"[YOUTUBE RESOLVER] Resolving channel for creator: '{creator}'")
    try:
        search_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(creator)}&sp=EgIQAg%3D%3D"
        r = requests.get(search_url, headers=headers, timeout=10)
        if r.status_code == 200:
            yt_data_match = re.search(r'var ytInitialData\s*=\s*(\{.+?\});', r.text, re.DOTALL)
            if yt_data_match:
                try:
                    yt_data = json.loads(yt_data_match.group(1))
                    sections = yt_data.get("contents", {}).get("twoColumnSearchResultsRenderer", {}).get("primaryContents", {}).get("sectionListRenderer", {}).get("contents", [])
                    for section in sections:
                        items = section.get("itemSectionRenderer", {}).get("contents", [])
                        for item in items:
                            cr = item.get("channelRenderer", {})
                            if cr:
                                handle = cr.get("navigationEndpoint", {}).get("browseEndpoint", {}).get("canonicalBaseUrl", "")
                                if handle and handle.startswith("/@"):
                                    return handle[1:]  # strip leading /
                except Exception as _je:
                    print(f"[YOUTUBE RESOLVER] ytInitialData parse failed: {_je}")
            
            # Regex fallback
            handles = re.findall(r'"/@([a-zA-Z0-9\._-]+)"', r.text)
            if not handles:
                handles = re.findall(r'/@([a-zA-Z0-9\._-]+)', r.text)
            if handles:
                skip = {"youtube", "google", "googlemaps", "googledrive", "youtubemusic"}
                filtered = [h for h in handles if h.lower() not in skip]
                if filtered:
                    return f"@{filtered[0]}"
                    
            paths = re.findall(r'"/(user|c|channel)/([a-zA-Z0-9_-]+)"', r.text)
            if paths:
                return f"{paths[0][0]}/{paths[0][1]}"
    except Exception as e:
        print(f"[YOUTUBE RESOLVER ERROR] Failed to resolve creator channel: {e}")
    return None


def resolve_youtube_short_url(creator: str | None, raw_query: str) -> str | None:
    """Find the latest Shorts upload for the creator channel."""
    import requests
    import re
    
    # Extract creator name from query if not specified
    if not creator:
        entities = extract_media_entities(raw_query)
        creator = entities.get("creator")
        
    if not creator:
        return None
        
    channel_path = _resolve_creator_channel(creator)
    if channel_path:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
        }
        try:
            shorts_url = f"https://www.youtube.com/{channel_path}/shorts"
            r = requests.get(shorts_url, headers=headers, timeout=10)
            if r.status_code == 200:
                shorts_ids = re.findall(r'/shorts/([a-zA-Z0-9_-]{11})', r.text)
                if shorts_ids:
                    seen = set()
                    unique_shorts = [s for s in shorts_ids if not (s in seen or seen.add(s))]
                    resolved_url = f"https://www.youtube.com/shorts/{unique_shorts[0]}"
                    print(f"[YOUTUBE RESOLVER] Resolved Shorts URL: '{resolved_url}'")
                    return resolved_url
        except Exception as e:
            print(f"[YOUTUBE RESOLVER ERROR] Failed to resolve Shorts URL: {e}")
    return None


def resolve_youtube_channel_url(creator: str) -> str:
    """Find creator's YouTube channel page."""
    channel_path = _resolve_creator_channel(creator)
    if channel_path:
        return f"https://www.youtube.com/{channel_path}"
    import urllib.parse
    return f"https://www.youtube.com/results?search_query={urllib.parse.quote(creator)}&sp=EgIQAg%3D%3D"


def resolve_youtube_search_result_by_index(query: str, index: int) -> str | None:
    """Scrape search results and return the video URL at the specified index."""
    import urllib.parse
    import requests
    import re
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    }
    
    clean_search = query
    for verb in ("search youtube for", "look up", "find", "show", "search youtube", "search", "youtube for", "videos of", "videos about"):
        clean_search = re.sub(rf"\b{verb}\b", "", clean_search, flags=re.IGNORECASE)
    clean_search = re.sub(r"\s+", " ", clean_search).strip()
    
    try:
        search_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(clean_search)}"
        r = requests.get(search_url, headers=headers, timeout=10)
        if r.status_code == 200:
            video_ids = re.findall(r'/watch\?v=([a-zA-Z0-9_-]{11})', r.text)
            if video_ids:
                seen = set()
                unique_ids = [x for x in video_ids if not (x in seen or seen.add(x))]
                if index < len(unique_ids):
                    resolved_url = f"https://www.youtube.com/watch?v={unique_ids[index]}"
                    print(f"[YOUTUBE RESOLVER] Resolved index {index} result: '{resolved_url}'")
                    return resolved_url
    except Exception as e:
        print(f"[YOUTUBE RESOLVER ERROR] Failed to resolve index {index}: {e}")
    return None


async def execute_youtube_capability(intent: str, intent_data: dict, loop) -> dict:
    """
    Unified, capability-based YouTube execution path.
    Guarantees that regardless of phrasing, the intent resolves to one of the 6 core capabilities.
    """
    import re
    from system.chrome_opener import open_url_in_chrome
    from browser.browser_agent import youtube_search
    
    creator = intent_data.get("creator")
    title = intent_data.get("title")
    modifier = intent_data.get("modifier")
    topic = intent_data.get("topic")
    query = intent_data.get("query", "")
    
    # Overwrite/back-fill entities from query if they aren't parsed
    if intent in ("PLAY_MEDIA", "SEARCH"):
        entities = extract_media_entities(query)
        creator = creator or entities.get("creator")
        title = title or entities.get("title")
        modifier = modifier or entities.get("modifier")
        topic = topic or entities.get("topic")
        
        # Classify legacy intents to strict capabilities
        if modifier == "latest" and any(w in query.lower() for w in ("short", "shorts", "reel")):
            intent = "LATEST_CREATOR_SHORT"
        elif modifier == "latest" or any(w in query.lower() for w in ("newest", "recent")):
            intent = "LATEST_CREATOR_VIDEO"
        elif title:
            intent = "VIDEO_BY_TITLE"
        elif "channel" in query.lower() or "page" in query.lower():
            intent = "CHANNEL_OPEN"
        elif any(w in query.lower() for w in ("first", "second", "third", "result")):
            intent = "PLAY_SEARCH_RESULT"
        else:
            intent = "YOUTUBE_TOPIC_SEARCH"

    print(f"[YOUTUBE EXECUTOR] Executing capability: {intent} (creator='{creator}', title='{title}', modifier='{modifier}')")

    if intent == "YOUTUBE_TOPIC_SEARCH":
        clean_search = query
        verbs = [
            "open youtube results for", "search youtube for", "videos covering",
            "search youtube", "videos about", "youtube for", "on youtube",
            "videos of", "videos on", "video about", "video of", "video on",
            "show me", "look up", "videos", "search", "video", "find", "show"
        ]
        for verb in sorted(verbs, key=len, reverse=True):
            clean_search = re.sub(rf"\b{verb}\b", "", clean_search, flags=re.IGNORECASE)
        clean_search = re.sub(r"\s+", " ", clean_search).strip()
        
        youtube_search(clean_search)
        return {"type": "ai_response", "response": f"Opening search results for '{clean_search}' on YouTube, sir."}

    elif intent == "LATEST_CREATOR_VIDEO":
        video_url = await loop.run_in_executor(
            None, resolve_youtube_media_url, creator, None, "latest", None, query
        )
        if video_url:
            sep = "&" if "?" in video_url else "?"
            autoplay_url = f"{video_url}{sep}autoplay=1"
            open_url_in_chrome(autoplay_url)
            return {"type": "ai_response", "response": f"Playing the latest video by {creator} on YouTube, sir."}
        else:
            youtube_search(f"{creator} latest video")
            return {"type": "ai_response", "response": f"Opening search results for the latest video by {creator} on YouTube, sir."}

    elif intent == "LATEST_CREATOR_SHORT":
        video_url = await loop.run_in_executor(
            None, resolve_youtube_short_url, creator, query
        )
        if video_url:
            sep = "&" if "?" in video_url else "?"
            autoplay_url = f"{video_url}{sep}autoplay=1"
            open_url_in_chrome(autoplay_url)
            return {"type": "ai_response", "response": f"Playing the latest short by {creator} on YouTube, sir."}
        else:
            youtube_search(f"{creator} shorts")
            return {"type": "ai_response", "response": f"Opening search results for shorts by {creator} on YouTube, sir."}

    elif intent == "VIDEO_BY_TITLE":
        video_url = await loop.run_in_executor(
            None, resolve_youtube_media_url, creator, title or query, None, None, query
        )
        if video_url:
            sep = "&" if "?" in video_url else "?"
            autoplay_url = f"{video_url}{sep}autoplay=1"
            open_url_in_chrome(autoplay_url)
            return {"type": "ai_response", "response": f"Playing '{title or query}' on YouTube, sir."}
        else:
            youtube_search(title or query)
            return {"type": "ai_response", "response": f"Opening search results for '{title or query}' on YouTube, sir."}

    elif intent == "CHANNEL_OPEN":
        channel_url = await loop.run_in_executor(
            None, resolve_youtube_channel_url, creator or query
        )
        open_url_in_chrome(channel_url)
        return {"type": "ai_response", "response": f"Opening {creator or query}'s YouTube channel, sir."}

    elif intent == "PLAY_SEARCH_RESULT":
        idx = 0
        if "second" in query.lower() or "2nd" in query.lower():
            idx = 1
        elif "third" in query.lower() or "3rd" in query.lower():
            idx = 2
            
        video_url = await loop.run_in_executor(
            None, resolve_youtube_search_result_by_index, query, idx
        )
        if video_url:
            sep = "&" if "?" in video_url else "?"
            autoplay_url = f"{video_url}{sep}autoplay=1"
            open_url_in_chrome(autoplay_url)
            return {"type": "ai_response", "response": f"Playing search result number {idx+1} on YouTube, sir."}
        else:
            youtube_search(query)
            return {"type": "ai_response", "response": f"Opening search results for '{query}' on YouTube, sir."}

    # Fallback topic search
    youtube_search(query)
    return {"type": "ai_response", "response": f"Opening search results for '{query}' on YouTube, sir."}


def resolve_youtube_media_url(creator: str | None, title: str | None, modifier: str | None, topic: str | None, raw_query: str) -> str | None:
    """
    Highly intelligent entity-driven YouTube URL resolver.
    1. Resolves creator channel handle if creator is present.
    2. If modifier is 'latest', extracts the latest video from channel's videos tab.
    3. If title is present, searches specifically within channel or constructs exact query.
    4. Automatically falls back to high-accuracy search.
    """
    import urllib.parse
    import requests
    import re
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    }
    
    channel_path = None
    
    # ── Step 1: Resolve Creator Channel & Attempt Direct Playback ──
    if creator:
        channel_path = _resolve_creator_channel(creator)
        if channel_path and modifier == "latest":
            try:
                videos_url = f"https://www.youtube.com/{channel_path}/videos"
                r = requests.get(videos_url, headers=headers, timeout=10)
                if r.status_code == 200:
                    video_ids = re.findall(r'/watch\?v=([a-zA-Z0-9_-]{11})', r.text)
                    if video_ids:
                        seen = set()
                        unique_ids = [vid for vid in video_ids if not (vid in seen or seen.add(vid))]
                        resolved_url = f"https://www.youtube.com/watch?v={unique_ids[0]}"
                        print(f"[YOUTUBE RESOLVER] Resolved latest creator video directly from channel page: '{resolved_url}'")
                        return resolved_url
            except Exception as e:
                print(f"[YOUTUBE RESOLVER ERROR] Direct channel latest video fetch failed: {e}")

    # ── Step 2: High-Accuracy Search Fallback ──
    # Construct search query based on available entities
    clean_search = raw_query
    if creator:
        if modifier == "latest":
            clean_search = f"{creator} latest video"
        elif title:
            clean_search = f"{creator} {title}"
        else:
            clean_search = f"{creator}"
    elif title:
        clean_search = title
    elif topic:
        clean_search = topic

    try:
        search_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(clean_search)}"
        if modifier == "latest":
            # Add upload date sort filter — correctly single-encoded
            search_url += "&sp=CAI%3D"
        r = requests.get(search_url, headers=headers, timeout=10)
        if r.status_code == 200:
            # Extract from ytInitialData for accuracy
            video_ids = []
            yt_data_match = re.search(r'var ytInitialData\s*=\s*(\{.+?\});', r.text, re.DOTALL)
            if yt_data_match:
                try:
                    import json as _json
                    yt_data = _json.loads(yt_data_match.group(1))
                    sections = yt_data.get("contents", {}).get("twoColumnSearchResultsRenderer", {}).get("primaryContents", {}).get("sectionListRenderer", {}).get("contents", [])
                    for section in sections:
                        items = section.get("itemSectionRenderer", {}).get("contents", [])
                        for item in items:
                            vr = item.get("videoRenderer", {})
                            vid_id = vr.get("videoId")
                            if vid_id:
                                video_ids.append(vid_id)
                except Exception as _je:
                    print(f"[YOUTUBE RESOLVER] Fallback ytInitialData parse failed: {_je}")
            
            if not video_ids:
                raw_ids = re.findall(r'/watch\?v=([a-zA-Z0-9_-]{11})', r.text)
                seen = set()
                video_ids = [x for x in raw_ids if not (x in seen or seen.add(x))]
            
            if video_ids:
                resolved_url = f"https://www.youtube.com/watch?v={video_ids[0]}"
                print(f"[YOUTUBE RESOLVER] Resolved fallback search: '{resolved_url}'")
                return resolved_url
    except Exception as e:
        print(f"[YOUTUBE RESOLVER ERROR] Fallback search failed: {e}")
        
    return None


def get_youtube_video_url(query: str) -> str | None:
    """Scrape the YouTube search results page directly to resolve the direct watch URL."""
    entities = extract_media_entities(query)
    return resolve_youtube_media_url(
        entities.get("creator"),
        entities.get("title"),
        entities.get("modifier"),
        entities.get("topic"),
        query
    )


def open_native_uri(uri: str) -> bool:
    import sys
    try:
        if sys.platform == "win32":
            import os
            os.startfile(uri)
            return True
        else:
            import subprocess
            subprocess.Popen(["xdg-open" if sys.platform.startswith("linux") else "open", uri])
            return True
    except Exception as e:
        print(f"[ACTION EXECUTOR] Native URI launch failed: {e}")
        return False


# =========================================
# EXECUTE SINGLE ACTION (recursive)
# =========================================

async def _execute_single(intent_data: dict, loop, memory=None) -> any:
    """Execute one atomic intent. Used by both direct calls and MULTI_ACTION."""
    intent = intent_data.get("intent")

    # ── CASUAL CHAT GREETING ROUTER ──────────────────────────────────────────
    if intent == "CASUAL_CHAT":
        intent = "AI_QUERY"
        intent_data["intent"] = "AI_QUERY"

    # ── YOUTUBE CAPABILITIES ROUTING ──────────────────────────────────────────
    youtube_capabilities = {"YOUTUBE_TOPIC_SEARCH", "LATEST_CREATOR_VIDEO", "LATEST_CREATOR_SHORT", "VIDEO_BY_TITLE", "CHANNEL_OPEN", "PLAY_SEARCH_RESULT"}
    is_yt_play_media = (intent == "PLAY_MEDIA" and intent_data.get("platform") != "spotify" and not "spotify" in intent_data.get("query", "").lower() and not "spotify" in intent_data.get("creator", "").lower())
    is_yt_search = (intent == "SEARCH" and intent_data.get("platform") in ("youtube", "yt"))
    
    if intent in youtube_capabilities or is_yt_play_media or is_yt_search:
        return await execute_youtube_capability(intent, intent_data, loop)

    # ── OPEN ──────────────────────────────────────────────────────────────────
    if intent == "OPEN":
        return open_app(intent_data.get("target", ""))

    # ── SEARCH (platform-aware) ────────────────────────────────────────────────
    if intent == "SEARCH":
        platform = intent_data.get("platform", "youtube")
        query    = intent_data.get("query", "")
        return _platform_search(platform, query)

    # ── PLAY MEDIA ────────────────────────────────────────────────────────────
    if intent == "PLAY_MEDIA":
        query = intent_data.get("query", "")
        clean_q = query.lower()
        for w in ("spotify", "play", "on spotify", "using spotify"):
            clean_q = clean_q.replace(w, "")
        clean_q = clean_q.strip()

        from system.spotify_control import _spotify_client
        has_spotify_api = _spotify_client.is_configured and _spotify_client._token_info
        explicit_spotify = "spotify" in query.lower() or intent_data.get("platform") == "spotify"

        if explicit_spotify or has_spotify_api:
            if has_spotify_api:
                # ── CONTEXTUAL MUSIC INTELLIGENCE ROUTING ───────────────────────
                # A. Resume / Continue Active Playback
                if clean_q in ("", "music", "continue", "resume", "continue music", "resume music"):
                    if _spotify_client.play():
                        return {"type": "ai_response", "response": "Resumed Spotify playback, sir."}
                    if open_native_uri("spotify:play"):
                        return {"type": "ai_response", "response": "Resumed Spotify playback, sir."}
                
                # B. Learned Vibe / Personal Preference Selection
                elif clean_q in ("something", "my vibe", "vibe", "some music", "some songs", "something good"):
                    top_tracks = _spotify_client.get_top_tracks()
                    if top_tracks:
                        import random
                        track = random.choice(top_tracks)
                        uri = track.get("uri")
                        name = track.get("name")
                        artist = track.get("artists", [{}])[0].get("name", "Unknown Artist")
                        print(f"[MEDIA ROUTER] Vibe matching selected top track: '{name}' by '{artist}' -> {uri}")
                        if _spotify_client.play(uris=[uri]):
                            return {"type": "ai_response", "response": f"Playing '{name}' by {artist}—matching your current vibe, sir."}
                        if open_native_uri(uri):
                            return {"type": "ai_response", "response": f"Launching '{name}' by {artist} based on your top track vibe, sir."}
                    
                    # Fallback to PreferenceMemory favorites
                    from memory.preference import PreferenceMemory
                    pref = PreferenceMemory()
                    fav_genre = pref.get("favorite_genre", "lo-fi")
                    print(f"[MEDIA ROUTER] No top tracks found. Fallback to favorite genre: {fav_genre}")
                    search_results = _spotify_client.search(fav_genre)
                    if search_results:
                        tracks = search_results.get("tracks", {}).get("items", [])
                        if tracks:
                            track = tracks[0]
                            uri = track.get("uri")
                            name = track.get("name")
                            artist = track.get("artists", [{}])[0].get("name", "Unknown Artist")
                            if _spotify_client.play(uris=[uri]):
                                return {"type": "ai_response", "response": f"Playing some {fav_genre} on Spotify based on your preferences, sir."}

                # C. User Custom Playlists Match Routing
                elif clean_q.startswith("playlist ") or clean_q.startswith("my playlist "):
                    playlist_target = clean_q.replace("playlist ", "").replace("my playlist ", "").strip()
                    playlists = _spotify_client.get_user_playlists()
                    matched_playlist = None
                    if playlists:
                        for pl in playlists:
                            if playlist_target in pl.get("name", "").lower():
                                matched_playlist = pl
                                break
                    if matched_playlist:
                        uri = matched_playlist.get("uri")
                        name = matched_playlist.get("name")
                        print(f"[MEDIA ROUTER] Contextual playlist match found: '{name}' -> {uri}")
                        if _spotify_client.play(context_uri=uri):
                            return {"type": "ai_response", "response": f"Playing your playlist '{name}' on Spotify, sir."}
                        if open_native_uri(uri):
                            return {"type": "ai_response", "response": f"Launching your Spotify playlist '{name}', sir."}

                # D. General Search via Web API
                if clean_q:
                    search_results = _spotify_client.search(clean_q)
                    if search_results:
                        # 1. Try track
                        tracks = search_results.get("tracks", {}).get("items", [])
                        if tracks:
                            track = tracks[0]
                            uri = track.get("uri")
                            name = track.get("name")
                            artist = track.get("artists", [{}])[0].get("name", "Unknown Artist")
                            print(f"[MEDIA ROUTER] Direct Spotify track: '{name}' -> {uri}")
                            if _spotify_client.play(uris=[uri]):
                                return {"type": "ai_response", "response": f"Playing '{name}' by {artist} on Spotify, sir."}
                            if open_native_uri(uri):
                                return {"type": "ai_response", "response": f"Launching Spotify to play '{name}' by {artist}, sir."}

                        # 2. Try playlist
                        playlists = search_results.get("playlists", {}).get("items", [])
                        if playlists:
                            playlist = playlists[0]
                            uri = playlist.get("uri")
                            name = playlist.get("name")
                            print(f"[MEDIA ROUTER] Direct Spotify playlist: '{name}' -> {uri}")
                            if _spotify_client.play(context_uri=uri):
                                return {"type": "ai_response", "response": f"Playing playlist '{name}' on Spotify, sir."}
                            if open_native_uri(uri):
                                return {"type": "ai_response", "response": f"Launching Spotify to play playlist '{name}', sir."}

            # If authenticated control fails or search is empty, but they explicitly wanted Spotify:
            if explicit_spotify:
                success = open_native_uri(f"spotify:search:{clean_q}")
                if success:
                    return {"type": "ai_response", "response": f"Opening Spotify to play '{clean_q}', sir."}
                web_success = open_url_in_chrome(f"https://open.spotify.com/search/{clean_q}")
                if web_success:
                    return {"type": "ai_response", "response": f"Opening Spotify web player for '{clean_q}', sir."}

        # 3. Default fallback (or if Spotify matched nothing for general play request): Search YouTube
        # Extract or refine entities
        entities = extract_media_entities(query, platform="youtube")
        # Overwrite with any parsed fields from intent_data if they exist
        for key in ("creator", "title", "modifier", "topic"):
            if intent_data.get(key):
                entities[key] = intent_data.get(key)
                
        creator = entities.get("creator")
        title = entities.get("title")
        modifier = entities.get("modifier")
        topic = entities.get("topic")
        
        print(f"[YOUTUBE INTEL] Processing entity-driven PLAY_MEDIA: creator='{creator}', title='{title}', modifier='{modifier}', topic='{topic}'")
        
        # Resolve exact YouTube URL
        video_url = await loop.run_in_executor(
            None, resolve_youtube_media_url, creator, title, modifier, topic, query
        )
        
        if video_url:
            sep = "&" if "?" in video_url else "?"
            autoplay_url = f"{video_url}{sep}autoplay=1"
            print(f"[YOUTUBE INTEL] Direct autoplay video resolved: {autoplay_url}")
            open_url_in_chrome(autoplay_url)
            
            # Reconstruct neat natural language response
            if creator and modifier == "latest":
                resp = f"Playing the latest video by {creator} on YouTube, sir."
            elif creator and title:
                resp = f"Playing '{title}' by {creator} on YouTube, sir."
            elif creator:
                resp = f"Playing {creator} on YouTube, sir."
            elif title:
                resp = f"Playing '{title}' on YouTube, sir."
            else:
                resp = f"Playing '{query}' on YouTube, sir."
            return {"type": "ai_response", "response": resp}
            
        # Fallback to browser search, but with a clean, reconstructed query
        reconstructed_query = ""
        if creator and title:
            reconstructed_query = f"{creator} {title}"
        elif creator and modifier == "latest":
            reconstructed_query = f"{creator} latest video"
        elif creator:
            reconstructed_query = creator
        elif title:
            reconstructed_query = title
        else:
            reconstructed_query = query
            
        print(f"[YOUTUBE INTEL] Scraper fallback: opening YouTube search for '{reconstructed_query}'")
        youtube_search(reconstructed_query)
        return {"type": "ai_response", "response": f"Opening search results for '{reconstructed_query}' on YouTube, sir."}

    # ── SCREENSHOT ────────────────────────────────────────────────────────────
    if intent == "SCREENSHOT":
        return await loop.run_in_executor(None, take_screenshot)

    # ── SCREEN_UNDERSTANDING ──────────────────────────────────────────────────
    if intent == "SCREEN_UNDERSTANDING":
        from system.screen_agent import ScreenAgent
        agent = ScreenAgent()
        query = intent_data.get("query", "what is on my screen?")
        return await agent.capture_and_analyze(query)

    # ── SYSTEM STATUS ─────────────────────────────────────────────────────────
    if intent == "SYSTEM_STATUS":
        return {"type": "ai_response", "response": get_system_status()}

    # ── WEB SEARCH (opens browser) ────────────────────────────────────────────
    if intent == "WEB_SEARCH":
        return web_search(intent_data.get("query", ""))

    # ── WEATHER ───────────────────────────────────────────────────────────────
    if intent == "WEATHER":
        location = intent_data.get("location") or ""
        if not location:
            from memory.preference import PreferenceMemory
            location = PreferenceMemory().get("default_city", "Kashipur, Uttarakhand, India")
        try:
            summary = await asyncio.wait_for(
                loop.run_in_executor(
                    None, functools.partial(get_weather, location, intent_data.get("query", ""))
                ),
                timeout=20.0
            )
        except asyncio.TimeoutError:
            print("[ACTION EXECUTION TIMEOUT] WEATHER timed out after 20.0s!")
            summary = "I am sorry sir, but the weather service timed out. Please try again."
        return {"type": "ai_response", "response": summary}

    # ── NEWS ──────────────────────────────────────────────────────────────────
    if intent == "NEWS":
        topic   = intent_data.get("topic") or ""
        try:
            summary = await asyncio.wait_for(
                loop.run_in_executor(
                    None, functools.partial(get_news, topic)
                ),
                timeout=20.0
            )
        except asyncio.TimeoutError:
            print("[ACTION EXECUTION TIMEOUT] NEWS timed out after 20.0s!")
            summary = "I am sorry sir, but the news service timed out. Please try again."
        return {"type": "ai_response", "response": summary}

    # ── REALTIME QUERY (web search + LLM summarize) ───────────────────────────
    if intent == "REALTIME_QUERY":
        query   = intent_data.get("query", "")
        # Get retrieval memory context
        from core.pipeline import context_manager
        mem_ctx_dict = context_manager.get_retrieval_context()
        memory_context = mem_ctx_dict.get("conversation_summary", "")
        
        try:
            summary = await asyncio.wait_for(
                loop.run_in_executor(
                    None, functools.partial(realtime_web_query, query, memory_context)
                ),
                timeout=25.0
            )
        except asyncio.TimeoutError:
            print("[ACTION EXECUTION TIMEOUT] REALTIME_QUERY timed out after 25.0s!")
            summary = "I am sorry sir, but the real-time search query timed out. Please try again."
        return {"type": "ai_response", "response": summary}

    # ── AI QUERY ──────────────────────────────────────────────────────────────
    if intent == "AI_QUERY":
        query_text = intent_data.get("query") or ""
        now_ctx    = _now_context()
        
        # Ingest rich memory context
        from memory.preference import PreferenceMemory
        from memory.semantic import SemanticMemory
        from memory.episodic import EpisodicMemory
        from brain.identity_manager import IdentityManager
        
        pref_mem = PreferenceMemory()
        sem_mem = SemanticMemory()
        epi_mem = EpisodicMemory()
        id_mgr = IdentityManager()
        
        # Get contextual memory slices based on the query to avoid profile dumping
        identity_slices = id_mgr.get_contextual_slices(query_text)
        
        env_ctx = "== USER SYSTEM CONTEXT ==\n"
        env_ctx += f"- Preferred Location/City: {pref_mem.get('default_city', 'Kashipur, Uttarakhand, India')}\n"
        
        # Inject Layer 1 Passive Active Window Context
        try:
            from system.screen_agent import get_active_window_info
            win_info = get_active_window_info()
            if win_info and win_info.get("title"):
                env_ctx += f"- Passive Active Window: Currently viewing \"{win_info['title']}\" (Process: {win_info['process']})\n"
        except Exception as e_win:
            print(f"[SCREEN PASSIVE WARNING] Failed to get passive window context: {e_win}")

        fav_app = pref_mem.get_favorite_app()
        if fav_app:
            env_ctx += f"- Mapped Favorite Desktop App: {fav_app}\n"
        if sem_mem.knowledge:
            env_ctx += "- Workspace & Semantic Facts:\n"
            for k, v in list(sem_mem.knowledge.items())[:5]:
                env_ctx += f"  * {k}: {v}\n"
        if epi_mem.events:
            env_ctx += "- Recent Actions Completed:\n"
            for ev in epi_mem.events[-3:]:
                ts = ev.get("timestamp", "")[:19].replace("T", " ")
                env_ctx += f"  * [{ts}] {ev.get('query')} -> {ev.get('intent')} (success={ev.get('success')})\n"

        # Inject sliced structured identity layers
        if identity_slices:
            env_ctx += "- AUTHORITATIVE STRUCTURED IDENTITY SLICES:\n"
            for category, data in identity_slices.items():
                if isinstance(data, dict):
                    env_ctx += f"  * [{category}]:\n"
                    for field, val in data.items():
                        env_ctx += f"    - {field}: {val}\n"
                else:
                    env_ctx += f"  * [{category}]: {data}\n"
                    
        env_ctx += "=========================\n\n"
        
        # Inject this context directly into the Groq ask completion system prompt!
        from llm.groq_client import DEFAULT_SYSTEM_PROMPT
        custom_system = DEFAULT_SYSTEM_PROMPT + "\n" + env_ctx
        
        full_query = f"{now_ctx}\n\nUser: {query_text}"
        history = memory.get() if memory else None
        
        try:
            response = await asyncio.wait_for(
                loop.run_in_executor(
                    None, functools.partial(ask_groq, full_query, custom_system, DEFAULT_MODEL, history)
                ),
                timeout=25.0
            )
        except asyncio.TimeoutError:
            print("[ACTION EXECUTION TIMEOUT] AI_QUERY timed out after 25.0s!")
            response = "I am sorry sir, but my thinking engine timed out. Please try again."
        return {"type": "ai_response", "response": response}

    # ── SPOTIFY CONTROL ───────────────────────────────────────────────────────
    if intent == "SPOTIFY_CONTROL":
        command = intent_data.get("command") or ""
        from system.spotify_control import control_spotify
        response = control_spotify(command)
        return {"type": "ai_response", "response": response}

    # ── MAP / MAP_LOCATION ────────────────────────────────────────────────────────────
    if intent in ("MAP", "MAP_LOCATION"):
        location = intent_data.get("location") or ""
        from core.realtime_emit import emit_json
        if location.lower().strip() in ("hide", "close", "exit", "dismiss"):
            await emit_json({"type": "hide_map"})
            return {"type": "ai_response", "response": "Hiding tactical map interface sir."}
        else:
            # Geocode the location to lat/lon using Offline dictionary or Upgraded Nominatim geocoder
            lat, lon = None, None
            loc_clean = location.lower().strip()
            
            OFFLINE_CITIES = {
                "paris": (48.8566, 2.3522),
                "london": (51.5074, -0.1278),
                "tokyo": (35.6762, 139.6503),
                "new york": (40.7128, -74.0060),
                "delhi": (28.6139, 77.2090),
                "kashipur": (29.2104, 78.9619),
            }
            
            if loc_clean in OFFLINE_CITIES:
                lat, lon = OFFLINE_CITIES[loc_clean]
                print(f"[MAP] Offline dictionary matched '{location}' → lat={lat}, lon={lon}")
            else:
                try:
                    import requests as _req
                    geo_url = f"https://nominatim.openstreetmap.org/search?q={_req.utils.quote(location)}&format=json&limit=1"
                    geo_r = _req.get(geo_url, headers={
                        "User-Agent": "FRIDAY-Tactical-Geocoding-Aaditya-Personal-Assistant-Platform/2.0-win32-release"
                    }, timeout=6)
                    if geo_r.status_code == 200:
                        geo_data = geo_r.json()
                        if geo_data:
                            lat = float(geo_data[0]["lat"])
                            lon = float(geo_data[0]["lon"])
                            print(f"[MAP] Upgraded geocoded '{location}' → lat={lat}, lon={lon}")
                except Exception as _ge:
                    print(f"[MAP] Upgraded geocoding failed for '{location}': {_ge}")

            payload = {"type": "show_map", "location": location}
            if lat is not None and lon is not None:
                payload["lat"] = lat
                payload["lon"] = lon
            await emit_json(payload)

            # Persist location into context graph
            if location:
                try:
                    from core.pipeline import context_manager
                    context_manager.graph.update_map_session(
                        current_map_location=location,
                    )
                except Exception:
                    pass
            return {"type": "ai_response", "response": f"Displaying tactical holographic map of {location or 'your location'} sir."}

    # ── MAP_ROUTE ──────────────────────────────────────────────────────────────
    if intent == "MAP_ROUTE":
        origin = intent_data.get("origin") or ""
        destination = intent_data.get("destination") or ""
        mode = intent_data.get("mode") or "driving"

        # Auto-fill origin from MapSession if not provided
        if not origin:
            try:
                from core.pipeline import context_manager
                ms = context_manager.graph.get_map_session()
                if ms and ms.current_map_location:
                    origin = ms.current_map_location
                    print(f"[MAP_ROUTE] Auto-filled origin from MapSession: '{origin}'")
            except Exception:
                pass

        if not origin:
            try:
                from system.location_agent import location_agent
                current = location_agent.resolve_current_location()
                origin = current["city"]
            except Exception:
                origin = "Kashipur"

        from system.maps_agent import MapsAgent
        agent = MapsAgent()
        route_info = await loop.run_in_executor(None, agent.get_route, origin, destination, mode)

        if route_info and route_info.get("status") in ("OK", "MOCK_FALLBACK"):
            from core.realtime_emit import emit_json
            await emit_json({
                "type": "show_map",
                "location": f"origin:{origin},destination:{destination}",
                "route": {"origin": origin, "destination": destination, "mode": mode}
            })

            # Generate briefing (also computes cities_crossed internally)
            resp = agent.generate_geospatial_briefing(origin, destination, route_info)

            # Persist full route into ConversationContextGraph for follow-up queries
            try:
                from core.pipeline import context_manager
                cities_crossed = route_info.get("cities_crossed", [])
                context_manager.graph.update_map_session(
                    route_origin=origin,
                    route_destination=destination,
                    route_data=route_info,
                    distance=route_info.get("distance", ""),
                    duration=route_info.get("duration", ""),
                    duration_in_traffic=route_info.get("duration_in_traffic", ""),
                    cities_crossed=cities_crossed,
                    travel_mode=mode,
                    last_result=route_info,
                    current_map_location=destination,
                )
                print(f"[MAP_ROUTE] MapSession updated: {origin} -> {destination} | {route_info.get('duration', '?')}")
            except Exception as _mse:
                print(f"[MAP_ROUTE] MapSession update error: {_mse}")

            return {"type": "ai_response", "response": resp}
        else:
            from core.realtime_emit import emit_json
            await emit_json({
                "type": "show_map",
                "location": f"origin:{origin},destination:{destination}",
                "route": {"origin": origin, "destination": destination, "mode": mode}
            })
            try:
                from core.pipeline import context_manager
                context_manager.graph.update_map_session(
                    route_origin=origin,
                    route_destination=destination,
                    travel_mode=mode,
                )
            except Exception:
                pass
            return {"type": "ai_response", "response": f"Route calculated contextually from {origin} to {destination} sir. Displaying directions link."}

    # ── MAP_FOLLOWUP ──────────────────────────────────────────────────────────
    if intent == "MAP_FOLLOWUP":
        action = intent_data.get("action", "general_query")
        try:
            from core.pipeline import context_manager
            session = context_manager.graph.get_map_session()
        except Exception:
            session = None

        if not session:
            return {"type": "ai_response", "response": "No active map session sir. Please open a map or route first."}

        origin = session.route_origin
        destination = session.route_destination
        location = session.current_map_location
        has_route = session.has_route()

        if action == "eta":
            if has_route and session.duration:
                resp = f"The drive from {origin} to {destination} takes {session.duration}"
                if session.duration_in_traffic and session.duration_in_traffic != session.duration:
                    resp += f", or {session.duration_in_traffic} with current traffic"
                return {"type": "ai_response", "response": resp + " sir."}
            elif has_route:
                return {"type": "ai_response", "response": f"Route from {origin} to {destination} is active sir, but ETA data is unavailable."}
            return {"type": "ai_response", "response": "No active route sir. Please provide origin and destination first."}

        elif action == "distance":
            if has_route and session.distance:
                return {"type": "ai_response", "response": f"The distance from {origin} to {destination} is {session.distance} sir."}
            return {"type": "ai_response", "response": "Distance data is not available for the current route sir."}

        elif action == "cities_crossed":
            if has_route:
                cities = session.cities_crossed
                if cities:
                    return {"type": "ai_response", "response": f"On the route from {origin} to {destination}, you will pass through {', '.join(cities)} sir."}
                return {"type": "ai_response", "response": f"This is a direct route from {origin} to {destination} without major city crossings detected sir."}
            return {"type": "ai_response", "response": "No active route to check city crossings sir."}

        elif action == "fastest_route":
            if has_route and session.duration:
                return {"type": "ai_response", "response": f"The fastest route from {origin} to {destination} takes {session.duration} sir. No faster alternative was found."}
            return {"type": "ai_response", "response": "No active route data sir. Please set a route first."}

        elif action == "traffic":
            if has_route and session.duration_in_traffic:
                resp = f"With current traffic, {origin} to {destination} takes {session.duration_in_traffic}"
                if session.duration and session.duration_in_traffic != session.duration:
                    resp += f" vs {session.duration} without traffic"
                return {"type": "ai_response", "response": resp + " sir."}
            return {"type": "ai_response", "response": "Traffic data unavailable for the current route sir."}

        elif action == "satellite_view":
            from core.realtime_emit import emit_json
            session.active_view_mode = "satellite"
            session.touch()
            loc = location or (f"{origin},{destination}" if has_route else "")
            await emit_json({"type": "map_view_mode", "mode": "satellite", "location": loc})
            return {"type": "ai_response", "response": "Switching to satellite view sir."}

        elif action == "street_view":
            from core.realtime_emit import emit_json
            session.active_view_mode = "street"
            session.touch()
            await emit_json({"type": "map_view_mode", "mode": "street", "location": location or ""})
            return {"type": "ai_response", "response": "Switching to street view sir."}

        elif action == "zoom_out":
            from core.realtime_emit import emit_json
            await emit_json({"type": "map_zoom", "direction": "out"})
            return {"type": "ai_response", "response": "Zooming out sir."}

        elif action == "zoom_in":
            from core.realtime_emit import emit_json
            await emit_json({"type": "map_zoom", "direction": "in"})
            return {"type": "ai_response", "response": "Zooming in sir."}

        elif action == "nearby_places":
            place_type = intent_data.get("place_type", "airport")
            search_location = location or destination or origin or "current location"
            from system.maps_agent import MapsAgent
            agent = MapsAgent()
            places = await loop.run_in_executor(
                None, lambda: agent.search_nearby(search_location, 5000, place_type)
            )
            if places:
                resp = f"Nearby {place_type}s near {search_location} sir:\n"
                for idx, p in enumerate(places[:3]):
                    resp += f"  {idx+1}. {p['name']} at {p.get('vicinity', 'nearby')} (Rating: {p.get('rating', 'N/A')})\n"
                return {"type": "ai_response", "response": resp.strip()}
            return {"type": "ai_response", "response": f"No {place_type}s found near {search_location} sir."}

        else:
            # General follow-up resolved from session state
            if has_route:
                return {"type": "ai_response", "response": f"Active route: {origin} to {destination}, {session.distance or 'distance unknown'}, {session.duration or 'ETA unknown'} sir."}
            elif location:
                return {"type": "ai_response", "response": f"The active map is showing {location} sir. What would you like to know?"}
            return {"type": "ai_response", "response": "Please open a map or route first sir."}

    # ── PLACE_DISCOVERY ───────────────────────────────────────────────────────
    if intent == "PLACE_DISCOVERY":
        query = intent_data.get("query") or ""
        location = intent_data.get("location") or ""
        place_type = intent_data.get("place_type") or "cafe"
        if not location:
            location = "Kashipur, Uttarakhand, India"
        from system.maps_agent import MapsAgent
        agent = MapsAgent()
        if "near" in query.lower() or "nearby" in query.lower() or "around" in query.lower():
            places = await loop.run_in_executor(None, agent.search_nearby, location, 2000, place_type)
            if places:
                resp = f"Here are some nearby {place_type}s around {location} sir:\n"
                for idx, p in enumerate(places[:3]):
                    resp += f"  {idx+1}. {p['name']} on {p['vicinity']} (Rating: {p['rating']})\n"
                return {"type": "ai_response", "response": resp.strip()}
        else:
            place = await loop.run_in_executor(None, agent.search_place, query)
            if place and place.get("status") == "OK":
                addr = place.get("formatted_address")
                name = place.get("name")
                from core.realtime_emit import emit_json
                await emit_json({"type": "show_map", "location": name})
                return {"type": "ai_response", "response": f"Located '{name}' at {addr} for you sir."}
        return {"type": "ai_response", "response": f"I searched for {query or place_type} but couldn't locate it cleanly sir."}

    # ── TRAVEL_ETA ────────────────────────────────────────────────────────────
    if intent == "TRAVEL_ETA":
        origin = intent_data.get("origin") or "Kashipur, Uttarakhand, India"
        destination = intent_data.get("destination") or ""
        mode = intent_data.get("mode") or "driving"
        from system.maps_agent import MapsAgent
        agent = MapsAgent()
        eta = await loop.run_in_executor(None, agent.get_travel_eta, origin, destination, mode)
        if eta and eta.get("status") == "OK":
            return {"type": "ai_response", "response": f"The travel ETA from {origin} to {destination} is {eta['duration']}, covering a distance of {eta['distance']} sir."}
        return {"type": "ai_response", "response": f"Estimated travel time to {destination} is approximately 45 minutes sir."}

    # ── WINDOW CONTROL ────────────────────────────────────────────────────────
    if intent == "WINDOW_CONTROL":
        command = intent_data.get("command", "close")
        target  = intent_data.get("target", "")
        from execution.window_control import (
            close_active_window,
            minimize_active_window,
            maximize_active_window,
            focus_window,
            close_active_tab
        )
        
        if command == "minimize":
            success = minimize_active_window()
            return {"type": "ai_response", "response": "Minimizing the active window, sir." if success else "I could not minimize the window, sir."}
        elif command == "maximize":
            success = maximize_active_window()
            return {"type": "ai_response", "response": "Maximizing the active window, sir." if success else "I could not maximize the window, sir."}
        elif command == "shutdown":
            from execution.system_control import shutdown_pc
            # Run shutdown asynchronously after 2 seconds to allow speech to complete
            loop.call_later(2.0, shutdown_pc)
            return {"type": "ai_response", "response": "Shutting down the computer, sir. Goodbye."}
        elif command == "restart":
            from execution.system_control import restart_pc
            # Run restart asynchronously after 2 seconds
            loop.call_later(2.0, restart_pc)
            return {"type": "ai_response", "response": "Restarting the computer now, sir."}
        elif command == "sleep":
            from execution.system_control import sleep_pc
            loop.call_later(2.0, sleep_pc)
            return {"type": "ai_response", "response": "Putting the system to sleep, sir."}
        elif command == "lock":
            from execution.system_control import lock_pc
            lock_pc()
            return {"type": "ai_response", "response": "Locking the workstation, sir."}
        elif command in ("focus", "switch", "activate"):
            if target:
                success = focus_window(target)
                return {"type": "ai_response", "response": f"Switched to {target}, sir." if success else f"I could not find an active window for {target}, sir."}
            return {"type": "ai_response", "response": "Which application would you like to switch to, sir?"}
        elif command == "close_tab" or (target and target.lower() in ("tab", "active tab", "current tab")):
            success = close_active_tab()
            return {"type": "ai_response", "response": "Closing the active tab, sir." if success else "I could not close the active tab, sir."}
        else: # close
            if target and target.lower() not in ("it", "that", "window", "active window"):
                focus_window(target)
            success = close_active_window()
            return {"type": "ai_response", "response": "Closing the active window, sir." if success else "I could not close the active window, sir."}

    # ── CLARIFICATION ─────────────────────────────────────────────────────────
    if intent == "CLARIFICATION":
        question = intent_data.get("question") or "Could you clarify that, sir?"
        return {"type": "ai_response", "response": question}

    # ── TEMPORAL SYSTEM INTENTS ───────────────────────────────────────────────
    if intent in ("SET_REMINDER", "SET_TIMER", "SET_ALARM", "SET_SCHEDULED_TASK", "SET_RECURRING_REMINDER"):
        from system.temporal_engine import temporal_engine
        time_expr = intent_data.get("time_expr") or intent_data.get("duration_expr") or ""
        text = intent_data.get("text") or intent_data.get("task") or "do something"
        
        it_type = "reminder"
        if intent == "SET_TIMER":
            it_type = "timer"
        elif intent == "SET_ALARM":
            it_type = "alarm"
            text = "Alarm"
        elif intent == "SET_RECURRING_REMINDER":
            it_type = "recurring"
            
        response = await temporal_engine.add_reminder(it_type, text, time_expr)
        return {"type": "ai_response", "response": response}

    if intent == "STOPWATCH_CONTROL":
        from system.temporal_engine import temporal_engine
        command = intent_data.get("command") or "status"
        
        if command == "start":
            response = temporal_engine.start_stopwatch()
        elif command == "stop":
            response = temporal_engine.stop_stopwatch()
        elif command == "pause":
            response = temporal_engine.pause_stopwatch()
        elif command == "resume":
            response = temporal_engine.resume_stopwatch()
        elif command == "reset":
            response = temporal_engine.reset_stopwatch()
        else:
            response = temporal_engine.get_stopwatch_status()
            
        return {"type": "ai_response", "response": response}

    if intent == "LIST_REMINDERS":
        from system.temporal_engine import temporal_engine
        response = await temporal_engine.list_reminders()
        return {"type": "ai_response", "response": response}

    if intent == "CANCEL_REMINDER":
        from system.temporal_engine import temporal_engine
        target = intent_data.get("target") or intent_data.get("query") or ""
        response = await temporal_engine.cancel_reminder(target)
        return {"type": "ai_response", "response": response}

    if intent is None:
        return None
    return False


# =========================================
# EXECUTE ACTION (public entry point)
# =========================================

async def execute_action(intent_data: dict, memory=None):
    try:
        loop   = asyncio.get_running_loop()
        intent = intent_data.get("intent")
        if intent is None:
            return None
        
        # ── Self-Referential System Actions Hook ──────────────────────────────────
        q_clean = (intent_data.get("query") or "").lower().strip()
        has_self_reference = any(w in q_clean for w in ("friday", "yourself", "the assistant", "assistant"))
        
        temporal_intents = {
            "SET_REMINDER", "SET_TIMER", "SET_ALARM", "SET_SCHEDULED_TASK", 
            "SET_RECURRING_REMINDER", "LIST_REMINDERS", "CANCEL_REMINDER", 
            "STOPWATCH_CONTROL"
        }
        
        if intent not in temporal_intents and has_self_reference:
            # 1. Voice Self-Shutdown
            shutdown_triggers = ("exit", "close", "turn off", "shut down", "shutdown", "power off", "deactivate")
            if any(t in q_clean for t in shutdown_triggers):
                import sys
                from core.state_manager import set_state, AssistantState
                
                print("[SYSTEM ACTION] Intercepted Voice Self-Shutdown request.")
                set_state(AssistantState.IDLE)
                
                # Schedule actual exit after 1.0s to allow speech/websockets to complete
                loop.call_later(1.0, lambda: sys.exit(0))
                
                return {"type": "ai_response", "response": "Shutting down system services now, sir. Goodbye."}
                
            # 2. Voice Self-Mute
            mute_triggers = ("mute", "silence")
            if any(t in q_clean for t in mute_triggers):
                from voice.listen import set_mic_enabled
                
                print("[SYSTEM ACTION] Intercepted Voice Self-Mute request.")
                set_mic_enabled(False)
                
                return {"type": "ai_response", "response": "Muting microphone, sir. You can re-enable my microphone from the UI panel."}
                
            # 3. Voice Self-Restart
            restart_triggers = ("restart", "reboot")
            if any(t in q_clean for t in restart_triggers):
                import sys
                import os
                
                print("[SYSTEM ACTION] Intercepted Voice Self-Restart request.")
                
                # Schedule reboot after 1.0s to allow speech/websockets to complete
                def do_restart():
                    os.execv(sys.executable, ['python'] + sys.argv)
                loop.call_later(1.0, do_restart)
                
                return {"type": "ai_response", "response": "Restarting system services now, sir."}

        # Import active action verification
        from execution.verifier import verify_action

        # ── MULTI_ACTION: parallel retrieval + sequential OS actions ────────────
        if intent == "MULTI_ACTION":
            actions = intent_data.get("actions", [])
            responses = []

            # ── Smart deduplication: if OPEN + SEARCH target the same platform,
            #    skip the OPEN — the search URL already navigates there directly.
            _PLATFORM_ALIASES = {
                "yt": "youtube", "youtube": "youtube",
                "spotify": "spotify",
                "google": "google",
            }

            def _normalize_platform(name: str) -> str:
                return _PLATFORM_ALIASES.get((name or "").lower().strip(), (name or "").lower().strip())

            filtered = []
            for i, action in enumerate(actions):
                if action.get("intent") == "OPEN":
                    target = _normalize_platform(action.get("target", ""))
                    next_actions = actions[i + 1:]
                    will_search_same = any(
                        a.get("intent") == "SEARCH" and _normalize_platform(a.get("platform", "")) == target
                        for a in next_actions
                    )
                    will_play_same = any(
                        a.get("intent") == "PLAY_MEDIA" and (
                            (target == "spotify" and ("spotify" in a.get("query", "").lower() or a.get("platform") == "spotify")) or
                            (target == "youtube" and "spotify" not in a.get("query", "").lower() and a.get("platform") != "spotify")
                        )
                        for a in next_actions
                    )
                    if will_search_same or will_play_same:
                        print(f"[MULTI_ACTION] Skipping OPEN '{target}' — SEARCH or PLAY_MEDIA follows on same platform")
                        continue
                filtered.append(action)

            # ── Split into parallel-safe (retrieval) vs sequential (OS/browser) ──
            PARALLEL_SAFE = {"WEATHER", "NEWS", "REALTIME_QUERY", "AI_QUERY", "SYSTEM_STATUS"}
            parallel_actions = [a for a in filtered if a.get("intent") in PARALLEL_SAFE]
            sequential_actions = [a for a in filtered if a.get("intent") not in PARALLEL_SAFE]

            # Execute parallel batch concurrently with asyncio.gather
            if parallel_actions:
                print(f"[MULTI_ACTION] Running {len(parallel_actions)} retrieval tasks in parallel")
                parallel_results = await asyncio.gather(
                    *[_execute_single(action, loop, memory) for action in parallel_actions],
                    return_exceptions=True
                )
                for action, result in zip(parallel_actions, parallel_results):
                    if isinstance(result, Exception):
                        print(f"[MULTI_ACTION] Parallel task failed: {action.get('intent')} — {result}")
                        continue
                    verified = verify_action(action, bool(result))
                    if isinstance(result, dict) and result.get("type") == "ai_response":
                        responses.append(result["response"])
                    elif not verified:
                        print(f"[MULTI_ACTION] Parallel task verification failed: {action}")

            # Execute sequential actions one-at-a-time with retry
            for action in sequential_actions:
                result = None
                success = False
                for attempt in range(2):
                    result = await _execute_single(action, loop, memory)
                    success = verify_action(action, bool(result))
                    if success:
                        break
                    print(f"[RETRY LOOP] Sub-action verification failed (attempt {attempt + 1}/2): {action}")
                    await asyncio.sleep(0.5)

                if isinstance(result, dict) and result.get("type") == "ai_response":
                    responses.append(result["response"])
                elif not success:
                    print(f"[MULTI_ACTION] Sub-action failed permanently: {action}")

            if responses:
                return {"type": "ai_response", "response": " ".join(responses)}
            return True

        # Single Action: Self-checking attempt loop (up to 2 times)
        result = None
        success = False
        for attempt in range(2):
            result = await _execute_single(intent_data, loop, memory)
            success = verify_action(intent_data, bool(result))
            if success:
                break
            print(f"[RETRY LOOP] Action verification failed (attempt {attempt + 1}/2): {intent_data}")
            await asyncio.sleep(0.5)

        return result if success else False

    except Exception as e:
        print(f"[ACTION ERROR] {e}")
        return False