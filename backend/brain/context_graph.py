"""
context_graph.py — ConversationContextGraph
===========================================

Single source of truth for all FRIDAY session intelligence.

Architecture:
  ConversationContextGraph
  ├── MapSession        — map location, route, view mode, cities, ETA
  ├── ScreenSession     — current video, document, website, graph, code
  ├── MediaSession      — active track, artist, playlist
  ├── AppSession        — last opened/active application
  ├── RouteSession      — origin, destination, cached route data
  ├── TopicSession      — active conversation topic
  └── PersonSession     — active person being discussed

Design principles:
  - Zero LLM calls. Zero network calls.
  - All resolution is pure in-process Python.
  - TTL-based pruning. Expired entities never resolve.
  - Confidence-weighted resolution: explicit > inferred > decayed.
  - Generalizes via entity-type priority, not keyword explosion.
  - SCREEN AUTHORITY: screen cognition is ISOLATED. It NEVER contaminates
    routing for identity, memory, or casual conversational queries.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from collections import deque
from typing import Optional
from brain.entity_tracker import _TAXONOMY


# ─────────────────────────────────────────────────────────────────────────────
# TTL constants (seconds)
# ─────────────────────────────────────────────────────────────────────────────

_TTL = {
    "location":      900,   # 15 min — geographic context fades slowly
    "route":         900,   # 15 min — route session stays active
    "person":        600,   # 10 min
    "video":         600,   # 10 min
    "website":       600,   # 10 min
    "file":          600,   # 10 min
    "app":           600,   # 10 min
    "topic":         600,   # 10 min
    "screen":        900,   # 15 min — screen context persists until replaced
    "media":         600,   # 10 min
    "default":       600,
}


# ─────────────────────────────────────────────────────────────────────────────
# ContextEntity — atomic entity entry with TTL
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ContextEntity:
    text: str
    entity_type: str
    confidence: float = 1.0          # 0.0–1.0; decays over time
    created_at: float = field(default_factory=time.time)
    ttl_seconds: float = 600.0
    source: str = "query"            # "query" | "result" | "screen" | "passive"

    def is_expired(self) -> bool:
        return time.time() - self.created_at > self.ttl_seconds

    @property
    def age_seconds(self) -> float:
        return time.time() - self.created_at

    @property
    def effective_confidence(self) -> float:
        """Confidence decays linearly to 0 at TTL boundary."""
        remaining = max(0.0, 1.0 - self.age_seconds / self.ttl_seconds)
        return self.confidence * remaining


# ─────────────────────────────────────────────────────────────────────────────
# Sub-sessions
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class MapSession:
    current_map_location: str = ""
    route_origin: str = ""
    route_destination: str = ""
    route_data: dict = field(default_factory=dict)
    distance: str = ""
    duration: str = ""
    duration_in_traffic: str = ""
    cities_crossed: list = field(default_factory=list)
    active_view_mode: str = "default"   # "default" | "satellite" | "street" | "terrain"
    last_result: dict = field(default_factory=dict)
    travel_mode: str = "driving"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def is_active(self) -> bool:
        """Map session stays active for 15 minutes since last update."""
        return time.time() - self.updated_at < 900

    def touch(self) -> None:
        self.updated_at = time.time()

    def has_route(self) -> bool:
        return bool(self.route_origin and self.route_destination)

    def clear_route(self) -> None:
        self.route_origin = ""
        self.route_destination = ""
        self.route_data = {}
        self.distance = ""
        self.duration = ""
        self.duration_in_traffic = ""
        self.cities_crossed = []
        self.last_result = {}
        self.touch()


@dataclass
class ScreenSession:
    """
    Stores active screen context from SCREEN_UNDERSTANDING results.

    AUTHORITY RULE: Only populated by explicit screen cognition requests.
    NEVER populated by passive window scanning or memory queries.
    """
    current_subject: str = ""         # generic label for what's on screen
    current_video: str = ""           # video title if watching
    current_document: str = ""        # document/PDF name if reading
    current_website: str = ""         # website URL or title if browsing
    current_graph: str = ""           # graph description if viewing chart
    current_code_file: str = ""       # filename/language if coding
    current_app: str = ""             # active app name
    current_image: str = ""           # image description if viewing
    raw_ocr_snippet: str = ""         # brief OCR snippet for context
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def is_active(self) -> bool:
        return time.time() - self.updated_at < 900

    def touch(self) -> None:
        self.updated_at = time.time()

    def clear(self) -> None:
        self.current_subject = ""
        self.current_video = ""
        self.current_document = ""
        self.current_website = ""
        self.current_graph = ""
        self.current_code_file = ""
        self.current_app = ""
        self.current_image = ""
        self.raw_ocr_snippet = ""
        self.updated_at = time.time()

    def get_primary_subject(self) -> str:
        """Returns the most specific active subject from the screen session."""
        for candidate in (
            self.current_video,
            self.current_document,
            self.current_website,
            self.current_graph,
            self.current_code_file,
            self.current_image,
            self.current_subject,
        ):
            if candidate:
                return candidate
        return ""


@dataclass
class MediaSession:
    current_track: str = ""
    current_artist: str = ""
    current_playlist: str = ""
    platform: str = ""               # "spotify" | "youtube"
    updated_at: float = field(default_factory=time.time)

    def is_active(self) -> bool:
        return time.time() - self.updated_at < 600

    def touch(self) -> None:
        self.updated_at = time.time()


@dataclass
class AppSession:
    last_opened: str = ""
    last_closed: str = ""
    active_app: str = ""
    updated_at: float = field(default_factory=time.time)

    def touch(self) -> None:
        self.updated_at = time.time()


@dataclass
class PersonSession:
    name: str = ""
    context: str = ""                # "person we're discussing"
    updated_at: float = field(default_factory=time.time)

    def is_active(self) -> bool:
        return time.time() - self.updated_at < 600

    def touch(self) -> None:
        self.updated_at = time.time()


@dataclass
class TopicSession:
    topic: str = ""
    context: str = ""
    updated_at: float = field(default_factory=time.time)

    def is_active(self) -> bool:
        return time.time() - self.updated_at < 600

    def touch(self) -> None:
        self.updated_at = time.time()


# ─────────────────────────────────────────────────────────────────────────────
# Pronoun resolution table
# ─────────────────────────────────────────────────────────────────────────────

# Maps pronoun → ordered list of entity_types to check (highest priority first)
_PRONOUN_PRIORITY: dict[str, list[str]] = {
    "it":     ["video", "app", "website", "file", "route", "person", "location", "media", "topic", "company", "brand"],
    "that":   ["video", "app", "website", "file", "route", "person", "location", "topic", "company", "brand"],
    "this":   ["video", "app", "website", "file", "route", "person", "location", "topic", "company", "brand"],
    "its":    ["app", "website", "person", "location", "topic", "company", "brand"],
    "there":  ["location"],
    "here":   ["location"],
    "he":     ["person"],
    "him":    ["person"],
    "she":    ["person"],
    "her":    ["person"],
    "they":   ["person", "topic"],
    "them":   ["person", "topic"],
    "his":    ["person"],
    "their":  ["person", "topic"],
    "theirs": ["person", "topic"],
    "the place":    ["location"],
    "the city":     ["location"],
    "the location": ["location"],
    "the person":   ["person"],
    "the video":    ["video"],
    "the app":      ["app"],
    "the route":    ["route"],
    "the same":     ["route", "location", "topic"],
    "same place":   ["location"],
    "same route":   ["route"],
    "the song":     ["media"],
    "the track":    ["media"],
    "the document": ["file"],
    "the file":     ["file"],
    "the website":  ["website"],
    "the page":     ["website", "file"],
    "the graph":    ["screen"],
    "the chart":    ["screen"],
    "the code":     ["screen"],
    "my project":    ["assistant"],
    "the project":   ["assistant"],
    "the assistant": ["assistant"],
    "the ai":        ["assistant"],
    "my ai":         ["assistant"],
    "project":       ["assistant"],
    "assistant":     ["assistant"],
    "ai":            ["assistant"],
}

# Multi-word pronouns that must be matched before single-word scan
_MULTI_WORD_PRONOUNS = sorted(
    [p for p in _PRONOUN_PRIORITY if " " in p],
    key=len,
    reverse=True,   # longest first to prevent partial matches
)

# Single-word pronouns (boundary-matched)
_SINGLE_WORD_PRONOUNS = {p for p in _PRONOUN_PRIORITY if " " not in p}


# ─────────────────────────────────────────────────────────────────────────────
# Map follow-up phrase detection (zero-LLM fast-path)
# ─────────────────────────────────────────────────────────────────────────────

_MAP_FOLLOWUP_PATTERNS: list[tuple[re.Pattern, str, dict]] = [
    # ETA / Duration
    (re.compile(r"\b(how long|how much time|what.?s the (eta|time|duration)|eta|time to get|travel time)\b", re.I), "eta", {}),
    # Distance
    (re.compile(r"\b(how far|what.?s the distance|distance|how many (km|miles|kilometers))\b", re.I), "distance", {}),
    # Cities crossed
    (re.compile(r"\b(which cities|what cities|cities (will i|i will)|cross|pass through|via|through which)\b", re.I), "cities_crossed", {}),
    # Fastest route
    (re.compile(r"\b(fastest|quickest|shortest|best route|alternate route|alternative)\b", re.I), "fastest_route", {}),
    # Avoid tolls
    (re.compile(r"\b(avoid toll|without toll|no toll|toll.?free)\b", re.I), "avoid_tolls", {}),
    # Traffic
    (re.compile(r"\b(traffic|congestion|jam|heavy traffic|current traffic)\b", re.I), "traffic", {}),
    # Satellite view
    (re.compile(r"\b(satellite|aerial|bird.?s.?eye|satellite view)\b", re.I), "satellite_view", {}),
    # Street view
    (re.compile(r"\b(street view|ground level|street level)\b", re.I), "street_view", {}),
    # Zoom out (specific first)
    (re.compile(r"\b(zoom out|zoom less)\b", re.I), "zoom_out", {}),
    # Zoom in
    (re.compile(r"\b(zoom in|zoom more)\b", re.I), "zoom_in", {}),
    # Specific nearby airports
    (re.compile(r"\b(airports?)\b", re.I), "nearby_places", {"place_type": "airport"}),
    # Specific nearby hotels
    (re.compile(r"\b(hotels?|stays?|accommodations?)\b", re.I), "nearby_places", {"place_type": "lodging"}),
    # Specific nearby petrol/gas
    (re.compile(r"\b(petrols?|gas stations?|fuel stations?|petrol pumps?)\b", re.I), "nearby_places", {"place_type": "gas_station"}),
    # Generic Nearby (fallback)
    (re.compile(r"\b(nearby|near (the route|destination|origin)|around (here|there)|close by)\b", re.I), "nearby_places", {}),
]

# Phrases that definitively signal a map follow-up (even without explicit route reference)
_MAP_CONTEXT_ANCHORS = frozenset({
    "the route", "this route", "that route", "same route", "the map",
    "this map", "that map", "the journey", "this journey",
})


# ─────────────────────────────────────────────────────────────────────────────
# Screen cognition trigger detection (AUTHORITY ISOLATION)
# ─────────────────────────────────────────────────────────────────────────────

_SCREEN_EXPLICIT_TRIGGERS = re.compile(
    r"\b(what am i (watching|reading|looking at|viewing|studying)"
    r"|what('?s| is) (on|visible on|shown on|displayed on)( my)? (screen|monitor|display)"
    r"|explain (this|what'?s on screen|what is on screen|this (graph|chart|diagram|derivation|equation|code|page|document|slide|image))"
    r"|explain what (you see|is visible)"
    r"|summarize (this|the (page|document|article|video|content))"
    r"|describe (my|the|this|this (graph|chart|diagram|screen)) (screen|display|monitor|page|document|chart|graph|diagram)"
    r"|what (code|website|graph|chart|document|video|image|page|diagram|equation) (am i|is this|is on|is visible)"
    r"|read what'?s on (the|my)? screen"
    r"|read (this|what'?s on screen)"
    r"|analyze (this|what'?s on screen|this (graph|chart|image|diagram))"
    r"|what is this (graph|chart|diagram|equation|derivation|code|image|page))\b",
    re.I,
)

# Phrases that should NEVER trigger screen cognition (identity/memory guards)
_SCREEN_AUTHORITY_BLOCKLIST = re.compile(
    r"\b(who (is|are|am) (i|aaditya|friday|you)|what are my (goals|targets|preferences)|"
    r"how are you|how'?s (your|the) (day|system|cpu)|my (name|class|jee|targets)|"
    r"what do you know|who built you|who created you|what is your (name|function))\b",
    re.I,
)


# ─────────────────────────────────────────────────────────────────────────────
# ConversationContextGraph — the single source of truth
# ─────────────────────────────────────────────────────────────────────────────

class ConversationContextGraph:
    """
    Persistent session-scoped entity memory for FRIDAY.

    Tracks 10 entity types with TTL-based pruning.
    Provides unified pronoun resolution across all entity types.
    Maintains MapSession, ScreenSession, MediaSession, AppSession,
    PersonSession, and TopicSession as structured sub-sessions.

    Zero LLM calls. Zero network calls. < 2ms overhead per query.
    """

    def __init__(self, entity_history_size: int = 30):
        # Rolling entity history — most recent at right
        self._entities: deque[ContextEntity] = deque(maxlen=entity_history_size)

        # Structured sub-sessions
        self.map_session = MapSession()
        self.screen_session = ScreenSession()
        self.media_session = MediaSession()
        self.app_session = AppSession()
        self.person_session = PersonSession()
        self.topic_session = TopicSession()

        # Passive window awareness (lightweight, no screenshot)
        self._passive_window_title: str = ""
        self._passive_process_name: str = ""
        self._last_passive_scan: float = 0.0

    # ── Entity registration ───────────────────────────────────────────────────

    def _register(
        self,
        text: str,
        entity_type: str,
        confidence: float = 1.0,
        source: str = "query",
    ) -> None:
        """Add an entity to the rolling history."""
        if not text or not text.strip():
            return
        text = text.strip()
        
        # User-name / self-reference entity filtering (User-memory isolation)
        clean_lower = text.lower().strip().replace("'s", "").replace("s", "")
        if entity_type == "person" and clean_lower in ("aaditya", "sir", "user", "me", "you", "friday", "assistant"):
            return
            
        ttl = _TTL.get(entity_type, _TTL["default"])
        entity = ContextEntity(
            text=text,
            entity_type=entity_type,
            confidence=confidence,
            ttl_seconds=float(ttl),
            source=source,
        )
        self._entities.append(entity)
        print(f"[CTX_GRAPH] Registered {entity_type}: '{text}' (conf={confidence:.2f}, src={source})")

    # ── Core update ───────────────────────────────────────────────────────────

    def update(self, query: str, intent: str | None = None) -> None:
        """
        Called on every turn BEFORE intent parsing.
        Extracts entities from the raw query and updates sub-sessions.
        """
        self.prune_expired()
        if not query:
            return

        from brain.entity_tracker import extract_all_entities
        entities = extract_all_entities(query)
        for text, etype in entities:
            self._register(text, etype, confidence=1.0, source="query")
            self._update_subsession_from_entity(text, etype, intent)

    def update_from_result(self, intent: str, result: dict | None) -> None:
        """
        Called AFTER execute_action returns.
        Extracts entities from assistant responses so follow-ups work.
        E.g. "Playing Mark Rober video" → stores video entity.
        """
        if not result or not isinstance(result, dict):
            return

        self.prune_expired()
        response = result.get("response", "")
        if not response:
            return

        # Extract entities from the spoken response text
        from brain.entity_tracker import extract_all_entities
        entities = extract_all_entities(response)
        for text, etype in entities:
            self._register(text, etype, confidence=0.85, source="result")
            self._update_subsession_from_entity(text, etype, intent)

        # Intent-specific structured updates
        if intent == "OPEN":
            # e.g. "Opening Chrome sir" → app_session.last_opened = Chrome
            pass  # entity_tracker handles app extraction

        elif intent in ("PLAY_MEDIA", "SPOTIFY_CONTROL"):
            # Capture what's now playing
            resp_lower = response.lower()
            for prefix in ("playing '", "playing \"", "playing "):
                if prefix in resp_lower:
                    tail = response[resp_lower.index(prefix) + len(prefix):]
                    track = tail.split("'")[0].split('"')[0].split(" by ")[0].strip()
                    if track:
                        self.media_session.current_track = track
                        self.media_session.touch()
                        self._register(track, "media", confidence=1.0, source="result")

        elif intent == "MAP_ROUTE":
            # Structured route data is stored directly by action_executor
            # via update_map_session — just touch here
            self.map_session.touch()

        elif intent == "SCREEN_UNDERSTANDING":
            # Parse screen context from the analysis response
            self._extract_screen_context_from_response(response)

    def _update_subsession_from_entity(
        self, text: str, etype: str, intent: str | None
    ) -> None:
        """Keep sub-sessions in sync when entities are registered."""
        if etype == "location":
            if not self.map_session.current_map_location:
                self.map_session.current_map_location = text
            self.map_session.touch()

        elif etype == "person":
            self.person_session.name = text
            self.person_session.touch()

        elif etype == "topic":
            self.topic_session.topic = text
            self.topic_session.touch()

        elif etype == "app":
            if intent == "OPEN":
                self.app_session.last_opened = text
                self.app_session.active_app = text
            elif intent == "WINDOW_CONTROL":
                self.app_session.last_closed = text
                if self.app_session.active_app == text:
                    self.app_session.active_app = ""
            self.app_session.touch()

        elif etype == "video":
            self.media_session.current_track = text
            self.media_session.platform = "youtube"
            self.media_session.touch()

        elif etype == "media":
            self.media_session.current_track = text
            self.media_session.touch()

    # ── MapSession management ─────────────────────────────────────────────────

    def update_map_session(self, **kwargs) -> None:
        """
        Directly update MapSession fields after a MAP or MAP_ROUTE execution.
        Called by action_executor after a successful route fetch.
        """
        for key, value in kwargs.items():
            if hasattr(self.map_session, key):
                setattr(self.map_session, key, value)
        self.map_session.touch()

        if self.map_session.current_map_location:
            self._register(
                self.map_session.current_map_location, "location", confidence=1.0, source="result"
            )
        # Also register route as a dedicated entity (registered last to ensure it is most recent)
        if self.map_session.has_route():
            route_text = f"{self.map_session.route_origin} to {self.map_session.route_destination}"
            self._register(route_text, "route", confidence=1.0, source="result")

    def get_map_session(self) -> MapSession | None:
        """Returns active MapSession or None if expired/empty."""
        if self.map_session.is_active() and (
            self.map_session.current_map_location or self.map_session.has_route()
        ):
            return self.map_session
        return None

    # ── ScreenSession management ──────────────────────────────────────────────

    def set_screen_context(self, **kwargs) -> None:
        """
        Update ScreenSession fields.
        ONLY called from SCREEN_UNDERSTANDING execution path.
        NEVER from memory, identity, or conversational paths.
        """
        for key, value in kwargs.items():
            if hasattr(self.screen_session, key) and value:
                setattr(self.screen_session, key, value)
        self.screen_session.touch()

        # Register screen subject as a typed entity
        subject = self.screen_session.get_primary_subject()
        if subject:
            self._register(subject, "screen", confidence=1.0, source="screen")

    def clear_screen_context(self) -> None:
        """Wipes screen session. Called when screen changes significantly."""
        self.screen_session.clear()
        print("[CTX_GRAPH] Screen session cleared.")

    def _extract_screen_context_from_response(self, response: str) -> None:
        """
        Parse the SCREEN_UNDERSTANDING response to populate ScreenSession fields.
        Uses pattern matching, not LLM — zero additional overhead.
        """
        resp_lower = response.lower()

        # Video detection patterns
        video_patterns = [
            r"(?:watching|video[:\s]+)['\"]?([A-Za-z0-9][^\n'\"]{3,60})['\"]?",
            r"(?:YouTube video|video titled)[:\s]+['\"]?([A-Za-z0-9][^\n'\"]{3,60})['\"]?",
        ]
        for pat in video_patterns:
            m = re.search(pat, response, re.I)
            if m:
                self.screen_session.current_video = m.group(1).strip()
                self.screen_session.current_subject = self.screen_session.current_video
                self._register(self.screen_session.current_video, "video", confidence=0.9, source="screen")
                return

        # Document detection
        doc_patterns = [
            r"(?:reading|document[:\s]+|file[:\s]+)['\"]?([A-Za-z0-9][^\n'\"]{3,60})['\"]?",
        ]
        for pat in doc_patterns:
            m = re.search(pat, response, re.I)
            if m:
                self.screen_session.current_document = m.group(1).strip()
                self.screen_session.current_subject = self.screen_session.current_document
                self._register(self.screen_session.current_document, "file", confidence=0.9, source="screen")
                return

        # Website detection
        web_patterns = [
            r"(?:browsing|website[:\s]+|viewing)[:\s]+['\"]?([A-Za-z0-9][^\n'\"]{3,60})['\"]?",
        ]
        for pat in web_patterns:
            m = re.search(pat, response, re.I)
            if m:
                self.screen_session.current_website = m.group(1).strip()
                self.screen_session.current_subject = self.screen_session.current_website
                self._register(self.screen_session.current_website, "website", confidence=0.9, source="screen")
                return

        # Graph/chart detection
        if any(w in resp_lower for w in ("graph", "chart", "diagram", "plot", "curve")):
            # Extract graph topic
            m = re.search(r"(?:graph|chart|diagram|plot)[:\s]+(?:of|showing|about|for)?[:\s]*([A-Za-z][^\n.]{3,50})", response, re.I)
            if m:
                self.screen_session.current_graph = m.group(1).strip()
                self.screen_session.current_subject = self.screen_session.current_graph
                self._register(self.screen_session.current_graph, "screen", confidence=0.9, source="screen")
                return

        # Code detection
        if any(w in resp_lower for w in ("code", "function", "class", "script", "programming")):
            m = re.search(r"(?:code|script|file)[:\s]+([A-Za-z][^\n.]{2,40})", response, re.I)
            if m:
                self.screen_session.current_code_file = m.group(1).strip()
                self.screen_session.current_subject = self.screen_session.current_code_file
                self._register(self.screen_session.current_code_file, "screen", confidence=0.85, source="screen")

    # ── Passive screen awareness ──────────────────────────────────────────────

    def update_passive_window(self, title: str, process: str) -> None:
        """
        Lightweight passive awareness — just title + process name.
        NO screenshots. NO OCR. NO vision. NO network calls.
        """
        self._passive_window_title = title or ""
        self._passive_process_name = process or ""
        self._last_passive_scan = time.time()

        # Update app session passively
        if process:
            clean_proc = process.replace(".exe", "").lower()
            self.app_session.active_app = clean_proc
            self.app_session.touch()

    # ── Entity retrieval ─────────────────────────────────────────────────────

    def get(self, entity_type: str) -> str | None:
        """Return the most recent non-expired entity of the given type."""
        self.prune_expired()
        for entity in reversed(self._entities):
            if entity.entity_type == entity_type and not entity.is_expired():
                return entity.text
        return None

    def get_best(self, entity_types: list[str]) -> str | None:
        """
        Return the best (highest effective_confidence) non-expired entity
        among the given types.
        """
        self.prune_expired()
        best: ContextEntity | None = None
        for entity in reversed(self._entities):
            if entity.entity_type in entity_types and not entity.is_expired():
                if best is None or entity.effective_confidence > best.effective_confidence:
                    best = entity
        return best.text if best else None

    @property
    def current_entity(self) -> str | None:
        """Last tracked entity (any type, not expired)."""
        self.prune_expired()
        for entity in reversed(self._entities):
            if not entity.is_expired():
                return entity.text
        return None

    @property
    def last_location(self) -> str | None:
        return self.get("location")

    @property
    def last_person(self) -> str | None:
        return self.get("person")

    @property
    def last_topic(self) -> str | None:
        return self.get("topic") or self.get("screen")

    @property
    def last_app(self) -> str | None:
        return self.get("app") or (self.app_session.last_opened or None)

    # ── Pronoun resolution ────────────────────────────────────────────────────

    def resolve(self, query: str) -> str:
        """
        Syntax Context-Aware Coreference Resolution.
        Uses POS tagging and dependency boundary guards to lock compound nouns
        and resolve standalone pronouns across four confidence states.
        """
        self.prune_expired()
        
        # Lazy-load spacy to keep initialization instant
        if not hasattr(self, "_nlp"):
            self._nlp = None
                
        if not self._nlp:
            return query
            
        doc = self._nlp(query)
        words = [t.text for t in doc]
        
        # Locked terms mapping standard competitors to prevent hijack
        locked_terms = {"chatgpt", "gemini", "claude", "copilot", "perplexity"}
        
        # Lock noun phrases (e.g. "my coding project", "my startup", "my app", "my website")
        locked_indices = set()
        for token in doc:
            if token.text.lower() in locked_terms:
                locked_indices.add(token.i)
            # Lock compound nouns modifying typical pronoun-sensitive nouns
            if token.dep_ == "compound" or (token.dep_ == "amod" and token.head.text.lower() in ("project", "startup", "company", "app", "website")):
                locked_indices.add(token.i)
                locked_indices.add(token.head.i)
                
        # Resolve standalone pronouns
        i = 0
        while i < len(doc):
            token = doc[i]
            token_lower = token.text.lower()
            
            is_pronoun = token.pos_ in ("PRON", "DET") or token_lower in _PRONOUN_PRIORITY
            
            # Standalone guard: cannot be part of compound noun or locked index
            if is_pronoun and token.i not in locked_indices:
                resolved = self._resolve_single_pronoun(token_lower)
                if resolved:
                    words[token.i] = resolved
            i += 1
            
        return self._reconstruct_with_ws(doc, words)

    def _reconstruct_with_ws(self, doc, resolved_words) -> str:
        text = ""
        for i, token in enumerate(doc):
            word = resolved_words[i]
            text += word + token.whitespace_
        return text.strip()

    def _resolve_single_pronoun(self, pronoun: str) -> str | None:
        """
        Resolve one pronoun against the entity graph using a four-state model.
        States:
          - Resolved (Conf >= 0.85) -> Replace
          - Likely (0.70 <= Conf < 0.85) -> Replace
          - Uncertain (0.50 <= Conf < 0.70) -> Do not replace, flag
          - Unknown (Conf < 0.50) -> Do not replace
        """
        priority_types = _PRONOUN_PRIORITY.get(pronoun, [])
        if not priority_types:
            return None

        self.prune_expired()

        now = time.time()
        # Recency maps
        recency = {
            "topic": self.topic_session.updated_at if self.topic_session.is_active() else 0.0,
            "person": self.person_session.updated_at if self.person_session.is_active() else 0.0,
            "media": self.media_session.updated_at if self.media_session.is_active() else 0.0,
            "video": self.media_session.updated_at if (self.media_session.is_active() and self.media_session.platform == "youtube") else 0.0,
            "route": self.map_session.updated_at if (self.map_session.is_active() and self.map_session.has_route()) else 0.0,
            "location": self.map_session.updated_at if (self.map_session.is_active() and self.map_session.current_map_location) else 0.0,
            "website": self.screen_session.updated_at if (self.screen_session.is_active() and self.screen_session.current_website) else 0.0,
            "app": self.app_session.updated_at if (now - self.app_session.updated_at < 600) else 0.0,
        }

        # chronological entities
        entity_recency = {}
        for ent in reversed(self._entities):
            if ent.entity_type in priority_types and not ent.is_expired():
                weight = 1.0 if ent.source in ("query", "result") else 0.5
                if ent.entity_type not in entity_recency:
                    entity_recency[ent.entity_type] = ent.created_at * weight

        sorted_types = sorted(
            priority_types,
            key=lambda t: max(recency.get(t, 0.0), entity_recency.get(t, 0.0)),
            reverse=True
        )

        for etype in sorted_types:
            # Calculate confidence
            base_conf = 0.90 if pronoun in ("my project", "the assistant", "the ai", "my ai") else 0.65
            
            # Chronological decay (15 min window)
            last_ent = None
            for ent in reversed(self._entities):
                if ent.entity_type == etype and not ent.is_expired():
                    last_ent = ent
                    break
                    
            decay = 1.0
            recency_bonus = 0.0
            if last_ent:
                age = now - last_ent.created_at
                decay = max(0.0, 1.0 - (age / 900.0))
                if age < 30.0:
                    recency_bonus = 0.20
            base_conf = base_conf * decay
            
            context_bonus = 0.0
            if self.topic_session.is_active() and any(w in self.topic_session.topic.lower() for w in ("friday", "code", "ai", "project", "system", "automation")):
                context_bonus = 0.10
                
            confidence = base_conf + recency_bonus + context_bonus
            
            # Map four-state model
            if confidence >= 0.85:
                state = "Resolved"
            elif confidence >= 0.70:
                state = "Likely"
            elif confidence >= 0.50:
                state = "Uncertain"
            else:
                state = "Unknown"
                
            # Log trace states if available
            import os
            os.environ["FRIDAY_RESOLUTION_STATE"] = state
            
            if state in ("Resolved", "Likely"):
                if etype == "assistant":
                    return "FRIDAY"
                elif etype == "route":
                    session = self.get_map_session()
                    if session and session.has_route():
                        return f"{session.route_origin} to {session.route_destination}"
                elif etype == "screen":
                    subject = self.screen_session.get_primary_subject()
                    if subject and self.screen_session.is_active():
                        return subject
                elif etype == "media" or etype == "video":
                    if self.media_session.is_active() and self.media_session.current_track:
                        return self.media_session.current_track
                
                # Fallback to rolling history
                if last_ent:
                    return last_ent.text

        return None

    def has_reference(self, query: str) -> bool:
        """Returns True if the query contains pronouns or implicit references."""
        q_lower = query.lower()
        # Check multi-word first
        for pronoun in _MULTI_WORD_PRONOUNS:
            if pronoun in q_lower:
                return True
        # Check single-word with boundary
        words = set(re.findall(r'\b\w+\b', q_lower))
        return bool(words & _SINGLE_WORD_PRONOUNS)

    # ── Map follow-up detection ───────────────────────────────────────────────

    def detect_map_followup(self, query: str) -> tuple[bool, str, dict]:
        """
        Zero-LLM fast-path: checks if query is a map follow-up question.

        Returns:
            (is_followup: bool, action: str, extra_params: dict)

        Only returns True if there is an ACTIVE map session with location/route.
        """
        session = self.get_map_session()
        if not session:
            return False, "", {}

        q_lower = query.lower()

        # EXCLUSION: If query is starting a new route calculation, let it fall through to MAP_ROUTE
        if any(marker in q_lower for marker in ("route to", "directions to", "navigate to", "way to", "go to", "show route to", "show route from")):
            return False, "", {}

        # Check context anchors first
        has_anchor = any(anchor in q_lower for anchor in _MAP_CONTEXT_ANCHORS)

        for pattern, action, extra in _MAP_FOLLOWUP_PATTERNS:
            if pattern.search(q_lower):
                return True, action, extra

        # If there's a location and the query is short + contains spatial/temporal words
        if session.current_map_location and len(query.split()) <= 8:
            spatial_temporal = re.compile(
                r"\b(long|far|distance|time|route|way|fastest|shortest|direct)\b",
                re.I
            )
            if spatial_temporal.search(q_lower) or has_anchor:
                return True, "general_query", {}

        return False, "", {}

    # ── Screen trigger detection ──────────────────────────────────────────────

    def is_screen_cognition_request(self, query: str) -> bool:
        """
        AUTHORITY RULE: Returns True ONLY when the query explicitly
        references visible screen content.

        NEVER returns True for:
        - Identity queries ("who are you", "who is aaditya")
        - Memory queries ("what are my goals")
        - Casual conversation ("how are you")
        """
        # Blocklist takes absolute priority
        if _SCREEN_AUTHORITY_BLOCKLIST.search(query):
            return False
        return bool(_SCREEN_EXPLICIT_TRIGGERS.search(query))

    # ── Context injection for LLM prompts ────────────────────────────────────

    def get_summary(self) -> str:
        """
        Returns a natural language context summary for injection
        into LLM prompt system contexts.
        """
        self.prune_expired()
        parts = []

        # Collect up to 5 most recent non-expired entities
        seen_types: set[str] = set()
        recent_entities = []
        for entity in reversed(self._entities):
            if not entity.is_expired() and entity.entity_type not in seen_types:
                recent_entities.append(entity)
                seen_types.add(entity.entity_type)
                if len(recent_entities) >= 5:
                    break

        if recent_entities:
            entity_strs = [f"{e.text} ({e.entity_type})" for e in recent_entities]
            parts.append("Recent context: " + ", ".join(entity_strs))

        # Map session
        ms = self.get_map_session()
        if ms:
            if ms.has_route():
                parts.append(
                    f"Active route: {ms.route_origin} → {ms.route_destination}"
                    + (f" ({ms.duration})" if ms.duration else "")
                )
            elif ms.current_map_location:
                parts.append(f"Active map location: {ms.current_map_location}")

        # Screen session
        if self.screen_session.is_active():
            subject = self.screen_session.get_primary_subject()
            if subject:
                parts.append(f"Screen context: {subject}")

        # Media session
        if self.media_session.is_active() and self.media_session.current_track:
            parts.append(f"Now playing: {self.media_session.current_track}")

        return " | ".join(parts) if parts else ""

    def get_retrieval_context(self) -> dict:
        """Structured context dict for injection into retrieval and planner paths."""
        self.prune_expired()
        entity_history = [
            {"text": e.text, "type": e.entity_type}
            for e in reversed(self._entities)
            if not e.is_expired()
        ]
        return {
            "last_location": self.last_location,
            "last_entity": self.current_entity,
            "last_intent": None,  # Set by pipeline
            "entity_history": entity_history[:8],
            "conversation_summary": self.get_summary(),
        }

    # ── TTL pruning ───────────────────────────────────────────────────────────

    def prune_expired(self) -> None:
        """Remove TTL-expired entities from the rolling history."""
        before = len(self._entities)
        live = deque(
            (e for e in self._entities if not e.is_expired()),
            maxlen=self._entities.maxlen,
        )
        self._entities = live
        pruned = before - len(self._entities)
        if pruned > 0:
            print(f"[CTX_GRAPH] Pruned {pruned} expired entities.")

    def clear_expired_payloads(self) -> None:
        """Alias for compatibility with ContextManager call sites."""
        self.prune_expired()
