"""
behavior_contract.py — FRIDAY Behavioral Contract Layer
======================================================
Manages independent behavioral, style, and communication preferences globally.
"""

from typing import Optional

class BehaviorContract:
    """
    Behavioral Contract Layer:
    Defines the standards for:
      - communication_style
      - response_structure
      - verbosity_preferences
      - explanation_preferences
      - reasoning_preferences
      - address_preferences
      
    The profile and active context influence this contract rather than replacing it.
    """

    def __init__(self):
        self.preferred_address = "Sir"
        self.default_verbosity = "concise"  # "concise" | "detailed"
        self.explanation_style = "first_principles"  # first-principles root-cause (how and why)
        self.reasoning_style = "evidence_based"
        self.tone = "Jarvis-style"  # premium, calm, quiet confidence, helpful companion

    def get_contract_directives(self, intent_vector: dict, overrides: dict, relevance_score: float, influence_weight: float) -> dict:
        """
        Dynamically adjusts behavioral directives based on query intent vector,
        relevance score, and explicit overrides.
        """
        directives = {
            "preferred_address": self.preferred_address,
            "verbosity": self.default_verbosity,
            "explanation_style": self.explanation_style,
            "reasoning_style": self.reasoning_style,
            "tone": self.tone
        }

        # 1. Address Preferences & Natural Flow
        if overrides.get("address") == "none":
            directives["preferred_address"] = ""
        
        # 2. Verbosity (Dynamic & Task-Dependent)
        # If the user explicitly asks for verbosity, or the intent is technical planning, coding, or debugging
        if overrides.get("verbosity") == "detailed":
            directives["verbosity"] = "detailed"
        elif overrides.get("verbosity") == "short":
            directives["verbosity"] = "short"
        elif intent_vector.get("debugging", 0.0) > 0.70 or intent_vector.get("planning", 0.0) > 0.70:
            # Coding, debugging, and systems planning mandate detailed explanations and code blocks
            directives["verbosity"] = "detailed"
        elif intent_vector.get("casual_chat", 0.0) > 0.80:
            directives["verbosity"] = "ultra_short"
            
        # 3. Explanation & Analogies (Suppress or focus based on overrides & domain)
        if overrides.get("domain") == "biology" or overrides.get("domain") == "history":
            directives["explanation_style"] = "native_discipline"
        elif intent_vector.get("explanation", 0.0) > 0.70 and influence_weight > 0.30:
            directives["explanation_style"] = "first_principles_technical"

        return directives

    def format_directives_prompt(self, directives: dict) -> str:
        """Assembles prompt-facing instructions from the active behavior contract."""
        prompt = "== BEHAVIORAL CONTRACT DIRECTIVES ==\n"
        
        # Salutation Rule (influences naturally, doesn't force prefix)
        if directives["preferred_address"]:
            prompt += f"- Preferred Address: Address the user as \"{directives['preferred_address']}\" (always capitalized) naturally, respectfully, and casually when appropriate (e.g. in greetings, key transitions, or statements). Do NOT force it as a mechanical prefix to every single sentence.\n"
        
        # Verbosity Rule
        verbosity = directives["verbosity"]
        if verbosity == "detailed":
            prompt += "- Verbosity: Provide a comprehensive, technically thorough, and detailed response. Include full complete code blocks, planning roadmaps, or structured architectural steps where applicable. No word limit.\n"
        elif verbosity == "short":
            prompt += "- Verbosity: Keep the response extremely brief, direct, and under 25 words. Cut all filler.\n"
        elif verbosity == "ultra_short":
            prompt += "- Verbosity: Keep the response to a single sentence (under 15 words) representing a warm, conversational transition.\n"
        else:
            prompt += "- Verbosity: Concise by default (typically 1 to 3 sentences, under 50 words), high signal, low fluff. Deliver the direct answer in the very first sentence.\n"
            
        # Explanation & Reasoning Style
        style = directives["explanation_style"]
        if style == "native_discipline":
            prompt += "- Explanation Style: Explain the concept strictly using its native academic terminology (e.g. biology, history). Do NOT introduce forced AI, software, or robotics analogies.\n"
        elif style == "first_principles_technical":
            prompt += "- Explanation Style: Explain concepts using a first-principles, root-cause perspective (the \"how\" and \"why\"). Feel free to draw analogies from engineering, software, robotics, space, or AI systems to clarify the concept.\n"
        else:
            prompt += "- Explanation Style: Factual, logical, evidence-based, and clear.\n"

        prompt += "- Tone: Premium Jarvis-style companion. Avoid corporate disclaimers, AI disclaimers, or robotic helper preambles.\n"
        prompt += "=====================================\n"
        return prompt
