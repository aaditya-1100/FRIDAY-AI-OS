"""
entity_tracker.py — LLM-free entity extraction using spaCy-style regex patterns.
Tracks: locations, people, products, organizations, topics.
Stores last N entities with type labels for context resolution.
"""
import re

# ── Named location patterns ──────────────────────────────────────────────────
# Handles: "show me the map of Paris", "navigate to Tokyo", "where is London"
# The trick: match trigger verb first, then skip optional filler, then capture name.
_LOCATION_TRIGGERS = re.compile(
    r"(?:map of|navigate to|where is|fly to|zoom into|directions? to|directions? from"
    r"|show\s+me|show|find|go\s+to|open|get|weather in|weather of|temperature in|temperature of)"
    r"(?:\s+(?:the|a|an|me))?"
    r"(?:\s+(?:map|weather|location|route|directions?))?"
    r"(?:\s+(?:of|for|to|in|near|around|from))?"
    r"\s+([A-Za-z\s\-\'\.]{1,35})",
    re.IGNORECASE,
)

# ── Person patterns ──
_PERSON_TRIGGERS = re.compile(
    r"""(?:who is|tell me about|search for|latest on|news about|update on|
        find|information on)\s+
        ([A-Za-z\s\-\'\.]{2,40})""",
    re.VERBOSE | re.IGNORECASE,
)

# ── General subject extraction (proper nouns 2-4 words) ──
_PROPER_NOUN = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\b")

# ── Pronoun references that should trigger context lookup ──
REFERENCE_PRONOUNS = frozenset({
    "it", "that", "this", "there", "him", "her", "they", "them",
    "its", "their", "the same", "the place", "the person", "the location",
    "the city", "latest one", "mentioned", "above"
})


def extract_entity(query: str) -> tuple[str, str] | None:
    """
    Returns (entity_text, entity_type) or None.
    Types: 'location', 'person', 'topic'
    """
    # Location match first (highest priority)
    m = _LOCATION_TRIGGERS.search(query)
    if m:
        name = m.group(1).strip().rstrip(".,?!")
        if len(name) > 2:
            return (name, "location")

    # Person match
    m = _PERSON_TRIGGERS.search(query)
    if m:
        name = m.group(1).strip().rstrip(".,?!")
        if len(name) > 2:
            return (name, "person")

    # Fallback: extract longest capitalized sequence (2+ words = likely proper noun)
    matches = _PROPER_NOUN.findall(query)
    if matches:
        # Prefer longer matches, filter out sentence-start words only
        candidates = [x for x in matches if len(x.split()) >= 2]
        if candidates:
            return (candidates[0], "topic")
        # Single proper noun with at least 4 chars
        single = [x for x in matches if len(x) >= 4]
        if single:
            return (single[0], "topic")

    # Smart lowercase fallback if no capitalized proper nouns are found
    # (highly resilient for fully lowercase voice transcriptions)
    stopwords = {
        "check", "search", "show", "open", "find", "go", "get", "play", "navigate",
        "map", "weather", "news", "videos", "music", "status", "system", "screenshot",
        "the", "a", "an", "for", "to", "in", "on", "at", "of", "with", "by", "about",
        "what", "who", "how", "why", "where", "when", "which", "is", "are", "am", "was",
        "were", "be", "been", "being", "have", "has", "had", "do", "does", "did", "doing",
        "tell", "say", "ask", "me", "you", "he", "she", "it", "they", "we", "us", "him",
        "her", "them", "my", "your", "his", "their", "our", "its", "this", "that", "these",
        "those", "there", "here", "some", "any", "all", "both", "each", "few", "more",
        "most", "other", "some", "such", "no", "nor", "not", "only", "own", "same", "so",
        "than", "too", "very", "can", "will", "just", "should", "would", "could", "may",
        "might", "must", "shall", "please", "like", "want", "need"
    }
    words = [w.strip().rstrip(".,?!") for w in query.split()]
    candidates = [w for w in words if w.lower() not in stopwords and len(w) > 2]
    if candidates:
        return (candidates[0], "topic")

    return None


def has_reference(query: str) -> bool:
    """Returns True if the query contains a pronoun that implies a previous entity."""
    q_lower = query.lower()
    words = set(re.findall(r"\b\w+\b", q_lower))
    return bool(words & REFERENCE_PRONOUNS)