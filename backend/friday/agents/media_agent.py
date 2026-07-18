import asyncio
import re
import urllib.parse
from loguru import logger
from friday.core.events import AgentType, TaskDispatch, TaskResult, TaskStatus
from friday.agents.base_agent import BaseAgent
from friday.security.permission_engine import permission_engine
from system.chrome_opener import open_url_in_chrome
from browser.browser_agent import youtube_search

# ── Monolith import REMOVED: execute_youtube_capability no longer imported ──


def _extract_media_entities(query: str, platform: str = "youtube") -> dict:
    """Extract media entities (creator, title, modifier, topic, platform) from a query string."""
    q = query.strip()
    q_lower = q.lower()
    if "spotify" in q_lower:
        platform = "spotify"
    elif "youtube" in q_lower or "yt" in q_lower:
        platform = "youtube"
    clean_q = q
    for w in ("play", "watch", "open", "on spotify", "on youtube", "on yt", "using spotify", "using youtube"):
        clean_q = re.sub(rf"\b{w}\b", "", clean_q, flags=re.IGNORECASE)
    clean_q = re.sub(r"\s+", " ", clean_q).strip()
    creator = None
    title = None
    modifier = None
    topic = None
    for mod in ("latest", "newest", "recent", "popular", "random", "first"):
        if re.search(rf"\b{mod}\b", q_lower):
            modifier = mod
            break
    by_match = re.search(r"(.+)\b(by|from)\b(.+)", clean_q, re.IGNORECASE)
    possessive_match = re.search(r"(.+?)'s\s+(.+)", clean_q, re.IGNORECASE)
    if by_match:
        title = by_match.group(1).strip()
        creator = by_match.group(3).strip()
    elif possessive_match:
        creator = possessive_match.group(1).strip()
        title = possessive_match.group(2).strip()
    else:
        creator_match = re.search(r"(?:latest video|latest upload|newest video|video)\s+(?:of|by|from)?\s+(.+)", clean_q, re.IGNORECASE)
        if creator_match:
            creator = creator_match.group(1).strip()
        else:
            title = clean_q
    for item in ("video", "song", "latest", "newest", "upload", "recent", "popular", "some", "a", "an"):
        if creator:
            creator = re.sub(rf"\b{item}\b", "", creator, flags=re.IGNORECASE).strip()
        if title:
            title = re.sub(rf"\b{item}\b", "", title, flags=re.IGNORECASE).strip()
    creator = creator if creator else None
    title = title if title else None
    if title and title.lower() in ("asmr", "lofi", "lo-fi", "study music", "relaxing music", "quantum physics", "science"):
        topic = title
        title = None
    return {"creator": creator, "title": title, "modifier": modifier, "topic": topic, "platform": platform}


def _resolve_creator_channel(creator: str) -> str | None:
    """Resolve YouTube channel handle from creator name, validating against the creator's display name."""
    import requests
    import json
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/115.0.0.0 Safari/537.36"}
    creator_lower = creator.lower()
    try:
        search_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(creator)}&sp=EgIQAg%3D%3D"
        r = requests.get(search_url, headers=headers, timeout=10)
        if r.status_code == 200:
            yt_data_match = re.search(r'var ytInitialData\s*=\s*(\{.+?\});', r.text, re.DOTALL)
            if yt_data_match:
                try:
                    yt_data = json.loads(yt_data_match.group(1))
                    sections = (yt_data.get("contents", {}).get("twoColumnSearchResultsRenderer", {})
                                .get("primaryContents", {}).get("sectionListRenderer", {}).get("contents", []))
                    for section in sections:
                        items = section.get("itemSectionRenderer", {}).get("contents", [])
                        for item in items:
                            cr = item.get("channelRenderer", {})
                            if cr:
                                # Validate display name contains creator token before accepting
                                display_name = ""
                                title_obj = cr.get("title", {})
                                if isinstance(title_obj, dict):
                                    runs = title_obj.get("runs", [])
                                    display_name = "".join(run.get("text", "") for run in runs).lower()
                                elif isinstance(title_obj, str):
                                    display_name = title_obj.lower()
                                creator_tokens = creator_lower.split()
                                name_matches = any(tok in display_name for tok in creator_tokens if len(tok) > 2)
                                handle = cr.get("navigationEndpoint", {}).get("browseEndpoint", {}).get("canonicalBaseUrl", "")
                                if handle and handle.startswith("/@") and name_matches:
                                    return handle[1:]
                except Exception:
                    pass
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
        logger.error(f"[MediaAgent] _resolve_creator_channel failed: {e}")
    return None


