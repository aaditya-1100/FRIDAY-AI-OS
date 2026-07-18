"""
spacy_loader.py — Unified spaCy model loading cache
===================================================
Prevents multiple processes/modules from loading en_core_web_sm independently,
saving significant RAM and cold-start/warm-start latency.
"""
import spacy

_nlp_model = None

def get_spacy_model():
    """Returns a cached, single instance of the spaCy model."""
    global _nlp_model
    if _nlp_model is None:
        try:
            print("[SPACY_LOADER] Loading spaCy 'en_core_web_sm' model...")
            _nlp_model = spacy.load("en_core_web_sm")
            print("[SPACY_LOADER] spaCy model loaded successfully.")
        except Exception as e:
            print(f"[SPACY_LOADER WARNING] Failed to load 'en_core_web_sm': {e}")
            _nlp_model = None
    return _nlp_model
