import re

WAKE_PREFIXES = [
    r"^hey friday\b",
    r"^hello friday\b",
    r"^hi friday\b",
    r"^wake up friday\b",
    r"^yo friday\b",
    r"^friday\b"
]

DAY_PREPOSITIONS = [
    r"\bon friday\b",
    r"\bthis friday\b",
    r"\bnext friday\b",
    r"\bcoming friday\b",
    r"\bby friday\b",
    r"\blast friday\b",
    r"\bevery friday\b",
    r"\bfor friday\b",
    r"\buntil friday\b"
]

def clean_text(text: str):
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)
    return text.strip()

def detect_wake_word(query: str) -> bool:
    """
    Detect if query contains a wake word.
    Returns True for wake words that should activate the assistant.
    """
    cleaned = clean_text(query)
    
    # 1. Standalone wake words are always wake words
    if cleaned in ("friday", "hey friday", "hello friday", "hi friday", "yo friday", "wake up friday"):
        return True
        
    # 2. Check if the query starts with one of the wake word prefixes
    for pat in WAKE_PREFIXES:
        if re.search(pat, cleaned):
            return True
            
    # 3. If "friday" is inside the query, check if it refers to the day of the week
    if "friday" in cleaned:
        # If it matches any day prepositions, it's a day of the week, NOT a wake word!
        is_day_of_week = any(re.search(prep, cleaned) for prep in DAY_PREPOSITIONS)
        if is_day_of_week:
            return False
            
    return False

def remove_wake_word(query: str) -> str:
    """
    Remove wake word from query while preserving the rest of the content.
    Returns empty string ONLY if the query is exactly a standalone wake word.
    """
    cleaned = query.strip()
    lower_query = cleaned.lower()
    
    # Regex patterns to match wake prefixes at the start, ignoring internal punctuation/spacing
    patterns = [
        r"^(wake\s+up\s+friday)\b",
        r"^(hello[,\s]+friday)\b",
        r"^(hey[,\s]+friday)\b",
        r"^(hi[,\s]+friday)\b",
        r"^(yo[,\s]+friday)\b",
        r"^(friday)\b",
    ]
    
    for pat in patterns:
        match = re.match(pat, lower_query)
        if match:
            matched_str = match.group(0)
            matched_len = len(matched_str)
            remaining = cleaned[matched_len:].strip()
            
            # Check if remaining string is just trailing punctuation or empty
            if not re.sub(r"[^\w\s]", "", remaining).strip():
                return ""
                
            # Strip leading separators/commas from remaining query
            remaining = re.sub(r"^[,\s;.\!?]+", "", remaining)
            return remaining.strip()
            
    return cleaned