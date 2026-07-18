import httpx
import time
import os
from loguru import logger
from friday.integrations.spotify_auth import load_tokens, refresh_tokens

class SpotifyClient:
    def __init__(self):
        self.client_id = os.environ.get("SPOTIFY_CLIENT_ID")
        
    async def _get_auth_headers(self) -> dict:
        self.client_id = os.environ.get("SPOTIFY_CLIENT_ID")
        if not self.client_id:
            raise Exception("SPOTIFY_CLIENT_ID not set in environment.")
        tokens = load_tokens()
        if not tokens:
            raise Exception("Spotify not authenticated. Please configure Spotify integration first.")
        
        if time.time() + 10 > tokens.get("expires_at", 0):
            logger.info("[SpotifyClient] Access token expired, refreshing...")
            tokens = await refresh_tokens(tokens["refresh_token"], self.client_id)
            if not tokens:
                raise Exception("Failed to refresh Spotify access token.")
                
        return {"Authorization": f"Bearer {tokens['access_token']}"}
        
    async def _request(self, method: str, endpoint: str, json_data: dict = None, params: dict = None) -> httpx.Response:
        url = f"https://api.spotify.com/v1/{endpoint}"
        headers = await self._get_auth_headers()
        
        async with httpx.AsyncClient() as client:
            r = await client.request(method, url, headers=headers, json=json_data, params=params)
            if r.status_code == 401:
                logger.warning("[SpotifyClient] Got 401, forcing token refresh...")
                tokens = load_tokens()
                if tokens:
                    tokens = await refresh_tokens(tokens["refresh_token"], self.client_id)
                    if tokens:
                        headers = {"Authorization": f"Bearer {tokens['access_token']}"}
                        r = await client.request(method, url, headers=headers, json=json_data, params=params)
            return r

    async def play(self) -> bool:
        r = await self._request("PUT", "me/player/play")
        return r.status_code in (200, 204)

    async def pause(self) -> bool:
        r = await self._request("PUT", "me/player/pause")
        return r.status_code in (200, 204)

    async def next_track(self) -> bool:
        r = await self._request("POST", "me/player/next")
        return r.status_code in (200, 204)

    async def prev_track(self) -> bool:
        r = await self._request("POST", "me/player/previous")
        return r.status_code in (200, 204)

    async def set_volume(self, pct: int) -> bool:
        r = await self._request("PUT", "me/player/volume", params={"volume_percent": pct})
        return r.status_code in (200, 204)

    async def get_current_track(self) -> dict:
        r = await self._request("GET", "me/player/currently-playing")
        if r.status_code == 200:
            data = r.json()
            item = data.get("item", {})
            return {
                "title": item.get("name"),
                "artist": ", ".join([a.get("name") for a in item.get("artists", [])]) if item.get("artists") else "Unknown",
                "is_playing": data.get("is_playing", False)
            }
        return None

    async def search(self, query: str, search_type: str = "track") -> list:
        r = await self._request("GET", "search", params={"q": query, "type": search_type, "limit": 5})
        if r.status_code == 200:
            data = r.json()
            results = []
            if search_type == "track" and "tracks" in data:
                for item in data["tracks"].get("items", []):
                    results.append({
                        "name": item.get("name"),
                        "uri": item.get("uri"),
                        "artist": ", ".join([a.get("name") for a in item.get("artists", [])])
                    })
            elif search_type == "playlist" and "playlists" in data:
                for item in data["playlists"].get("items", []):
                    results.append({
                        "name": item.get("name"),
                        "uri": item.get("uri")
                    })
            return results
        return []

    async def play_uri(self, uri: str) -> bool:
        json_data = {}
        if "track" in uri:
            json_data["uris"] = [uri]
        else:
            json_data["context_uri"] = uri
        r = await self._request("PUT", "me/player/play", json_data=json_data)
        return r.status_code in (200, 204)

    async def play_playlist(self, name: str) -> bool:
        playlists = await self.search(name, search_type="playlist")
        if playlists:
            return await self.play_uri(playlists[0]["uri"])
        return False