def _resolve_youtube_media_url(creator, title, modifier, topic, raw_query) -> str | None:
    """Entity-driven YouTube URL resolver."""
    import requests
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/115.0.0.0 Safari/537.36"}
    channel_path = None
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
                        unique = [v for v in video_ids if not (v in seen or seen.add(v))]
                        return f"https://www.youtube.com/watch?v={unique[0]}"
            except Exception as e:
                logger.warning(f"[MediaAgent] Direct channel latest fetch failed: {e}")
    clean_search = raw_query
    if creator:
        clean_search = f"{creator} latest video" if modifier == "latest" else (f"{creator} {title}" if title else creator)
    elif title:
        clean_search = title
    elif topic:
        clean_search = topic
    try:
        search_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(clean_search)}"
        if modifier == "latest":
            search_url += "&sp=CAI%3D"
        r = requests.get(search_url, headers=headers, timeout=10)
        if r.status_code == 200:
            import json
            video_ids = []
            yt_data_match = re.search(r'var ytInitialData\s*=\s*(\{.+?\});', r.text, re.DOTALL)
            if yt_data_match:
                try:
                    yt_data = json.loads(yt_data_match.group(1))
                    sections = (yt_data.get("contents", {}).get("twoColumnSearchResultsRenderer", {})
                                .get("primaryContents", {}).get("sectionListRenderer", {}).get("contents", []))
                    for section in sections:
                        items = section.get("itemSectionRenderer", {}).get("contents", [])
                        for item in items:
                            vid_id = item.get("videoRenderer", {}).get("videoId")
                            if vid_id:
                                video_ids.append(vid_id)
                except Exception:
                    pass
            if not video_ids:
                raw_ids = re.findall(r'/watch\?v=([a-zA-Z0-9_-]{11})', r.text)
                seen = set()
                video_ids = [x for x in raw_ids if not (x in seen or seen.add(x))]
            if video_ids:
                return f"https://www.youtube.com/watch?v={video_ids[0]}"
    except Exception as e:
        logger.warning(f"[MediaAgent] YouTube search fallback failed: {e}")
    return None


def _resolve_youtube_short_url(creator, raw_query) -> str | None:
    """Find the latest Shorts upload for a creator."""
    import requests
    if not creator:
        entities = _extract_media_entities(raw_query)
        creator = entities.get("creator")
    if not creator:
        return None
    channel_path = _resolve_creator_channel(creator)
    if channel_path:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/115.0.0.0 Safari/537.36"}
        try:
            shorts_url = f"https://www.youtube.com/{channel_path}/shorts"
            r = requests.get(shorts_url, headers=headers, timeout=10)
            if r.status_code == 200:
                shorts_ids = re.findall(r'/shorts/([a-zA-Z0-9_-]{11})', r.text)
                if shorts_ids:
                    seen = set()
                    unique = [s for s in shorts_ids if not (s in seen or seen.add(s))]
                    return f"https://www.youtube.com/shorts/{unique[0]}"
        except Exception as e:
            logger.warning(f"[MediaAgent] Shorts resolve failed: {e}")
    return None


def _resolve_youtube_channel_url(creator) -> str:
    channel_path = _resolve_creator_channel(creator)
    if channel_path:
        return f"https://www.youtube.com/{channel_path}"
    return f"https://www.youtube.com/results?search_query={urllib.parse.quote(creator)}&sp=EgIQAg%3D%3D"


def _resolve_youtube_search_result_by_index(query, index) -> str | None:
    import requests
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/115.0.0.0 Safari/537.36"}
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
                unique = [x for x in video_ids if not (x in seen or seen.add(x))]
                if index < len(unique):
                    return f"https://www.youtube.com/watch?v={unique[index]}"
    except Exception as e:
        logger.warning(f"[MediaAgent] search_by_index failed: {e}")
    return None


