"""
retrieval_utils.py — Query rewriting, ranking, and verification utilities.

Supports the realtime retrieval pipeline with:
  - Deterministic query rewriting (no LLM)
  - Freshness-aware result ranking
  - Authority-based scoring
  - Stale result verification and filtering

All functions are pure Python — NO LLM calls, NO network calls.
"""

import re
from datetime import datetime


# ─── QUERY REWRITING ─────────────────────────────────────────────────────────

def rewrite_query(query: str) -> list[str]:
    """Deterministic, rule-based query rewriter.

    Returns a list of 1–2 optimized search strings.
    Pure string manipulation — NO LLM calls.
    """
    q = query.lower().strip()
    year = datetime.now().year
    queries: list[str] = []

    # ── Rule 1: Compound question splitting ──────────────────────────────────
    # "who is PM of UK and how old is he" → two separate queries
    question_words = ("who", "what", "how", "where", "when", "why", "which")
    if " and " in q:
        parts = q.split(" and ", 1)
        left, right = parts[0].strip(), parts[1].strip()
        left_has_qword = any(left.startswith(w) for w in question_words)
        right_has_qword = any(right.startswith(w) for w in question_words)
        if left_has_qword and right_has_qword and len(left) > 8 and len(right) > 8:
            queries.append(left)
            queries.append(right)
            return queries

    # ── Rule 2: Media/video query enhancement ────────────────────────────────
    _VIDEO_PATTERN = re.compile(
        r'\b(latest|new|newest|recent)\b.*\b(video|upload)s?\b'
        r'|\b(video|upload)s?\b.*\b(latest|new|newest|recent)\b',
        re.I,
    )
    if _VIDEO_PATTERN.search(q):
        # "latest MrBeast video" → site-scoped YouTube search
        creator = re.sub(r'\b(latest|new|newest|recent)\b', '', q).strip()
        creator = re.sub(r'\b(video|upload)s?\b', '', creator).strip()
        creator = re.sub(r'\b(of|by|from|the|show|me|find|get)\b', '', creator).strip()
        creator = re.sub(r'\s+', ' ', creator).strip()
        if creator:
            queries.append(f"site:youtube.com {creator} latest video {year}")
        queries.append(q)
        return queries[:2]

    # ── Rule 3: Sports/live score enhancement ────────────────────────────────
    sports_signals = ("score", "live score", "standings", "results", "match today")
    if any(ss in q for ss in sports_signals):
        queries.append(f"{q} {year}")
        queries.append(q)
        return queries[:2]

    # ── Rule 4: Trend query enhancement ──────────────────────────────────────
    if any(t in q for t in ("trending", "trends", "viral")):
        queries.append(f"{q} today {year}")
        queries.append(q)
        return queries[:2]

    # ── Rule 5: News queries with year boost ─────────────────────────────────
    if any(n in q for n in ("news", "headlines", "breaking")):
        queries.append(f"{q} {year}")
        queries.append(q)
        return queries[:2]

    # ── Rule 6: Launch / Space queries with year boost ───────────────────────
    if "latest launch" in q or "recent launch" in q or "space launch" in q or "spacex launch" in q:
        queries.append(f"{q} {year}")
        queries.append(q)
        return queries[:2]

    # ── Default: return as-is ────────────────────────────────────────────────
    return [q]


# ─── RESULT RANKING & SCORING ────────────────────────────────────────────────

_AUTHORITY_DOMAINS: dict[str, float] = {
    # Video / Reference
    "youtube.com": 1.0, "wikipedia.org": 0.9,
    # News (international)
    "bbc.com": 0.9, "bbc.co.uk": 0.9,
    "reuters.com": 0.9, "apnews.com": 0.9, "nytimes.com": 0.85,
    "theguardian.com": 0.85, "cnn.com": 0.8,
    # Sports
    "espncricinfo.com": 0.9, "espn.com": 0.9, "cricbuzz.com": 0.85,
    # Government / Science
    "gov.in": 0.9, "gov.uk": 0.9, "whitehouse.gov": 0.9,
    "nasa.gov": 0.95, "who.int": 0.9,
    # News (India)
    "ndtv.com": 0.8, "thehindu.com": 0.8, "hindustantimes.com": 0.8,
    "indianexpress.com": 0.8, "timesofindia.indiatimes.com": 0.75,
    # Weather
    "weather.com": 0.85, "accuweather.com": 0.85,
    # Entertainment
    "imdb.com": 0.85, "rottentomatoes.com": 0.8,
}

_FRESHNESS_PATTERNS: list[tuple] = [
    (re.compile(r'\b(\d+)\s*(?:min(?:ute)?s?|m)\s*ago\b', re.I), lambda m: int(m.group(1))),
    (re.compile(r'\b(\d+)\s*(?:hour|hr)s?\s*ago\b', re.I), lambda m: int(m.group(1)) * 60),
    (re.compile(r'\b(\d+)\s*days?\s*ago\b', re.I), lambda m: int(m.group(1)) * 1440),
    (re.compile(r'\byesterday\b', re.I), lambda _: 1440),
    (re.compile(r'\btoday\b', re.I), lambda _: 120),
    (re.compile(r'\bjust now\b', re.I), lambda _: 5),
]

_STOPWORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "of", "in", "on",
    "for", "to", "and", "or", "what", "who", "how", "where", "when",
    "it", "at", "by", "with", "from", "this", "that", "be", "has",
    "me", "show", "tell", "get", "find",
})


def _score_freshness(text: str) -> float:
    """Score freshness from 0.0 (stale) to 1.0 (just now)."""
    for pattern, minutes_fn in _FRESHNESS_PATTERNS:
        m = pattern.search(text)
        if m:
            minutes_ago = minutes_fn(m)
            if minutes_ago <= 60:
                return 1.0
            elif minutes_ago <= 360:
                return 0.8
            elif minutes_ago <= 1440:
                return 0.6
            elif minutes_ago <= 4320:
                return 0.4
            return 0.2
    # Check for current year mention
    current_year = str(datetime.now().year)
    if current_year in text:
        return 0.5
    return 0.3  # no temporal signal


def _score_authority(text: str) -> float:
    """Score authority from 0.0 (unknown) to 1.0 (highly authoritative)."""
    text_lower = text.lower()
    for domain, score in _AUTHORITY_DOMAINS.items():
        if domain in text_lower:
            return score
    # Known high-quality source labels from our own pipeline
    if any(label in text_lower for label in ("google direct answer", "knowledge:", "quick fact:")):
        return 0.9
    return 0.4  # unknown source


def _score_relevance(text: str, query_words: set[str]) -> float:
    """Score relevance from 0.0 to 1.0 based on query word overlap."""
    text_words = set(text.lower().split())
    if not query_words:
        return 0.5
    overlap = query_words & text_words
    ratio = len(overlap) / len(query_words)
    return min(ratio + 0.2, 1.0)  # baseline 0.2 since all results are query-related


def rank_and_filter(context_parts: list[str], query: str, max_results: int = 8) -> list[str]:
    """Score and rank context snippets by relevance, freshness, authority.

    Returns the top ``max_results`` unique snippets, sorted by composite score.
    """
    if len(context_parts) <= 1:
        return context_parts

    q_words = set(query.lower().split()) - _STOPWORDS

    scored: list[tuple[float, str]] = []
    for part in context_parts:
        part_lower = part.lower()
        
        # 1. Base scores
        rel = _score_relevance(part, q_words)
        fresh = _score_freshness(part)
        auth = _score_authority(part)
        
        # 2. Heuristics for official source bonus
        official_bonus = 0.0
        # If it matches an official channel, official website, or government release
        if any(w in part_lower for w in ("official channel", "verified channel", "official music video", "official trailer", "press release", "official statement", "announcement")):
            official_bonus += 0.3
            
        # 3. Dynamic multiplier for freshness if query requires recency
        freshness_multiplier = 1.0
        if any(w in query.lower() for w in ("news", "latest", "recent", "live", "score", "trending")):
            freshness_multiplier = 1.5
            
        total = (rel * 0.4) + (fresh * 0.3 * freshness_multiplier) + (auth * 0.3) + official_bonus
        scored.append((total, part))

    scored.sort(key=lambda x: x[0], reverse=True)

    # Deduplicate by first-line similarity
    seen: set[str] = set()
    unique: list[str] = []
    for _score, part in scored:
        key = part.split('\n')[0][:60].lower().strip()
        if key not in seen:
            seen.add(key)
            unique.append(part)
        if len(unique) >= max_results:
            break

    return unique


# ─── RESULT VERIFICATION ────────────────────────────────────────────────────

def verify_results(context_parts: list[str], query: str) -> list[str]:
    """Lightweight verification — remove clearly invalid or stale results.

    Checks:
      - Skip very short/empty snippets
      - For freshness-critical queries, filter snippets referencing old years
    """
    if not context_parts:
        return context_parts

    q_lower = query.lower()
    current_year = datetime.now().year
    verified: list[str] = []

    for part in context_parts:
        # Skip very short snippets (likely noise)
        if len(part.strip()) < 15:
            continue

        # For freshness-critical queries, filter stale year references
        if any(w in q_lower for w in ("news", "latest", "today", "current", "trending", "live")):
            old_years = re.findall(r'\b(20[01]\d|201[0-9]|202[0-3])\b', part)
            current_refs = re.findall(rf'\b{current_year}\b', part)
            last_year_refs = re.findall(rf'\b{current_year - 1}\b', part)
            if old_years and not current_refs and not last_year_refs:
                print(f"[VERIFY] Filtering stale snippet (year {old_years[0]}): {part[:80]}")
                continue

        verified.append(part)

    # Never return empty if we had data — fall back to original
    return verified if verified else context_parts
