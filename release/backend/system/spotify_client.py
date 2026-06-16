"""
Premium Spotify Integration for FRIDAY.
Uses official Spotify OAuth 2.0 Authorization Code Flow with PKCE (Proof Key for Code Exchange).
Secures the desktop application by eliminating the need for client secrets in public configurations.
"""

from __future__ import annotations

import os
import json
import time
import secrets
import hashlib
import base64
import urllib.parse
import threading
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler

import requests
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"
if not ENV_PATH.exists() and (BASE_DIR.parent / ".env").exists():
    ENV_PATH = BASE_DIR.parent / ".env"

TOKEN_CACHE_PATH = BASE_DIR / "data" / "spotify_token.json"

# Ensure data directory exists
TOKEN_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)

# Load env
load_dotenv(dotenv_path=ENV_PATH, override=True)


def generate_code_verifier() -> str:
    """Generate high-entropy cryptographic code verifier (43 - 128 characters)."""
    allowed = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
    return "".join(secrets.choice(allowed) for _ in range(64))


def generate_code_challenge(verifier: str) -> str:
    """Calculate SHA-256 hash of the code verifier and base64url encode it."""
    sha256 = hashlib.sha256(verifier.encode("utf-8")).digest()
    # Base64url encoding (replaces +, / and removes padding)
    b64 = base64.urlencode_to_string(sha256) if hasattr(base64, "urlencode_to_string") else \
          base64.urlsafe_b64encode(sha256).decode("utf-8").rstrip("=")
    return b64


class SpotifyPKCECallbackHandler(BaseHTTPRequestHandler):
    """Callback server for capturing PKCE authorization code."""
    server: PKCEServer

    def do_GET(self):
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)
        code = params.get("code")

        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()

        if code:
            self.server.auth_code = code[0]
            html = """
            <html>
                <body style="font-family: system-ui, sans-serif; background-color: #121212; color: #ffffff; text-align: center; padding-top: 100px;">
                    <div style="max-width: 500px; margin: 0 auto; padding: 40px; border-radius: 12px; background-color: #181818; box-shadow: 0 4px 12px rgba(0,0,0,0.5);">
                        <h1 style="color: #1DB954; font-size: 2.2em; margin-bottom: 20px;">FRIDAY Connected</h1>
                        <p style="font-size: 1.2em; line-height: 1.6; color: #b3b3b3;">You have successfully authorized FRIDAY using Spotify PKCE flow, sir.</p>
                        <p style="color: #888888; font-size: 0.9em; margin-top: 30px;">This tab can be closed safely now.</p>
                    </div>
                </body>
            </html>
            """
            self.wfile.write(html.encode("utf-8"))
        else:
            html = """
            <html>
                <body style="font-family: system-ui, sans-serif; background-color: #121212; color: #ff5555; text-align: center; padding-top: 100px;">
                    <div style="max-width: 500px; margin: 0 auto; padding: 40px; border-radius: 12px; background-color: #181818; box-shadow: 0 4px 12px rgba(0,0,0,0.5);">
                        <h1 style="font-size: 2.2em; margin-bottom: 20px;">Connection Failed</h1>
                        <p>No PKCE code returned by Spotify authorization server.</p>
                    </div>
                </body>
            </html>
            """
            self.wfile.write(html.encode("utf-8"))

        if hasattr(self.server, "timeout_timer") and self.server.timeout_timer:
            self.server.timeout_timer.cancel()
        threading.Thread(target=self.server.shutdown).start()

    def log_message(self, format, *args):
        pass


class PKCEServer(HTTPServer):
    def __init__(self, server_address, RequestHandlerClass):
        super().__init__(server_address, RequestHandlerClass)
        self.auth_code = None


