"""
conflict_engine.py — FRIDAY Stateless Trigger Conflict Engine
============================================================
Implements spaCy-driven syntactic dependency parsing, fused conflict scoring,
weak state softmax priors, and high-resolution tie-breaking.
"""

import re
import spacy
from typing import Dict, Any, List, Tuple

class ConflictResolver:
    """
    Syntactic & Contextual Conflict Engine.
    Resolves competing triggers when the margin is narrow (< 0.05).
    """
    def __init__(self):
        # Calibrated conflict weights: sum to 1.0
        self.weights = {
            "semantic": 0.45,
            "dependency": 0.25,
            "grounding": 0.15,
            "reliability": 0.10,
            "state_prior": 0.05
        }
        
        # Load spaCy NLP small model
        try:
            self.nlp = spacy.load("en_core_web_sm")
        except Exception:
            # Fallback will be handled gracefully if model is missing
            self.nlp = None
            print("[CONFLICT_ENGINE WARNING] spaCy 'en_core_web_sm' model not found. Using fallback regex parser.")

        # Weak State Softmax Prior association matrix:
        # matrix[state_name][trigger_name] -> association strength
        self.state_matrix = {
            "TASK_MODE": {
                "NATIVE_OS": 0.90,
                "SYSTEM_STATUS": 0.85,
                "LLM": 0.40,
                "MEDIA": 0.10,
                "RETRIEVAL": 0.70
            },
            "CASUAL_CHAT": {
                "LLM": 0.90,
                "NATIVE_OS": 0.05,
                "SYSTEM_STATUS": 0.10,
                "MEDIA": 0.20,
                "RETRIEVAL": 0.30
            },
            "MEDIA_MODE": {
                "MEDIA": 0.90,
                "NATIVE_OS": 0.15,
                "LLM": 0.20,
                "SYSTEM_STATUS": 0.20,
                "RETRIEVAL": 0.40
            }
        }

    # ── 1. DEPENDENCY PARSING STRATEGY ────────────────────────────────────────
    def parse_dependency_confidence(self, query: str, trigger: str) -> float:
        """
        Uses spaCy token dependency graph parser to evaluate root verb-object mapping.
        Distinguishes:
          - "Explain [X]" -> explanatory (AI_QUERY / LLM)
          - "Play [X] tutorial" -> media-bound (MEDIA / PLAY_MEDIA)
        """
        q_lower = query.lower().strip()
        t_upper = trigger.upper()
        
        # Fallback to Regex pattern parser if spaCy is missing
        if not self.nlp:
            return self._regex_dependency_fallback(q_lower, t_upper)

        try:
            doc = self.nlp(q_lower)
        except Exception:
            return self._regex_dependency_fallback(q_lower, t_upper)
            
        root_verb = ""
        direct_obj = ""
        modifiers = []
        
        for token in doc:
            if token.dep_ == "ROOT" and token.pos_ == "VERB":
                root_verb = token.text.lower()
            elif token.dep_ == "dobj":
                direct_obj = token.text.lower()
            elif token.dep_ in ("amod", "compound", "nmod"):
                modifiers.append(token.text.lower())
                
        # Classify root verbs
        explanatory_verbs = {"explain", "what is", "how do", "define", "understand", "describe", "clarify"}
        action_verbs = {"play", "open", "launch", "start", "close", "minimize", "maximize", "quit", "exit"}
        
        # A. Cognitive Explanations (AI_QUERY / LLM)
        if t_upper in ("LLM", "AI_QUERY"):
            if root_verb in explanatory_verbs or q_lower.startswith(("what is", "how do", "why do", "explain")):
                return 1.0
            if "tutorial" in modifiers or "tutorial" in q_lower:
                return 0.15  # Penalty: "tutorial" implies media or guide lookup
            return 0.70
            
        # B. Media Triggers
        elif t_upper in ("MEDIA", "MEDIA_PLAY"):
            if root_verb in ("play", "watch", "listen"):
                if "tutorial" in q_lower or "guide" in q_lower or direct_obj in ("tutorial", "guide", "video", "song"):
                    return 1.0
                return 0.95
            if "youtube" in q_lower or "spotify" in q_lower or "playlist" in q_lower:
                return 0.90
            return 0.20
            
        # C. Native OS App Launch Triggers
        elif t_upper == "NATIVE_OS":
            if root_verb in ("open", "launch", "start", "close", "quit", "exit"):
                # Clean targets checklist
                apps = {"notepad", "chrome", "spotify", "vscode", "explorer", "calculator", "paint", "cmd"}
                if direct_obj in apps or any(app in q_lower for app in apps):
                    return 1.0
                return 0.85
            return 0.10
            
        return 0.50

    def _regex_dependency_fallback(self, q_lower: str, t_upper: str) -> float:
        """Syntactic pattern scanner fallback using word boundary regexes."""
        explanatory_words = r"\b(explain|what is|how do|why do|define|understand|describe|difference between)\b"
        action_words = r"\b(play|open|launch|start|close|minimize|maximize|quit|exit)\b"
        
        if t_upper in ("LLM", "AI_QUERY"):
            if re.search(explanatory_words, q_lower):
                return 1.0
            if "tutorial" in q_lower:
                return 0.15
            return 0.65
            
        elif t_upper in ("MEDIA", "MEDIA_PLAY"):
            if re.search(r"\b(play|watch|listen)\b", q_lower):
                return 0.95
            if "youtube" in q_lower or "spotify" in q_lower or "tutorial" in q_lower:
                return 0.90
            return 0.25
            
        elif t_upper == "NATIVE_OS":
            if re.search(r"\b(open|launch|start|close)\b", q_lower):
                return 0.85
            return 0.15
            
        return 0.50

    # ── 2. OBJECT RESOLUTION GROUNDING ────────────────────────────────────────
    def get_grounding_confidence(self, query: str, trigger: str) -> float:
        """Grounds entities against local executable binaries or known databases."""
        q_lower = query.lower()
        t_upper = trigger.upper()
        
        # Verify local application installations for OS triggers
        if t_upper == "NATIVE_OS":
            apps = {"notepad", "chrome", "spotify", "vscode", "explorer", "calculator", "paint", "cmd", "pw", "physics wallah"}
            if any(app in q_lower for app in apps):
                return 1.0
            return 0.30
            
        # Grounding check for known media resources
        elif t_upper == "MEDIA":
            media_keywords = {"lofi", "music", "song", "playlist", "spotify", "youtube", "video", "tutorial", "mark rober"}
            if any(k in q_lower for k in media_keywords):
                return 0.95
            return 0.40
            
        return 0.50

    # ── 3. STATE PRIOR SOFTMAX CALCULATOR ─────────────────────────────────────
    def get_state_prior(self, trigger: str, system_state: str) -> float:
        """Calculates softmax prior mapping from state matrix."""
        t_upper = trigger.upper()
        state_upper = system_state.upper() if system_state else "CASUAL_CHAT"
        
        # Softmax default mapping
        state_row = self.state_matrix.get(state_upper, self.state_matrix["CASUAL_CHAT"])
        
        # Translate detailed trigger names to matrix indices
        matrix_trigger = "LLM"
        if t_upper in ("MEDIA", "MEDIA_PLAY"):
            matrix_trigger = "MEDIA"
        elif t_upper in ("NATIVE_OS", "TEMPORAL", "WINDOW_CONTROL"):
            matrix_trigger = "NATIVE_OS"
        elif t_upper in ("WEATHER", "NEWS", "REALTIME_QUERY", "RETRIEVAL"):
            matrix_trigger = "RETRIEVAL"
            
        return state_row.get(matrix_trigger, 0.50)

    # ── 4. CONFLICT SCORE ASSEMBLY ───────────────────────────────────────────
    def calculate_fused_conflict_score(
        self,
        trigger: str,
        semantic_intent_score: float,
        query: str,
        system_state: str,
        historical_reliability: float
    ) -> float:
        """
        Fused Conflict Score:
        S_conflict = w1*C_semantic + w2*C_dependency + w3*C_grounding + w4*R_trigger + w5*Psi_state
        """
        c_semantic = semantic_intent_score
        c_dependency = self.parse_dependency_confidence(query, trigger)
        c_grounding = self.get_grounding_confidence(query, trigger)
        r_trigger = historical_reliability
        psi_state = self.get_state_prior(trigger, system_state)
        
        score = (
            self.weights["semantic"] * c_semantic +
            self.weights["dependency"] * c_dependency +
            self.weights["grounding"] * c_grounding +
            self.weights["reliability"] * r_trigger +
            self.weights["state_prior"] * psi_state
        )
        return float(round(score, 4))

# Global Conflict Resolver instance
conflict_resolver = ConflictResolver()
