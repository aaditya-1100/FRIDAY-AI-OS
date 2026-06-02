"""
system/location_agent.py — High-precision location intelligence and IP Geolocation manager.
Provides high-speed caching and robust fallbacks.
"""
import requests
import time
from core.api_manager import api_manager

class LocationAgent:
    """
    Handles Aaditya's current location detection and route inference.
    Checks:
      1. High-speed internal memory coordinates.
      2. IP Geolocation endpoint lookup (e.g. ip-api.com/json) with micro TTL cache.
      3. Authoritative default coordinates (Kashipur, Uttarakhand, India).
    """
    def __init__(self):
        self.default_city = "Kashipur"
        self.default_location = "Kashipur, Uttarakhand, India"
        self.default_lat_lon = (29.2098, 78.9618)
        
        # In-memory cached geolocated city and coords
        self._cached_location = None
        self._cached_coords = None
        self._last_resolved_time = 0.0
        self._cache_ttl = 3600.0 # Cache IP geolocation for 1 hour

    def resolve_current_location(self) -> dict:
        """
        Resolves current location using geolocated IP coordinates, enforcing a 1-hour cache TTL.
        Returns a dict: {"city": str, "coords": (lat, lon), "formatted": str}
        """
        now = time.time()
        if self._cached_location and (now - self._last_resolved_time < self._cache_ttl):
            return self._cached_location

        print("[LOCATION] Resolving geolocated IP location...")
        try:
            # Call free, high-speed IP geolocation API
            r = requests.get("http://ip-api.com/json", timeout=2.0)
            r.raise_for_status()
            data = r.json()
            if data.get("status") == "success":
                resolved = {
                    "city": data.get("city", self.default_city),
                    "coords": (data.get("lat", self.default_lat_lon[0]), data.get("lon", self.default_lat_lon[1])),
                    "formatted": f"{data.get('city')}, {data.get('regionName')}, {data.get('country')}"
                }
                self._cached_location = resolved
                self._last_resolved_time = now
                print(f"[LOCATION] Successfully geolocated current location: {resolved['formatted']} {resolved['coords']}")
                return resolved
        except Exception as e:
            print(f"[LOCATION ERROR] IP Geolocation lookup failed: {e}. Falling back to default: {self.default_location}")
        
        # Safe authoritative fallback
        fallback = {
            "city": self.default_city,
            "coords": self.default_lat_lon,
            "formatted": self.default_location
        }
        return fallback

    def infer_route_context(self, destination: str) -> dict:
        """
        Contextual route inference helper.
        Given a destination (e.g. 'Delhi'), infers Aaditya's current geolocated city as the origin
        and prepares route metadata.
        """
        current = self.resolve_current_location()
        origin = current["city"]
        print(f"[LOCATION] Contextual Route Inferred: origin='{origin}' -> destination='{destination}'")
        return {
            "origin": origin,
            "destination": destination,
            "coords": current["coords"]
        }

location_agent = LocationAgent()
