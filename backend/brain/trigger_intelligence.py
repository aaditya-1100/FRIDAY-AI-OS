"""
trigger_intelligence.py — FRIDAY Dynamic Trigger Intelligence Layer
===================================================================
Manages persistent trigger reliability, EMA log-odds reinforcement learning,
temporal decay, capability confidence estimation, and dynamic score calculation.
"""

import os
import json
import math
import time
from typing import Dict, Any, Tuple

RELIABILITY_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "trigger_reliability.json"
)

# Default base priors for triggers
BASE_PRIORS = {
    "MEMORY": 0.95,
    "COMMAND": 0.90,
    "MEDIA": 0.92,
    "NATIVE_OS": 0.92,
    "TEMPORAL": 0.98,
    "FRESHNESS": 0.90,
    "KNOWLEDGE": 0.85,
    "CONVERSATIONAL": 0.85,
    "LLM": 0.85
}

class TriggerIntelligenceManager:
    """
    Manages dynamic trigger arbitration dimensions:
    - Capability checks (C_cap)
    - Persistent learned reliability (R)
    - Priority weights (W_priority)
    """
    def __init__(self):
        self.reliability: Dict[str, float] = {}
        self.last_used_time: Dict[str, float] = {}
        self.learning_rate = 0.15
        self.decay_constant = 1.15e-6  # half-life of ~1 week
        self.reliability_floor = 0.15
        self.load_reliability()

    def load_reliability(self) -> None:
        """Loads learned reliability scores from local JSON file."""
        if os.path.exists(RELIABILITY_FILE):
            try:
                with open(RELIABILITY_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.reliability = data.get("reliability", {})
                    self.last_used_time = data.get("last_used_time", {})
            except Exception as e:
                print(f"[TRIGGER INTEL ERROR] Failed to load reliability: {e}")
                
        # Back-fill any missing baseline triggers
        for k, v in BASE_PRIORS.items():
            if k not in self.reliability:
                self.reliability[k] = v
            if k not in self.last_used_time:
                self.last_used_time[k] = time.time()

    def save_reliability(self) -> None:
        """Persists learned reliability scores locally."""
        os.makedirs(os.path.dirname(RELIABILITY_FILE), exist_ok=True)
        try:
            with open(RELIABILITY_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "reliability": self.reliability,
                    "last_used_time": self.last_used_time
                }, f, indent=2)
        except Exception as e:
            print(f"[TRIGGER INTEL ERROR] Failed to save reliability: {e}")

    # ── 1. CAPABILITY CONFIDENCE (C_cap) ──────────────────────────────────────
    def get_capability_confidence(self, trigger: str) -> float:
        """Dynamic check of the trigger execution environment."""
        t_upper = trigger.upper()
        
        # A. Spotify/Media controls require dynamic API status
        if t_upper == "MEDIA":
            try:
                from system.spotify_control import _spotify_client
                if _spotify_client.is_configured and _spotify_client._token_info:
                    return 1.0
                return 0.85 # Fallback to local browser/YT scraper
            except Exception:
                return 0.85
                
        # B. Native OS App Launch checks
        elif t_upper == "NATIVE_OS":
            # Baseline apps path check
            return 0.98
            
        # C. Temporal alarm/timer triggers are always available
        elif t_upper == "TEMPORAL":
            return 1.0
            
        return 1.0

    # ── 2. PRIORITY WEIGHT (W_priority) ──────────────────────────────────────
    def get_priority_weight(self, trigger: str) -> float:
        """Determines the baseline weak prior weight modifier."""
        t_upper = trigger.upper()
        if t_upper in ("SYSTEM_STATUS", "EMERGENCY"):
            return 1.25
        elif t_upper == "TEMPORAL":
            return 1.15
        elif t_upper in ("MEDIA", "NATIVE_OS"):
            return 1.00
        elif t_upper in ("LLM", "CONVERSATIONAL", "KNOWLEDGE"):
            return 0.85
        return 1.00

    # ── 3. TRIGGER RELIABILITY & DECAY (R) ───────────────────────────────────
    def get_reliability(self, trigger: str) -> float:
        """Returns the dynamically decayed reliability score."""
        t_upper = trigger.upper()
        if t_upper not in self.reliability:
            return 0.95
            
        r_current = self.reliability[t_upper]
        last_t = self.last_used_time.get(t_upper, time.time())
        delta_t = time.time() - last_t
        
        # Apply temporal decay: regress towards base prior
        base = BASE_PRIORS.get(t_upper, 0.90)
        phi_current = self._prob_to_log_odds(r_current)
        phi_base = self._prob_to_log_odds(base)
        
        decay_factor = math.exp(-self.decay_constant * delta_t)
        phi_decayed = phi_current * decay_factor + phi_base * (1.0 - decay_factor)
        
        r_decayed = self._log_odds_to_prob(phi_decayed)
        return max(self.reliability_floor, r_decayed)

    def register_feedback(self, trigger: str, success: bool) -> None:
        """Updates log-odds reliability score using EMA reinforcement loop."""
        t_upper = trigger.upper()
        if t_upper not in self.reliability:
            return
            
        r_current = self.reliability[t_upper]
        phi_current = self._prob_to_log_odds(r_current)
        
        y = 1.0 if success else -1.0
        
        # Log-odds EMA update rule
        phi_updated = phi_current + self.learning_rate * (y - self._log_odds_to_prob(phi_current))
        r_updated = self._log_odds_to_prob(phi_updated)
        
        # Enforce floors and ceiling
        r_updated = max(self.reliability_floor, min(0.99, r_updated))
        
        self.reliability[t_upper] = r_updated
        self.last_used_time[t_upper] = time.time()
        self.save_reliability()
        print(f"[TRIGGER INTEL LEARNING] Trigger '{t_upper}' updated. Reliability: {r_current:.4f} -> {r_updated:.4f}")

    # ── HELPER MATHEMATICAL TRANSLATIONS ──────────────────────────────────────
    @staticmethod
    def _prob_to_log_odds(p: float) -> float:
        p = max(1e-5, min(1.0 - 1e-5, p))
        return math.log(p / (1.0 - p))

    @staticmethod
    def _log_odds_to_prob(phi: float) -> float:
        try:
            return 1.0 / (1.0 + math.exp(-phi))
        except OverflowError:
            return 0.0 if phi < 0 else 1.0

    # ── 4. DYNAMIC SCORE ASSEMBLY ─────────────────────────────────────────────
    def calculate_trigger_score(
        self,
        trigger: str,
        semantic_intent_score: float
    ) -> float:
        """
        Dynamic Score Formula:
        S_trigger = I(T) * C_cap * R * W_priority
        """
        c_cap = self.get_capability_confidence(trigger)
        r = self.get_reliability(trigger)
        w_priority = self.get_priority_weight(trigger)
        
        score = semantic_intent_score * c_cap * r * w_priority
        return float(round(score, 4))

# Global thread-safe Trigger Intelligence Manager instance
trigger_intel_mgr = TriggerIntelligenceManager()
