import secrets
import hashlib
import base64
import http.server
import threading
import urllib.parse
import json
import time
import httpx
import keyring
from loguru import logger

REDIRECT_URI = "http://127.0.0.1:54321/callback"
SCOPES = "user-read-playback-state user-modify-playback-state user-read-currently-playing playlist-read-private"

def generate_pkce_pair():
    token = secrets.token_urlsafe(64)
    code_verifier = token[:128]
    sha = hashlib.sha256(code_verifier.encode('utf-8')).digest()
    code_challenge = base64.urlsafe_b64encode(sha).decode('utf-8').rstrip('=')
    return code_verifier, code_challenge

def build_authorize_url(client_id: str, challenge: str) -> str:
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "code_challenge_method": "S256",
        "code_challenge": challenge,
        "scope": SCOPES
    }
    return "https://accounts.spotify.com/authorize?" + urllib.parse.urlencode(params)

class CallbackHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass
    def do_GET(self):
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)
        if "code" in params:
            self.server.auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body><h1>Spotify Login Successful!</h1><p>You can close this tab now and return to FRIDAY.</p></body></html>")
        else:
            self.send_response(400)
            self.end_headers()

def run_loopback_server(timeout=120) -> str:
    server = http.server.HTTPServer(("127.0.0.1", 54321), CallbackHandler)
    server.auth_code = None
    
    def serve():
        server.handle_request()
        
    t = threading.Thread(target=serve, daemon=True)
    t.start()
    t.join(timeout)
    server.server_close()
    return server.auth_code

async def exchange_code(code: str, verifier: str, client_id: str) -> dict:
    url = "https://accounts.spotify.com/api/token"
    data = {
        "client_id": client_id,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "code_verifier": verifier
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    async with httpx.AsyncClient() as client:
        r = await client.post(url, data=data, headers=headers)
        if r.status_code == 200:
            res = r.json()
            expires_at = time.time() + res.get("expires_in", 3600)
            tokens = {
                "access_token": res.get("access_token"),
                "refresh_token": res.get("refresh_token"),
                "expires_at": expires_at
            }
            return tokens
        else:
            logger.error(f"[SpotifyAuth] Token exchange failed: {r.status_code} {r.text}")
            return None

def store_tokens(tokens: dict) -> None:
    try:
        keyring.set_password("FRIDAY", "spotify_tokens", json.dumps(tokens))
    except Exception as e:
        logger.error(f"[SpotifyAuth] Failed to store tokens in keyring: {e}")

def load_tokens() -> dict:
    try:
        val = keyring.get_password("FRIDAY", "spotify_tokens")
        if val:
            return json.loads(val)
    except Exception as e:
        logger.error(f"[SpotifyAuth] Failed to load tokens from keyring: {e}")
    return None

async def refresh_tokens(refresh_token: str, client_id: str) -> dict:
    url = "https://accounts.spotify.com/api/token"
    data = {
        "client_id": client_id,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    async with httpx.AsyncClient() as client:
        r = await client.post(url, data=data, headers=headers)
        if r.status_code == 200:
            res = r.json()
            expires_at = time.time() + res.get("expires_in", 3600)
            new_tokens = {
                "access_token": res.get("access_token"),
                "refresh_token": res.get("refresh_token") or refresh_token,
                "expires_at": expires_at
            }
            store_tokens(new_tokens)
            return new_tokens
        else:
            logger.error(f"[SpotifyAuth] Token refresh failed: {r.status_code} {r.text}")
            return None
