"""
entity_tracker.py — LLM-free entity extraction.
Tracks: locations, people, apps, videos, websites, files, media, topics.
"""
from __future__ import annotations

import re




# ─────────────────────────────────────────────────────────────────────────────
# Location patterns
# ─────────────────────────────────────────────────────────────────────────────

_LOCATION_TRIGGERS = re.compile(
    r"(?:map of|navigate to|where is|fly to|zoom into|directions?\s+to|directions?\s+from"
    r"|go\s+to|weather in|weather of|temperature in|temperature of"
    r"|route to|route from|flight to|flight from|drive to|drive from|travel to|travel from"
    r"|distance from|distance to|near|around|locate)"
    r"(?:\s+(?:the|a|an|me))?"
    r"(?:\s+(?:map|weather|location|route|directions?))?"
    r"(?:\s+(?:of|for|to|in|near|around|from))?"
    r"\s+([A-Za-z][A-Za-z\s\-\'\.]{1,34})",
    re.IGNORECASE,
)

# Matches "X to Y" route patterns: "Paris to London", "Kashipur to Delhi"
_ROUTE_PATTERN = re.compile(
    r"\b([A-Z][a-z]{2,20}(?:\s+[A-Z][a-z]{2,15})?)\s+to\s+([A-Z][a-z]{2,20}(?:\s+[A-Z][a-z]{2,15})?)\b"
)


# ─────────────────────────────────────────────────────────────────────────────
# Person patterns
# ─────────────────────────────────────────────────────────────────────────────

_PERSON_TRIGGERS = re.compile(
    r"""(?:who is|tell me about|search for|latest on|news about|update on|
        find|information on|about|directed by|founded by|created by|invented by|
        who (?:is|was|owns|runs|leads|founded|created|directed|made)|
        talk about|what did|what has)\s+
        ([A-Za-z][A-Za-z\s\-\'\.]{1,39})""",
    re.VERBOSE | re.IGNORECASE,
)

# Well-known person name fragments for stricter matching
_KNOWN_PERSON_FRAGMENTS = frozenset({
    "elon", "musk", "trump", "modi", "rober", "bezos", "gates", "zuckerberg",
    "yann", "lecun", "sam", "altman", "sundar", "pichai", "satya", "nadella",
    "nolan", "tarantino", "spielberg", "einstein", "newton",
})


# ─────────────────────────────────────────────────────────────────────────────
# App patterns
# ─────────────────────────────────────────────────────────────────────────────

_KNOWN_APPS = frozenset({
    "chrome", "firefox", "edge", "safari", "brave",
    "spotify", "youtube", "netflix", "prime",
    "vscode", "vs code", "visual studio", "pycharm", "intellij",
    "notepad", "word", "excel", "powerpoint", "onenote",
    "discord", "slack", "telegram", "whatsapp", "zoom", "teams",
    "calculator", "paint", "explorer", "file explorer",
    "settings", "task manager", "cmd", "powershell", "terminal",
    "steam", "obs", "vlc", "mpv",
    "photoshop", "illustrator", "figma",
    "physics wallah", "pw",
})

_APP_TRIGGERS = re.compile(
    r"(?:open|start|launch|close|quit|exit|run|switch to|focus|bring up)\s+"
    r"(?:the\s+)?([A-Za-z][A-Za-z\s\-]{1,30})",
    re.IGNORECASE,
)


# ─────────────────────────────────────────────────────────────────────────────
# Video patterns
# ─────────────────────────────────────────────────────────────────────────────

_VIDEO_TRIGGERS = re.compile(
    r"""(?:latest|newest|recent|new|watch|play|open|show|find|search|get)\s+
        (?:(?:video|clip|episode|vlog|tutorial|lecture)(?:\s+(?:by|from|of))?\s+)?
        (?:(?:by|from|of)\s+)?
        ([A-Za-z][A-Za-z0-9\s\-\'\.]{2,50})
        (?:\s+(?:video|clip|episode|vlog|tutorial|lecture))?""",
    re.VERBOSE | re.IGNORECASE,
)

_VIDEO_CHANNEL_WORDS = frozenset({
    "video", "videos", "channel", "playlist", "rober", "veritasium", "kurzgesagt",
    "3blue1brown", "vsauce", "mkbhd", "linus", "fireship",
})


# ─────────────────────────────────────────────────────────────────────────────
# Website patterns
# ─────────────────────────────────────────────────────────────────────────────

_URL_PATTERN = re.compile(
    r"https?://[^\s]+|www\.[^\s]+|\b[\w\-]+\.(com|org|net|io|co|dev|ai|app|edu|gov)\b",
    re.IGNORECASE,
)

_KNOWN_WEBSITES = frozenset({
    "youtube", "google", "github", "stackoverflow", "reddit", "twitter", "x",
    "instagram", "linkedin", "wikipedia", "medium", "notion", "figma",
    "chatgpt", "openai", "anthropic", "perplexity", "amazon",
})

