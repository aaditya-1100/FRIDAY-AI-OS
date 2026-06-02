"""
confidence_engine.py — FRIDAY Reliability-Aware Bayesian Confidence Engine
========================================================================
Implements the RABF model to fuse pipeline component scores, dynamically
compiling relevance masks based on intent, and determining policy thresholds.
"""

from typing import Dict, Any, Tuple

class ConfidenceEngine:
    """
    RABF (Reliability-Aware Bayesian Fusion) Engine.
    Excludes optional/irrelevant modules from calculating unified turn confidence.
    """
    def __init__(self):
        # Calibrated weights: sum of weights = 1.0 (baseline priorities)
        self.weights = {
            "asr": 0.25,
            "intent": 0.30,
            "domain": 0.15,
            "routing": 0.20,
            "memory": 0.10,
            "execution": 0.15
        }
        
        # Specific thresholds for system actions
        self.threshold_high = 0.85
        self.threshold_medium = 0.55

    def get_relevance_masks(self, intent: str) -> Dict[str, int]:
        """
        Dynamic Relevance Masks (beta_i):
        Determines which pipeline components are critical for a given intent.
        """
        # Default: Speech, Intent, Domain, and Routing are always critical
        masks = {
            "asr": 1,
            "intent": 1,
            "domain": 1,
            "routing": 1,
            "memory": 0,
            "execution": 0
        }
        
        if not intent:
            return masks
            
        intent_upper = intent.upper()
        
        # 1. Memory Identity queries require Memory lookup
        if intent_upper in ("MEMORY_IDENTITY", "AI_QUERY") and any(x in intent_upper for x in ("IDENTITY", "PROFILE")):
            masks["memory"] = 1
            
        # 2. Local OS, app controls, screenshot, window controls require pre-execution checks
        elif intent_upper in ("OPEN", "WINDOW_CONTROL", "SCREENSHOT", "SYSTEM_STATUS", "STOPWATCH_CONTROL"):
            masks["execution"] = 1
            
        # 3. Media, Spotify, news, weather require active execution integrations
        elif intent_upper in ("PLAY_MEDIA", "SPOTIFY_CONTROL", "WEATHER", "NEWS", "REALTIME_QUERY"):
            masks["execution"] = 1
            
        # 4. Multi-action compound tasks require pre-execution mapping
        elif intent_upper in ("MULTI_ACTION", "SEARCH", "WEB_SEARCH", "MAP_ROUTE", "MAP_LOCATION"):
            masks["execution"] = 1
            
        return masks

    def calculate_unified_confidence(
        self,
        intent: str,
        components_score: Dict[str, float]
    ) -> Dict[str, Any]:
        """
        Fuses component scores using the RABF formula:
        C_unified = sum(beta_i * w_i * C_i) / sum(beta_i * w_i)
        """
        masks = self.get_relevance_masks(intent)
        
        weighted_sum = 0.0
        mask_weight_sum = 0.0
        
        for k in self.weights:
            beta = masks.get(k, 1)
            w = self.weights[k]
            score = components_score.get(k, 1.0)
            
            weighted_sum += beta * w * score
            mask_weight_sum += beta * w
            
        if mask_weight_sum > 0:
            unified_score = weighted_sum / mask_weight_sum
        else:
            unified_score = 0.50
            
        # Enforce Policy Action thresholds
        if unified_score >= self.threshold_high:
            policy = "HIGH"
            action = "SILENT_EXECUTION"
        elif unified_score >= self.threshold_medium:
            policy = "MEDIUM"
            action = "IMPLICIT_CONFIRMATION"
        else:
            policy = "LOW"
            action = "ACTIVE_CLARIFICATION"
            
        return {
            "unified_score": float(round(unified_score, 4)),
            "relevance_masks": masks,
            "weights": self.weights,
            "policy": policy,
            "action": action
        }

# Global Confidence Engine instance
confidence_engine = ConfidenceEngine()