async def _execute_youtube_capability(intent: str, parameters: dict, loop) -> dict:
    """
    Unified capability-based YouTube execution path — fully internalized.
    Replaces the monolith's execute_youtube_capability().
    """
    creator = parameters.get("creator")
    title = parameters.get("title")
    modifier = parameters.get("modifier")
    topic = parameters.get("topic")
    query = parameters.get("query", "")

    # Re-classify PLAY_MEDIA / SEARCH into strict capabilities
    if intent in ("PLAY_MEDIA", "SEARCH"):
        has_search_verb = any(re.search(rf"\b{w}\b", query.lower()) for w in ("search", "find", "look up", "results", "videos about", "videos covering"))
        has_play_verb = any(re.search(rf"\b{w}\b", query.lower()) for w in ("play", "watch", "listen to", "put on", "latest video", "newest video"))
        if has_search_verb and not has_play_verb:
            intent = "YOUTUBE_TOPIC_SEARCH"
        else:
            entities = _extract_media_entities(query)
            creator = creator or entities.get("creator")
            title = title or entities.get("title")
            modifier = modifier or entities.get("modifier")
            topic = topic or entities.get("topic")
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

    if intent == "YOUTUBE_TOPIC_SEARCH":
        verbs = ["open youtube results for", "search youtube for", "videos covering", "search youtube",
                 "videos about", "youtube for", "on youtube", "videos of", "videos on", "video about",
                 "video of", "video on", "open youtube and", "open youtube", "open yt and", "open yt",
                 "show me", "look up", "videos", "search", "video", "find", "show", "youtube", "yt"]
        clean_search = query
        for verb in sorted(verbs, key=len, reverse=True):
            clean_search = re.sub(rf"\b{verb}\b", "", clean_search, flags=re.IGNORECASE)
        clean_search = re.sub(r"\s+", " ", clean_search).strip()
        youtube_search(clean_search)
        return {"type": "ai_response", "response": f"Opening search results for '{clean_search}' on YouTube, sir."}

    elif intent == "LATEST_CREATOR_VIDEO":
        video_url = await loop.run_in_executor(None, _resolve_youtube_media_url, creator, None, "latest", None, query)
        if video_url:
            sep = "&" if "?" in video_url else "?"
            try:
                open_url_in_chrome(f"{video_url}{sep}autoplay=1")
                return {"type": "ai_response", "response": f"Playing the latest video by {creator} on YouTube, sir."}
            except Exception as e_open:
                logger.error(f"[MediaAgent] open_url_in_chrome failed for latest video: {e_open}")
                return {"type": "ai_response", "response": f"I found the video but could not open Chrome, sir."}
        youtube_search(f"{creator} latest video")
        return {"type": "ai_response", "response": f"Opening search results for the latest video by {creator} on YouTube, sir."}

    elif intent == "LATEST_CREATOR_SHORT":
        video_url = await loop.run_in_executor(None, _resolve_youtube_short_url, creator, query)
        if video_url:
            sep = "&" if "?" in video_url else "?"
            try:
                open_url_in_chrome(f"{video_url}{sep}autoplay=1")
                return {"type": "ai_response", "response": f"Playing the latest short by {creator} on YouTube, sir."}
            except Exception as e_open:
                logger.error(f"[MediaAgent] open_url_in_chrome failed for latest short: {e_open}")
                return {"type": "ai_response", "response": f"I found the short but could not open Chrome, sir."}
        youtube_search(f"{creator} shorts")
        return {"type": "ai_response", "response": f"Opening search results for shorts by {creator} on YouTube, sir."}

    elif intent == "VIDEO_BY_TITLE":
        video_url = await loop.run_in_executor(None, _resolve_youtube_media_url, creator, title or query, None, None, query)
        if video_url:
            sep = "&" if "?" in video_url else "?"
            try:
                open_url_in_chrome(f"{video_url}{sep}autoplay=1")
                return {"type": "ai_response", "response": f"Playing '{title or query}' on YouTube, sir."}
            except Exception as e_open:
                logger.error(f"[MediaAgent] open_url_in_chrome failed for video by title: {e_open}")
                return {"type": "ai_response", "response": f"I found the video but could not open Chrome, sir."}
        youtube_search(title or query)
        return {"type": "ai_response", "response": f"Opening search results for '{title or query}' on YouTube, sir."}

    elif intent == "CHANNEL_OPEN":
        channel_url = await loop.run_in_executor(None, _resolve_youtube_channel_url, creator or query)
        try:
            open_url_in_chrome(channel_url)
            return {"type": "ai_response", "response": f"Opening {creator or query}'s YouTube channel, sir."}
        except Exception as e_open:
            logger.error(f"[MediaAgent] open_url_in_chrome failed for channel open: {e_open}")
            return {"type": "ai_response", "response": f"I could not open the channel in Chrome, sir."}

    elif intent == "PLAY_SEARCH_RESULT":
        idx = 0
        if "second" in query.lower() or "2nd" in query.lower():
            idx = 1
        elif "third" in query.lower() or "3rd" in query.lower():
            idx = 2
        video_url = await loop.run_in_executor(None, _resolve_youtube_search_result_by_index, query, idx)
        if video_url:
            sep = "&" if "?" in video_url else "?"
            try:
                open_url_in_chrome(f"{video_url}{sep}autoplay=1")
                return {"type": "ai_response", "response": f"Playing search result number {idx + 1} on YouTube, sir."}
            except Exception as e_open:
                logger.error(f"[MediaAgent] open_url_in_chrome failed for search result: {e_open}")
                return {"type": "ai_response", "response": f"I found the video but could not open Chrome, sir."}
        youtube_search(query)
        return {"type": "ai_response", "response": f"Opening search results for '{query}' on YouTube, sir."}

    # Default fallback
    youtube_search(query)
    return {"type": "ai_response", "response": f"Opening search results for '{query}' on YouTube, sir."}