class SpotifyClient:
    def __init__(self):
        # Only client_id is required for PKCE authorization code flow! No Client Secret needed.
        self.client_id = os.getenv("SPOTIFY_CLIENT_ID")
        self.redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI", "http://localhost:8888/callback")
        self.scope = (
            "user-modify-playback-state "
            "user-read-playback-state "
            "user-read-currently-playing "
            "playlist-read-private "
            "playlist-read-collaborative "
            "user-library-read "
            "user-top-read"
        )
        self._token_info = None
        self._load_cached_token()

    @property
    def is_configured(self) -> bool:
        return bool(self.client_id)

    def _load_cached_token(self):
        if TOKEN_CACHE_PATH.exists():
            try:
                with open(TOKEN_CACHE_PATH, "r", encoding="utf-8") as f:
                    self._token_info = json.load(f)
            except Exception as e:
                print(f"[SPOTIFY PKCE] Failed loading cached token: {e}")
                self._token_info = None

    def _save_token(self, token_info: dict):
        self._token_info = token_info
        try:
            with open(TOKEN_CACHE_PATH, "w", encoding="utf-8") as f:
                json.dump(token_info, f, indent=2)
        except Exception as e:
            print(f"[SPOTIFY PKCE] Failed caching token: {e}")

    def refresh_token_if_needed(self) -> bool:
        if not self.is_configured or not self._token_info:
            return False

        now = int(time.time())
        # Refresh if token expires in less than 5 minutes
        if self._token_info.get("expires_at", 0) - now > 300:
            return True

        print("[SPOTIFY PKCE] Refreshing access token via PKCE...")
        refresh_token = self._token_info.get("refresh_token")
        if not refresh_token:
            return False

        try:
            # PKCE token refresh request does NOT require client_secret!
            payload = {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": self.client_id,
            }
            headers = {"Content-Type": "application/x-www-form-urlencoded"}
            r = requests.post("https://accounts.spotify.com/api/token", data=payload, headers=headers, timeout=10)
            if r.status_code == 200:
                res = r.json()
                token_info = {
                    "access_token": res["access_token"],
                    "refresh_token": res.get("refresh_token", refresh_token),
                    "expires_in": res["expires_in"],
                    "expires_at": int(time.time()) + res["expires_in"]
                }
                self._save_token(token_info)
                print("[SPOTIFY PKCE] Token refreshed successfully.")
                return True
            else:
                print(f"[SPOTIFY PKCE] Refresh failed: status {r.status_code}, {r.text}")
                return False
        except Exception as e:
            print(f"[SPOTIFY PKCE] Token refresh exception: {e}")
            return False

    def authenticate(self) -> bool:
        """Runs the official Spotify OAuth 2.0 PKCE flow."""
        if not self.is_configured:
            print("[SPOTIFY PKCE] Missing SPOTIFY_CLIENT_ID in env.")
            return False

        if self._token_info and self.refresh_token_if_needed():
            return True

        print("[SPOTIFY PKCE] Initiating PKCE Auth flow...")
        # 1. Generate code verifier and challenge
        verifier = generate_code_verifier()
        challenge = generate_code_challenge(verifier)

        # 2. Spin up redirect server on redirect_uri's port
        parsed_url = urllib.parse.urlparse(self.redirect_uri)
        port = parsed_url.port or 8888
        
        try:
            server = PKCEServer(("localhost", port), SpotifyPKCECallbackHandler)
        except OSError as e:
            print(f"[SPOTIFY PKCE] Port {port} already in use: {e}")
            return False

        # 3. Form authorization URL
        auth_params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "code_challenge_method": "S256",
            "code_challenge": challenge,
            "scope": self.scope,
            "state": "friday_pkce"
        }
        auth_url = f"https://accounts.spotify.com/authorize?{urllib.parse.urlencode(auth_params)}"

        # 4. Open in Chrome
        from system.chrome_opener import open_url_in_chrome
        print(f"[SPOTIFY PKCE] Opening PKCE auth link in browser...")
        open_url_in_chrome(auth_url)

        timeout_timer = None
        try:
            # Set up the watchdog timer to shut down the server after 120s if inactive
            def force_shutdown():
                if server and server.auth_code is None:
                    print("[SPOTIFY PKCE] Authorization timed out (120s limit). Shutting down callback server...")
                    server.shutdown()

            timeout_timer = threading.Timer(120.0, force_shutdown)
            server.timeout_timer = timeout_timer
            timeout_timer.start()

            # 5. Wait for callback code
            server.serve_forever()
            code = server.auth_code
        finally:
            if timeout_timer:
                timeout_timer.cancel()
            server.server_close()
            print("[SPOTIFY PKCE] Callback server closed and port unbound.")

        if not code:
            print("[SPOTIFY PKCE] Authentication failed or timed out.")
            return False

        # 6. Exchange code for tokens (includes client_id and code_verifier, but no client_secret!)
        try:
            payload = {
                "client_id": self.client_id,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.redirect_uri,
                "code_verifier": verifier,
            }
            headers = {"Content-Type": "application/x-www-form-urlencoded"}
            r = requests.post("https://accounts.spotify.com/api/token", data=payload, headers=headers, timeout=10)
            if r.status_code == 200:
                res = r.json()
                token_info = {
                    "access_token": res["access_token"],
                    "refresh_token": res["refresh_token"],
                    "expires_in": res["expires_in"],
                    "expires_at": int(time.time()) + res["expires_in"]
                }
                self._save_token(token_info)
                print("[SPOTIFY PKCE] PKCE Auth exchange successful. Session secured.")
                return True
            else:
                print(f"[SPOTIFY PKCE] Code exchange failed: status {r.status_code}, {r.text}")
                return False
        except Exception as e:
            print(f"[SPOTIFY PKCE] Exchange exception: {e}")
            return False

    def _get_headers(self) -> dict | None:
        if not self.refresh_token_if_needed():
            return None
        return {
            "Authorization": f"Bearer {self._token_info['access_token']}",
            "Content-Type": "application/json"
        }

    # =========================================================================
    # OFFICIAL WEB API WRAPPERS
    # =========================================================================

    def get_devices(self) -> list[dict]:
        headers = self._get_headers()
        if not headers:
            return []
        try:
            r = requests.get("https://api.spotify.com/v1/me/player/devices", headers=headers, timeout=5)
            if r.status_code == 200:
                return r.json().get("devices", [])
        except Exception as e:
            print(f"[SPOTIFY] Failed fetching devices: {e}")
        return []

    def get_currently_playing(self) -> dict | None:
        headers = self._get_headers()
        if not headers:
            return None
        try:
            r = requests.get("https://api.spotify.com/v1/me/player/currently-playing", headers=headers, timeout=5)
            if r.status_code == 200 and r.text.strip():
                return r.json()
        except Exception as e:
            print(f"[SPOTIFY] Failed fetching currently playing track: {e}")
        return None

    def play(self, context_uri: str | None = None, uris: list[str] | None = None, device_id: str | None = None) -> bool:
        headers = self._get_headers()
        if not headers:
            return False

        # Ensure there is an active device. If not, try to find one and target it
        if not device_id:
            devices = self.get_devices()
            active_device = next((d for d in devices if d.get("is_active")), None)
            if not active_device and devices:
                # Target the first available device
                device_id = devices[0]["id"]
                print(f"[SPOTIFY] Transferring playback targeting device: {devices[0]['name']}")

        payload = {}
        if context_uri:
            payload["context_uri"] = context_uri
        elif uris:
            payload["uris"] = uris

        params = {}
        if device_id:
            params["device_id"] = device_id

        try:
            url = "https://api.spotify.com/v1/me/player/play"
            r = requests.put(url, headers=headers, params=params, json=payload, timeout=5)
            if r.status_code in (200, 204):
                return True
            else:
                print(f"[SPOTIFY] Play API failed: {r.status_code}, {r.text}")
        except Exception as e:
            print(f"[SPOTIFY] Play API exception: {e}")
        return False

    def pause(self) -> bool:
        headers = self._get_headers()
        if not headers:
            return False
        try:
            r = requests.put("https://api.spotify.com/v1/me/player/pause", headers=headers, timeout=5)
            return r.status_code in (200, 204)
        except Exception as e:
            print(f"[SPOTIFY] Pause failed: {e}")
        return False

    def next(self) -> bool:
        headers = self._get_headers()
        if not headers:
            return False
        try:
            r = requests.post("https://api.spotify.com/v1/me/player/next", headers=headers, timeout=5)
            return r.status_code in (200, 204)
        except Exception as e:
            print(f"[SPOTIFY] Next failed: {e}")
        return False

    def previous(self) -> bool:
        headers = self._get_headers()
        if not headers:
            return False
        try:
            r = requests.post("https://api.spotify.com/v1/me/player/previous", headers=headers, timeout=5)
            return r.status_code in (200, 204)
        except Exception as e:
            print(f"[SPOTIFY] Previous failed: {e}")
        return False

    def set_volume(self, percent: int) -> bool:
        headers = self._get_headers()
        if not headers:
            return False
        try:
            r = requests.put(f"https://api.spotify.com/v1/me/player/volume?volume_percent={percent}", headers=headers, timeout=5)
            return r.status_code in (200, 204)
        except Exception as e:
            print(f"[SPOTIFY] Volume failed: {e}")
        return False

    def search(self, query: str, limit: int = 1) -> dict | None:
        headers = self._get_headers()
        if not headers:
            return None
        try:
            q = urllib.parse.quote(query)
            url = f"https://api.spotify.com/v1/search?q={q}&type=track,playlist,artist&limit={limit}"
            r = requests.get(url, headers=headers, timeout=5)
            if r.status_code == 200:
                return r.json()
        except Exception as e:
            print(f"[SPOTIFY] Search exception: {e}")
        return None

    def get_user_playlists(self) -> list[dict]:
        headers = self._get_headers()
        if not headers:
            return []
        try:
            r = requests.get("https://api.spotify.com/v1/me/playlists?limit=20", headers=headers, timeout=5)
            if r.status_code == 200:
                return r.json().get("items", [])
        except Exception as e:
            print(f"[SPOTIFY] Fetch playlists failed: {e}")
        return []

    def get_top_tracks(self) -> list[dict]:
        """Fetch user's top tracks for contextual music intelligence (e.g. 'play something')."""
        headers = self._get_headers()
        if not headers:
            return []
        try:
            r = requests.get("https://api.spotify.com/v1/me/top/tracks?limit=15&time_range=short_term", headers=headers, timeout=5)
            if r.status_code == 200:
                return r.json().get("items", [])
        except Exception as e:
            print(f"[SPOTIFY] Fetch top tracks failed: {e}")
        return []

    def add_to_queue(self, uri: str) -> bool:
        headers = self._get_headers()
        if not headers:
            return False
        try:
            q_uri = urllib.parse.quote(uri)
            r = requests.post(f"https://api.spotify.com/v1/me/player/queue?uri={q_uri}", headers=headers, timeout=5)
            return r.status_code in (200, 204)
        except Exception as e:
            print(f"[SPOTIFY] Add to queue failed: {e}")
        return False