_WEBSITE_TRIGGERS = re.compile(
    r"(?:open|go to|visit|browse|navigate to|check|show|view)\s+"
    r"(?:the\s+)?([A-Za-z][A-Za-z0-9\s\-\.]{1,40})(?:\.com|\.org|\.io|\.net|\.ai)?",
    re.IGNORECASE,
)


# ─────────────────────────────────────────────────────────────────────────────
# File patterns
# ─────────────────────────────────────────────────────────────────────────────

_FILE_PATTERN = re.compile(
    r"\b([\w\-\s]{1,30}\.(pdf|docx?|txt|xlsx?|pptx?|csv|json|py|js|ts|html|css|md|yaml|yml|xml|png|jpg|jpeg|mp4|mp3))\b",
    re.IGNORECASE,
)

_FILE_TRIGGERS = re.compile(
    r"(?:read|open|edit|view|load|import|export|save|analyze|summarize|explain)\s+"
    r"(?:the\s+|this\s+|a\s+)?([A-Za-z][A-Za-z0-9\s\-\.]{2,40}\.(?:pdf|docx?|txt|xlsx?|pptx?|csv|json|py|md))",
    re.IGNORECASE,
)


# ─────────────────────────────────────────────────────────────────────────────
# General proper noun fallback
# ─────────────────────────────────────────────────────────────────────────────

_PROPER_NOUN = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\b")

# Stopwords to filter out false proper noun matches
_STOPWORDS = frozenset({
    "check", "search", "show", "open", "find", "go", "get", "play", "navigate",
    "map", "weather", "news", "videos", "music", "status", "system", "screenshot",
    "the", "a", "an", "for", "to", "in", "on", "at", "of", "with", "by", "about",
    "what", "who", "how", "why", "where", "when", "which", "is", "are", "am", "was",
    "were", "be", "been", "being", "have", "has", "had", "do", "does", "did", "doing",
    "tell", "say", "ask", "me", "you", "he", "she", "it", "they", "we", "us",
    "him", "her", "them", "my", "your", "his", "their", "our", "its", "this",
    "that", "these", "those", "there", "here", "some", "any", "all", "both",
    "each", "few", "more", "most", "other", "such", "no", "nor", "not", "only",
    "own", "same", "so", "than", "too", "very", "can", "will", "just", "should",
    "would", "could", "may", "might", "must", "shall", "please", "like", "want",
    "need", "also", "then", "even", "still", "already", "always", "never",
    "far", "long", "time", "route", "close", "zoom", "view", "write", "explain",
    "describe", "summarize", "read", "analyze", "watching", "reading", "looking",
    "screen", "display", "monitor", "app", "video", "website", "file",
    "Friday", "Saturday", "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday",
    "January", "February", "March", "April", "May", "June", "July", "August",
    "September", "October", "November", "December",
})


# ─────────────────────────────────────────────────────────────────────────────
# Reference pronouns (for has_reference checks)
# ─────────────────────────────────────────────────────────────────────────────

REFERENCE_PRONOUNS = frozenset({
    "it", "that", "this", "there", "him", "her", "they", "them",
    "its", "their", "the same", "the place", "the person", "the location",
    "the city", "latest one", "mentioned", "above", "here",
    "he", "she", "his", "theirs", "the video", "the app", "the route",
    "the song", "the track", "the document", "the file", "the website",
    "the page", "the graph", "the chart", "the code",
    # Deliberately EXCLUDING "you", "your", "yourself" — those are FRIDAY self-refs
    # handled by context_manager.py, not entity pronoun resolution
})


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def extract_entity(query: str) -> tuple[str, str] | None:
    """
    Returns the single BEST (entity_text, entity_type) or None.
    Types: 'location', 'route', 'person', 'app', 'video',
           'website', 'file', 'media', 'topic', 'assistant'
    """
    results = extract_all_entities(query)
    return results[0] if results else None


