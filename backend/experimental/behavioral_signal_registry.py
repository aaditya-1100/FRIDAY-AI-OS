"""
behavioral_signal_registry.py — FRIDAY Behavioral Signal Registry & Fusion Engine
=============================================================================
Compiles static and active signals from Identity Profiles and dynamic contexts.
Implements Section 7's weighted fusion, confidence propagation, and decay.
"""

import time
import numpy as np

class BehavioralSignalRegistry:
    def __init__(self):
        # Default source weights: w_j where sum(w_j) = 1.0
        self.source_weights = {
            "profile": 0.60,
            "observed": 0.20,
            "conversation": 0.15,
            "task": 0.05
        }
        self.conflict_stiffness = 2.0  # beta parameter
        
        # Taxonomy lists for signal compilation
        self.signals_taxonomy = [
            # 1. Communication Signals
            "brevity_preference", "directness_preference", "verbosity_tolerance", "technical_depth_preference",
            # 2. Reasoning Signals
            "root_cause_preference", "systems_thinking_preference", "causal_reasoning_preference", "evidence_preference",
            # 3. Explanation Signals
            "analogy_preference", "engineering_example_preference", "technology_example_preference",
            # 4. Planning Signals
            "execution_preference", "actionability_preference", "long_term_thinking_preference",
            # 5. Decision Signals
            "tradeoff_visibility_preference", "risk_awareness_preference", "objective_reasoning_preference",
            # 6. Context Signals
            "project_resolution_bias", "assistant_resolution_bias", "context_continuity_preference"
        ]

    def extract_profile_baselines(self, profile: dict) -> dict[str, dict]:
        """
        Translates raw Identity Profile fields (UserIdentityModel, AssistantIdentityModel,
        RelationshipContextModel) into standardized, strength-calibrated profile signals.
        """
        baselines = {}
        for sig in self.signals_taxonomy:
            baselines[sig] = {"strength": 0.50, "confidence": 0.50}

        # 1. Extraction from user identity communication preferences
        comm_pref = profile.get("communication_preferences", {})
        brevity_text = str(comm_pref.get("brevity", "")).lower()
        if "under 50 words" in brevity_text or "concise" in brevity_text:
            baselines["brevity_preference"] = {"strength": 0.95, "confidence": 0.95}
            baselines["verbosity_tolerance"] = {"strength": 0.25, "confidence": 0.90}
            
        cadence_text = str(comm_pref.get("cadence", "")).lower()
        if "direct-answer-first" in cadence_text or "direct" in cadence_text:
            baselines["directness_preference"] = {"strength": 0.90, "confidence": 0.95}

        # 2. Extraction from personality and core values
        user_id = profile.get("user_identity", {})
        personality = [p.lower() for p in user_id.get("personality", [])]
        values = [v.lower() for v in user_id.get("core_values", [])]
        goals = [g.lower() for g in user_id.get("goals", [])]

        if "analytical" in personality or "skeptical" in personality:
            baselines["root_cause_preference"] = {"strength": 0.90, "confidence": 0.90}
            baselines["evidence_preference"] = {"strength": 0.90, "confidence": 0.85}
            baselines["objective_reasoning_preference"] = {"strength": 0.90, "confidence": 0.90}
            
        if "system-thinking" in personality or "system-thinking" in values:
            baselines["systems_thinking_preference"] = {"strength": 0.95, "confidence": 0.95}
            baselines["causal_reasoning_preference"] = {"strength": 0.85, "confidence": 0.85}
            
        if "execution-oriented" in personality or "execution-oriented" in values:
            baselines["actionability_preference"] = {"strength": 0.95, "confidence": 0.95}
            baselines["execution_preference"] = {"strength": 0.90, "confidence": 0.90}

        if "software engineering" in goals or "technology" in goals:
            baselines["engineering_example_preference"] = {"strength": 0.85, "confidence": 0.85}
            baselines["technical_depth_preference"] = {"strength": 0.85, "confidence": 0.85}
            baselines["project_resolution_bias"] = {"strength": 0.90, "confidence": 0.90}

        # 3. Analogy preference maps inversely to high technical profile
        if baselines["technical_depth_preference"]["strength"] > 0.70:
            baselines["analogy_preference"] = {"strength": 0.35, "confidence": 0.80}

        # 4. Planning milestones
        baselines["long_term_thinking_preference"] = {"strength": 0.80, "confidence": 0.80}
        baselines["tradeoff_visibility_preference"] = {"strength": 0.95, "confidence": 0.95}
        baselines["risk_awareness_preference"] = {"strength": 0.90, "confidence": 0.90}
        baselines["context_continuity_preference"] = {"strength": 0.90, "confidence": 0.90}

        return baselines

    def fuse_signals(self, profile_signals: dict, observed: dict = None, conversation: dict = None, task: dict = None) -> dict[str, dict]:
        """
        Signal Fusion Engine: Implements Section 7's weighted fusion,
        confidence propagation with conflict penalty, and signal compiling.
        """
        fused = {}
        obs = observed or {}
        conv = conversation or {}
        tsk = task or {}
        
        sources = {
            "profile": (profile_signals, self.source_weights["profile"]),
            "observed": (obs, self.source_weights["observed"]),
            "conversation": (conv, self.source_weights["conversation"]),
            "task": (tsk, self.source_weights["task"])
        }
        
        for sig in self.signals_taxonomy:
            values = []
            confidences = []
            weights = []
            
            for src_name, (src_data, src_w) in sources.items():
                if sig in src_data:
                    item = src_data[sig]
                    # Support both dict style and plain floats
                    if isinstance(item, dict):
                        val = item.get("strength", 0.50)
                        conf = item.get("confidence", 0.50)
                    else:
                        val = float(item)
                        conf = 0.50
                    
                    values.append(val)
                    confidences.append(conf)
                    weights.append(src_w)
            
            if not values:
                # Fallback to default
                fused[sig] = {
                    "signal_name": sig,
                    "strength": 0.50,
                    "confidence": 0.50,
                    "source": "fusion_fallback"
                }
                continue
                
            # Convert lists to numpy arrays for vectorized calculations
            x = np.array(values)
            c = np.array(confidences)
            w = np.array(weights)
            
            # 1. Fused Strength: weighted confidence average
            denom_strength = np.sum(w * c)
            if denom_strength > 0:
                fused_strength = float(np.sum(w * c * x) / denom_strength)
            else:
                fused_strength = 0.50
                
            # 2. Fused Confidence with Conflict Penalty
            denom_conf = np.sum(w)
            c_base = float(np.sum(w * c) / denom_conf) if denom_conf > 0 else 0.50
            
            # Weighted variance of strengths
            if denom_strength > 0:
                variance = float(np.sum(w * c * (x - fused_strength)**2) / denom_strength)
            else:
                variance = 0.0
                
            fused_conf = max(0.0, c_base * (1.0 - self.conflict_stiffness * variance))
            
            fused[sig] = {
                "signal_name": sig,
                "strength": float(np.clip(fused_strength, 0.0, 1.0)),
                "confidence": float(np.clip(fused_conf, 0.0, 1.0)),
                "source": "fusion_layer",
                "last_updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }
            
        return fused
