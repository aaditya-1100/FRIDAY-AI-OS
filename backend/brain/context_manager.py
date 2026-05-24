"""
context_manager.py — Conversational context + entity tracking.
Tracks last 5 entities with type labels. Resolves pronouns to last known entity.
Also injects context into follow-up queries before intent parsing.
"""
from collections import deque
from brain.entity_tracker import extract_entity, has_reference


class ContextManager:

    def __init__(self, history_size: int = 5):
        # deque of (entity_text, entity_type) tuples
        self._entities: deque = deque(maxlen=history_size)
        # Last intent for follow-up context (e.g. MAP → follow-up distance queries)
        self.last_intent: str | None = None
        self.last_location: str | None = None

    # ── Update from a new query ───────────────────────────────────────────────
    def update(self, query: str, intent: str | None = None) -> None:
        result = extract_entity(query)
        if result:
            entity_text, entity_type = result
            self._entities.append((entity_text, entity_type))
            if entity_type == "location":
                self.last_location = entity_text
        if intent:
            self.last_intent = intent

    # ── Get the most recent entity of a given type ────────────────────────────
    def last_of_type(self, entity_type: str) -> str | None:
        for text, typ in reversed(self._entities):
            if typ == entity_type:
                return text
        return None

    @property
    def current_entity(self) -> str | None:
        """Last tracked entity (any type)."""
        if self._entities:
            return self._entities[-1][0]
        return None

    # ── Resolve pronoun references in a query ─────────────────────────────────
    def resolve_reference(self, query: str) -> str | None:
        """
        Returns the entity the pronoun likely refers to, or None.
        Priority: location (for spatial queries) > most recent entity.
        """
        if not has_reference(query):
            return None

        q_lower = query.lower()

        # Spatial follow-up or explicit "there" -> prefer last location
        spatial_words = {"distance", "far", "near", "close", "from", "to", "between",
                         "miles", "km", "kilometers", "travel", "drive", "fly", "there"}
        if ("there" in q_lower or any(w in q_lower for w in spatial_words)) and self.last_location:
            return self.last_location

        return self.current_entity

    # ── Inject resolved context into the query before sending to LLM ─────────
    def enrich_query(self, query: str) -> str:
        """
        If query has a pronoun reference, replace it with the resolved entity
        so LLM gets full context even without conversation history.
        """
        resolved = self.resolve_reference(query)
        if not resolved:
            return query

        import re
        # Use regex word boundaries \b to replace pronouns flawlessly even near punctuation
        replacements = {
            r"\bit\b": resolved,
            r"\bthat\b": resolved,
            r"\bthis\b": resolved,
            r"\bthere\b": resolved,
            r"\bits\b": f"{resolved}'s",
            r"\bthe\b\s+place\b": resolved,
            r"\bthe\b\s+city\b": resolved,
            r"\bthe\b\s+location\b": resolved,
        }
        q = query
        for pattern, replacement in replacements.items():
            q = re.sub(pattern, replacement, q, flags=re.IGNORECASE)
        return q.strip()