def extract_all_entities(query: str) -> list[tuple[str, str]]:
    """
    Returns ALL extracted (entity_text, entity_type) pairs from a query,
    ordered by priority: location > person > app > website > file > video > topic.
    """
    results: list[tuple[str, str]] = []
    seen: set[str] = set()

    def _add(text: str, etype: str) -> None:
        clean = text.strip().rstrip(".,?!")
        if not clean or len(clean) <= 1:
            return
        
        # User-name / self-reference entity filtering (User-memory isolation)
        clean_norm = clean.lower().replace("'s", "").replace("s", "")
        if etype == "person" and clean_norm in ("aaditya", "sir", "user", "me", "you", "friday", "assistant"):
            return
            
        if clean.lower() not in seen:
            seen.add(clean.lower())
            results.append((clean, etype))

    q = query.strip()
    q_lower = q.lower()

    # 1. Self-reference
    if any(w in q_lower.split() for w in ("friday", "assistant")):
        _add("FRIDAY", "assistant")

    # 2. Route pattern (e.g. "Paris to London")
    for m in _ROUTE_PATTERN.finditer(q):
        origin = m.group(1).strip()
        dest = m.group(2).strip()
        if origin.lower() not in _STOPWORDS and dest.lower() not in _STOPWORDS:
            _add(f"{origin} to {dest}", "route")
            _add(origin, "location")
            _add(dest, "location")

    # 3. Location
    m = _LOCATION_TRIGGERS.search(q)
    if m:
        name = m.group(1).strip().rstrip(".,?!")
        if len(name) > 2 and name.lower() not in _STOPWORDS:
            _add(name, "location")

    # 4. Person
    m = _PERSON_TRIGGERS.search(q)
    if m:
        name = m.group(1).strip().rstrip(".,?!")
        if len(name) > 2 and name.lower() not in _STOPWORDS:
            _add(name, "person")

    # Also check for known person fragments
    for fragment in _KNOWN_PERSON_FRAGMENTS:
        if re.search(r'\b' + re.escape(fragment) + r'\b', q_lower):
            # Extract the full name around this fragment
            pattern = re.compile(
                r'([A-Z][a-z]+\s+)?' + re.escape(fragment.capitalize()) + r'(\s+[A-Z][a-z]+)?',
                re.IGNORECASE
            )
            nm = pattern.search(q)
            if nm:
                full_name = nm.group(0).strip()
                if len(full_name) > 2:
                    _add(full_name, "person")

    # 5. App — check known apps first (most reliable)
    for app in _KNOWN_APPS:
        if re.search(r'\b' + re.escape(app) + r'\b', q_lower):
            app_display = "VS Code" if app in ("vscode", "vs code") else app.title()
            _add(app_display, "app")
            break

    # Also check app triggers
    m = _APP_TRIGGERS.search(q)
    if m:
        app_name = m.group(1).strip().rstrip(".,?!").lower()
        if app_name in _KNOWN_APPS and app_name not in seen:
            app_display = "VS Code" if app_name in ("vscode", "vs code") else app_name.title()
            _add(app_display, "app")

    # 6. Website — check known sites + URL
    url_m = _URL_PATTERN.search(q)
    if url_m:
        _add(url_m.group(0), "website")

    for site in _KNOWN_WEBSITES:
        if re.search(r'\b' + re.escape(site) + r'\b', q_lower):
            # Only if there's an open/go/visit trigger nearby
            _add(site.title(), "website")
            break

    # 7. File
    file_m = _FILE_PATTERN.search(q)
    if file_m:
        _add(file_m.group(1), "file")

    # 8. Video (requires trigger verb + content noun)
    if any(w in q_lower for w in ("video", "watch", "play", "episode", "lecture", "tutorial")):
        vm = _VIDEO_TRIGGERS.search(q)
        if vm:
            vname = vm.group(1).strip().rstrip(".,?!")
            # Strip trailing video terminology
            vname_lower = vname.lower()
            for suffix in ("video", "clip", "episode", "vlog", "tutorial", "lecture"):
                if vname_lower.endswith(suffix):
                    vname = vname[:-len(suffix)].strip()
                    vname_lower = vname.lower()
            if len(vname) > 2 and vname.lower() not in _STOPWORDS:
                # Check it's not just a generic word
                words = vname.lower().split()
                if any(w not in _STOPWORDS for w in words):
                    _add(vname, "video")


    # 9. Proper noun fallback for topic (only if nothing else extracted)

    if len([r for r in results if r[1] not in ("assistant",)]) == 0:
        matches = _PROPER_NOUN.findall(q)
        for m_text in matches:
            if m_text not in _STOPWORDS and len(m_text) >= 3:
                words_list = m_text.split()
                if len(words_list) >= 2:
                    _add(m_text, "topic")
                    break
                elif len(m_text) >= 4:
                    _add(m_text, "topic")
                    break

    # 10. Lowercase word fallback (handles voice transcription without capitalization)
    if not results:
        words = [w.strip().rstrip(".,?!") for w in q.split()]
        candidates = [w for w in words if w.lower() not in _STOPWORDS and len(w) > 2]
        if candidates:
            _add(candidates[0], "topic")

    return results


def has_reference(query: str) -> bool:
    """Returns True if the query contains a pronoun that implies a previous entity."""
    q_lower = query.lower()
    words = set(re.findall(r"\b\w+\b", q_lower))
    # Multi-word reference check
    for ref in REFERENCE_PRONOUNS:
        if " " in ref and ref in q_lower:
            return True
    return bool(words & REFERENCE_PRONOUNS)