class MediaAgent(BaseAgent):
    def __init__(self):
        super().__init__(AgentType.MEDIA_AGENT)

    async def startup(self) -> None:
        logger.info("[MediaAgent] Startup complete.")

    async def shutdown(self) -> None:
        logger.info("[MediaAgent] Shutdown complete.")

    def get_capabilities(self) -> list[str]:
        return [
            "YOUTUBE_TOPIC_SEARCH", "LATEST_CREATOR_VIDEO", "LATEST_CREATOR_SHORT",
            "VIDEO_BY_TITLE", "CHANNEL_OPEN", "PLAY_SEARCH_RESULT",
            "PLAY_MEDIA", "SEARCH", "URL_OPEN", "SPOTIFY_CONTROL"
        ]

    def _ok(self, dispatch, payload):
        return TaskResult(
            task_id=dispatch.task_id, agent_id=self.agent_id,
            status=TaskStatus.SUCCESS, payload=payload,
            correlation_id=dispatch.correlation_id
        )

    def _fail(self, dispatch, error: str):
        return TaskResult(
            task_id=dispatch.task_id, agent_id=self.agent_id,
            status=TaskStatus.FAILED, payload={"error": error},
            correlation_id=dispatch.correlation_id
        )

    async def handle_task(self, dispatch: TaskDispatch) -> TaskResult:
        intent = dispatch.intent
        parameters = dispatch.parameters or {}

        if "query" not in parameters and "url" in parameters:
            parameters["query"] = parameters["url"]
        elif "query" not in parameters:
            parameters["query"] = ""

        allowed = await permission_engine.check_permission(
            agent_trust_level=self.trust_level,
            tool_name=intent,
            agent_id=self.agent_id,
            correlation_id=dispatch.correlation_id,
            session_id=dispatch.session_id
        )
        if not allowed:
            logger.warning(f"[MediaAgent] Permission denied for intent: {intent}")
            return self._fail(dispatch, "Permission denied")

        try:
            loop = asyncio.get_running_loop()

            # ── URL_OPEN ──────────────────────────────────────────────────────
            if intent == "URL_OPEN":
                url = (parameters.get("url") or parameters.get("query") or "").strip()
                logger.info(f"[MediaAgent] Opening URL: {url}")
                success = open_url_in_chrome(url)
                if success:
                    return self._ok(dispatch, {"success": True})
                return self._fail(dispatch, "Failed to launch Chrome with requested URL.")

            # ── SPOTIFY_CONTROL ────────────────────────────────────────────────
            elif intent == "SPOTIFY_CONTROL" or (
                intent == "PLAY_MEDIA" and (
                    "spotify" in parameters.get("query", "").lower() or
                    parameters.get("platform") == "spotify"
                )
            ):
                client_id = os.environ.get("SPOTIFY_CLIENT_ID")
                if not client_id or "your_spotify_client_id_here" in client_id:
                    return self._fail(
                        dispatch,
                        "Spotify Client ID is not configured. Please set a valid SPOTIFY_CLIENT_ID in your .env file."
                    )
                
                from friday.integrations.spotify_auth import load_tokens, generate_pkce_pair, build_authorize_url, run_loopback_server, exchange_code, store_tokens
                from friday.integrations.spotify_client import SpotifyClient
                
                tokens = load_tokens()
                if not tokens:
                    logger.info("[MediaAgent] Spotify credentials not found, starting PKCE auth flow...")
                    verifier, challenge = generate_pkce_pair()
                    auth_url = build_authorize_url(client_id, challenge)
                    
                    import webbrowser
                    # Open browser in executor
                    await loop.run_in_executor(None, webbrowser.open, auth_url)
                    
                    # Run loopback server in executor with 120s timeout
                    logger.info("[MediaAgent] Awaiting loopback authorization callback on port 54321...")
                    code = await loop.run_in_executor(None, run_loopback_server, 120)
                    if not code:
                        return self._fail(dispatch, "Spotify authentication timed out or was cancelled by user.")
                    
                    tokens = await exchange_code(code, verifier, client_id)
                    if not tokens:
                        return self._fail(dispatch, "Spotify token exchange failed.")
                    store_tokens(tokens)
                    logger.info("[MediaAgent] Spotify authenticated and tokens stored in keyring.")
                
                # We have tokens, execute command
                client = SpotifyClient()
                
                if intent == "SPOTIFY_CONTROL":
                    cmd = parameters.get("command", "play").lower()
                    if cmd == "play":
                        success = await client.play()
                        resp = "Playing Spotify, sir." if success else "I could not start Spotify playback, sir."
                    elif cmd == "pause":
                        success = await client.pause()
                        resp = "Pausing Spotify playback, sir." if success else "I could not pause Spotify playback, sir."
                    elif cmd in ("next", "skip"):
                        success = await client.next_track()
                        resp = "Skipping to the next track, sir." if success else "I could not skip the track, sir."
                    elif cmd in ("previous", "prev"):
                        success = await client.prev_track()
                        resp = "Playing the previous track, sir." if success else "I could not go back, sir."
                    elif cmd == "volume_up":
                        success = await client.set_volume(80)
                        resp = "Setting Spotify volume to eighty percent, sir." if success else "I could not change volume, sir."
                    elif cmd == "volume_down":
                        success = await client.set_volume(30)
                        resp = "Setting Spotify volume to thirty percent, sir." if success else "I could not change volume, sir."
                    elif cmd in ("status", "current"):
                        track = await client.get_current_track()
                        resp = f"Currently playing {track['title']} by {track['artist']}, sir." if track else "Nothing is currently playing on Spotify, sir."
                    else:
                        resp = f"Unsupported Spotify command: {cmd}"
                        return self._fail(dispatch, resp)
                    
                    return self._ok(dispatch, {"response": resp})
                
                else:
                    # PLAY_MEDIA
                    query = parameters.get("query", "").strip()
                    # Strip 'spotify' out of query if present to search clean
                    clean_query = re.sub(r'\bspotify\b', '', query, flags=re.IGNORECASE).strip()
                    
                    # Check if user wanted a playlist specifically
                    is_playlist = "playlist" in query.lower()
                    clean_query = re.sub(r'\bplaylist\b', '', clean_query, flags=re.IGNORECASE).strip()
                    
                    if is_playlist:
                        success = await client.play_playlist(clean_query)
                        resp = f"Playing playlist '{clean_query}' on Spotify, sir." if success else f"I could not find a playlist matching '{clean_query}', sir."
                    else:
                        tracks = await client.search(clean_query, search_type="track")
                        if tracks:
                            success = await client.play_uri(tracks[0]["uri"])
                            resp = f"Playing {tracks[0]['name']} by {tracks[0]['artist']} on Spotify, sir." if success else "I could not start playback, sir."
                        else:
                            resp = f"I could not find '{clean_query}' on Spotify, sir."
                            return self._fail(dispatch, resp)
                    return self._ok(dispatch, {"response": resp})

            # ── YouTube capabilities ───────────────────────────────────────────
            else:
                logger.info(f"[MediaAgent] Executing YouTube capability '{intent}'")
                result = await _execute_youtube_capability(intent, parameters, loop)
                if result is False:
                    return self._fail(dispatch, "YouTube capability returned failure")
                payload = result if isinstance(result, dict) else {"success": bool(result)}
                return self._ok(dispatch, payload)

        except Exception as e:
            logger.error(f"[MediaAgent] Error handling task {intent}: {e}", exc_info=True)
            return self._fail(dispatch, str(e))
