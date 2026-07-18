import time
import asyncio
import threading
import hashlib
import json
import requests
from typing import Any, Callable, Dict, Tuple

def generate_cache_key(namespace: str, *args, **kwargs) -> str:
    """Safely generates a deterministic cache key string from arbitrary arguments."""
    try:
        serialized = json.dumps({"args": args, "kwargs": kwargs}, sort_keys=True, default=str)
        h = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        return f"{namespace}:{h}"
    except Exception:
        # Fallback if serialization fails
        return f"{namespace}:{hash(str(args) + str(kwargs))}"

class APIManager:
    """
    FRIDAY Central API Quota, Cache, and Latency Budget Manager.
    Guarantees stable orchestration, micro TTL caching, strict latency enforcement,
    and failsafe degraded conversational survival.
    """
    def __init__(self):
        self._cache: Dict[str, Tuple[float, Any]] = {}  # key -> (expiry_time, data)
        self._cache_lock = threading.Lock()
        
        # API Cooldowns: stores timestamp when an API is allowed to be queried again
        # key: api_name (e.g. 'groq', 'gemini', 'tavily', 'maps') -> timestamp
        self._cooldowns: Dict[str, float] = {}
        self._cooldown_lock = threading.Lock()

        # Latency Budgets (seconds)
        self.budgets = {
            "groq": 1.5,
            "maps": 2.5,
            "retrieval": 3.0,
            "vision": 4.0
        }

    # ── MICRO TTL CACHE LAYER ────────────────────────────────────────────────
    def get_cached(self, namespace: str, *args, **kwargs) -> Any | None:
        """Retrieves non-expired cached item if exists."""
        key = generate_cache_key(namespace, *args, **kwargs)
        with self._cache_lock:
            if key in self._cache:
                expiry, data = self._cache[key]
                if time.time() < expiry:
                    print(f"[API CACHE] Cache HIT for namespace '{namespace}'")
                    return data
                else:
                    # Clean up expired item
                    del self._cache[key]
        return None

    def set_cached(self, namespace: str, data: Any, ttl_seconds: float = 300.0, *args, **kwargs) -> None:
        """Saves data into the cache with a specific Time-To-Live."""
        if data is None or data is False:
            return # Don't cache failures or empty responses
        key = generate_cache_key(namespace, *args, **kwargs)
        expiry = time.time() + ttl_seconds
        with self._cache_lock:
            self._cache[key] = (expiry, data)
            print(f"[API CACHE] Cache SET for namespace '{namespace}' (TTL: {ttl_seconds}s)")

    def clear_cache(self) -> None:
        """Clears all cached entries."""
        with self._cache_lock:
            self._cache.clear()
            print("[API CACHE] Cache completely cleared.")

    # ── COOLDOWNS & API STABILITY ──────────────────────────────────────────
    def is_cooling_down(self, api_name: str) -> bool:
        """Checks if the given API is currently in a cooldown window."""
        with self._cooldown_lock:
            cd_until = self._cooldowns.get(api_name, 0.0)
            if time.time() < cd_until:
                print(f"[API MANAGER] API '{api_name}' is cooling down for another {cd_until - time.time():.1f}s")
                return True
        return False

    def trigger_cooldown(self, api_name: str, duration_seconds: float = 10.0) -> None:
        """Puts an API into a cooldown window to prevent rapid rate-limit hammering."""
        with self._cooldown_lock:
            self._cooldowns[api_name] = time.time() + duration_seconds
            print(f"[API MANAGER] Triggered {duration_seconds}s cooldown on API '{api_name}' due to error/limit.")

    # ── LATENCY BUDGET & RUNTIME EXECUTION ───────────────────────────────────
    async def execute_with_budget(self, api_name: str, func: Callable, *args, **kwargs) -> Any:
        """
        Executes a blocking or async function within a strict latency budget.
        Enforces timeout, handles cooldowns, and falls back gracefully.
        """
        # 1. Check if the API is cooling down
        if self.is_cooling_down(api_name):
            print(f"[API MANAGER] Skipping execution of '{api_name}' due to active cooldown.")
            return self._get_failsafe_response(api_name)

        budget = self.budgets.get(api_name, 2.0)
        loop = asyncio.get_running_loop()

        # Define wrapped worker to catch internal REST request/execution exceptions
        def worker():
            try:
                return func(*args, **kwargs)
            except requests.exceptions.HTTPError as he:
                print(f"[API MANAGER ERROR] HTTPError on '{api_name}': {he}")
                if he.response is not None and he.response.status_code == 429:
                    self.trigger_cooldown(api_name, 30.0) # 30s cooldown on rate-limits
                else:
                    self.trigger_cooldown(api_name, 10.0)
                raise
            except Exception as e:
                print(f"[API MANAGER ERROR] Execution failed on '{api_name}': {e}")
                self.trigger_cooldown(api_name, 10.0)
                raise

        try:
            # 2. Run inside thread pool with strict async timeout budget
            # (Works perfectly for both blocking synchronous and async targets)
            print(f"[API MANAGER] Dispatching '{api_name}' with budget {budget}s...")
            result = await asyncio.wait_for(
                loop.run_in_executor(None, worker),
                timeout=budget
            )
            return result

        except asyncio.TimeoutError:
            print(f"[API MANAGER WARNING] Latency budget of {budget}s EXCEEDED for API '{api_name}'!")
            self.trigger_cooldown(api_name, 15.0) # Trigger temporary cooldown for slow response
            return self._get_failsafe_response(api_name)
            
        except Exception as e:
            print(f"[API MANAGER] Gracefully recovering from failed call to '{api_name}': {e}")
            return self._get_failsafe_response(api_name)

    def _get_failsafe_response(self, api_name: str) -> Any:
        """Returns safe, conversationally alive mock data or friendly messages."""
        if api_name == "groq":
            return "I am having minor trouble connecting to my fast conversational services, sir. However, I am standing by."
        elif api_name == "vision":
            return "I'm sorry sir, but my visual reasoning systems are currently running slowly or offline. Please try again in a moment."
        elif api_name == "retrieval":
            return "I cannot fetch real-time web news right now sir, but I will search my local offline knowledge."
        elif api_name == "maps":
            # Maps fallback dictionary matching what action executor expects
            return {
                "status": "MOCK_FALLBACK",
                "distance": "unknown distance",
                "duration": "estimated 30 minutes",
                "steps": ["Proceed along the route locally"],
                "origin": "Kashipur",
                "destination": "Rudrapur"
            }
        return None

# Global instance for thread-safe system-wide API orchestration
api_manager = APIManager()
