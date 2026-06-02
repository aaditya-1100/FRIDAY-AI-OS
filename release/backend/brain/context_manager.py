"""
context_manager.py — Conversational context + entity tracking.

This module now delegates to ConversationContextGraph (context_graph.py)
as the single source of truth for all session intelligence.

100% backward-compatible public API is preserved so all existing pipeline
call sites continue to work without changes.

SCREEN AUTHORITY RULES enforced here:
  - update_passive_visual_context() → lightweight window title only, NO screenshots
  - Screen cognition is NEVER triggered by identity, memory, or casual queries
"""
from __future__ import annotations

from brain.context_graph import ConversationContextGraph
from brain.entity_tracker import extract_entity, has_reference


class ContextManager:
    """
    Backward-compatible wrapper around ConversationContextGraph.

    All context intelligence is delegated to the graph.
    Existing call sites (pipeline.py, action_executor.py, planner.py)
    continue to work without modification.
    """

    def __init__(self, history_size: int = 5):
        # Primary intelligence store — single source of truth
        self._graph = ConversationContextGraph(entity_history_size=max(history_size * 6, 30))

        # ── Backward-compat public attributes ──────────────────────────────
        # These proxy to the graph and sub-sessions transparently.
        self.last_intent: str | None = None

        # Passive visual context (lightweight — title + process only)
        self.current_screen_title: str | None = None
        self.current_screen_process: str | None = None
        self.current_ocr_text: str | None = None
        self.current_workflow_snapshot: str | None = None
        self.last_active_app: str | None = None
        self.last_window_scan_time: float = 0.0
        self.workflow_confidence: float = 0.0

    # ── Graph accessor (for callers that need the full graph) ─────────────────
    @property
    def graph(self) -> ConversationContextGraph:
        return self._graph

    # ── Backward-compat route_session property ────────────────────────────────
    @property
    def route_session(self) -> dict | None:
        """Returns active MapSession as dict, or None. Backward compat."""
        ms = self._graph.get_map_session()
        if not ms:
            return None
        return {
            "origin": ms.route_origin,
            "destination": ms.route_destination,
            "route_data": ms.route_data,
            "distance": ms.distance,
            "duration": ms.duration,
            "cities_crossed": ms.cities_crossed,
            "view_mode": ms.active_view_mode,
        }

    @route_session.setter
    def route_session(self, value: dict | None) -> None:
        if value is None:
            self._graph.map_session.clear_route()
        else:
            self._graph.update_map_session(**value)

    # ── Backward-compat last_location ─────────────────────────────────────────
    @property
    def last_location(self) -> str | None:
        return self._graph.last_location

    @last_location.setter
    def last_location(self, value: str | None) -> None:
        if value:
            self._graph._register(value, "location", source="setter")

    # ── Core update ───────────────────────────────────────────────────────────
    def update(self, query: str, intent: str | None = None) -> None:
        """Update context from a new user query."""
        self._graph.update(query, intent)
        if intent:
            self.last_intent = intent
            self._graph.map_session.touch()

    def update_from_result(self, intent: str, result: dict | None) -> None:
        """Update context from execution result (captures video, track, app entities)."""
        self._graph.update_from_result(intent, result)
        if intent:
            self.last_intent = intent

    # ── Entity accessors ─────────────────────────────────────────────────────
    def last_of_type(self, entity_type: str) -> str | None:
        return self._graph.get(entity_type)

    @property
    def current_entity(self) -> str | None:
        return self._graph.current_entity

    # ── Pronoun resolution ────────────────────────────────────────────────────
    def resolve_reference(self, query: str) -> str | None:
        """Returns the entity a pronoun refers to, or None."""
        if not has_reference(query):
            return None
        return self._graph._resolve_single_pronoun("it") or self._graph.current_entity

    def enrich_query(self, query: str) -> str:
        """
        Enriches the query by:
        1. Resolving FRIDAY self-referential pronouns (you/your/yourself → FRIDAY)
        2. Resolving third-person pronouns (it/that/there/him/her) via ConversationContextGraph
        """
        import re
        q = query

        # 1. FRIDAY self-referential pronouns (unchanged from original)
        self_replacements = {
            r"\byourself\b": "FRIDAY",
            r"\byou\b": "FRIDAY",
            r"\byour\b": "FRIDAY's",
            r"\byou're\b": "FRIDAY is",
        }
        for pattern, replacement in self_replacements.items():
            q = re.sub(pattern, replacement, q, flags=re.IGNORECASE)

        # 2. Third-person pronouns via context graph (covers all 10 entity types)
        q = self._graph.resolve(q)

        return q.strip()

    # ── Screen authority ──────────────────────────────────────────────────────
    def is_screen_cognition_request(self, query: str) -> bool:
        """
        AUTHORITY RULE: Returns True ONLY for explicit screen content requests.
        Never for identity/memory/casual queries.
        """
        return self._graph.is_screen_cognition_request(query)

    def set_screen_context(self, **kwargs) -> None:
        """Update screen session — ONLY called from SCREEN_UNDERSTANDING path."""
        self._graph.set_screen_context(**kwargs)

    # ── Map follow-up detection ───────────────────────────────────────────────
    def detect_map_followup(self, query: str) -> tuple[bool, str, dict]:
        """Zero-LLM map follow-up detection."""
        return self._graph.detect_map_followup(query)

    # ── Passive visual context (lightweight — NO screenshots, NO OCR) ─────────
    def update_passive_visual_context(self) -> None:
        """
        Layer 1 Passive Visual Awareness — window title + process name only.

        STRICT RULES:
        - NO screenshots
        - NO OCR
        - NO vision API calls
        - NO network calls
        Rate-limited to max once per 1.5 seconds.
        """
        import time
        now = time.time()
        if now - self.last_window_scan_time < 1.5:
            decay = (now - self.last_window_scan_time) * 0.05
            self.workflow_confidence = max(0.0, self.workflow_confidence - decay)
            return

        self.last_window_scan_time = now
        try:
            from system.screen_agent import get_active_window_info
            win_info = get_active_window_info()
            if not win_info or not win_info.get("title"):
                return

            title = win_info.get("title", "")
            proc = win_info.get("process", "").lower()

            self.current_screen_title = title
            self.current_screen_process = proc
            self.last_active_app = proc

            # Update graph passive awareness (title + process only)
            self._graph.update_passive_window(title, proc)

            # Build lightweight workflow snapshot (NO vision, NO OCR)
            snapshot = self._build_passive_snapshot(title, proc)
            self.current_workflow_snapshot = snapshot
            self.workflow_confidence = 1.0
            print(f"[AMBIENT AWARENESS] Passive Snapshot: \"{snapshot}\" (Confidence: 1.0)")

        except Exception as e:
            print(f"[AMBIENT ERROR] Failed updating passive visual context: {e}")

    def _build_passive_snapshot(self, title: str, proc: str) -> str:
        """Build a descriptive workflow string from title + process only."""
        t_lower = title.lower()

        if "code" in proc or "devenv" in proc:
            return f"Coding in VS Code. Active file: {title}"
        elif "chrome" in proc or "msedge" in proc or "firefox" in proc:
            if "youtube" in t_lower or "yt" in t_lower:
                cleaned = title.replace("- YouTube", "").strip()
                return f"Watching YouTube: \"{cleaned}\""
            elif "notes" in t_lower or "jee" in t_lower:
                return f"Reading JEE notes: \"{title}\""
            else:
                return f"Browsing: \"{title}\""
        elif "spotify" in proc:
            return "Listening to Spotify"
        elif "notepad" in proc:
            return f"Drafting in Notepad: {title}"
        elif "pdf" in t_lower or "reader" in proc:
            return f"Reading PDF: {title}"
        elif "cmd" in proc or "powershell" in proc or "terminal" in proc:
            return "Running terminal commands"
        elif title:
            return f"Working in: {title}"
        return "Interacting with desktop"

    # ── Context retrieval for LLM injection ──────────────────────────────────
    def get_retrieval_context(self) -> dict:
        """Returns structured context dict for retrieval and planner injection."""
        ctx = self._graph.get_retrieval_context()
        ctx["last_intent"] = self.last_intent
        return ctx

    # ── Cleanup ───────────────────────────────────────────────────────────────
    def clear_screen_context(self) -> None:
        """Wipe screen session and OCR context."""
        self.current_screen_title = None
        self.current_screen_process = None
        self.current_ocr_text = None
        self.workflow_confidence = 0.0
        self.current_workflow_snapshot = None
        self._graph.clear_screen_context()
        print("[CONTEXT] Screen and visual contexts cleared.")

    def clear_expired_payloads(self) -> None:
        """Wipe operational context. Called in pipeline finally block."""
        self.last_intent = None
        self._graph.clear_expired_payloads()
        # Do NOT clear screen context here — it persists for the session