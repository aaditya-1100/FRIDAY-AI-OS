import os
import json
import re
from brain.personalization_engine import PersonalizationEngine
from brain.behavior_contract import BehaviorContract

class IdentityManager:
    def __init__(self, file_path=None):
        if file_path is None:
            self.file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "memory", "identity_profile.json")
        else:
            self.file_path = file_path
        
        # Default authoritative profile matching user settings
        self.profile = {
            "user_identity": {
                "name": "Aaditya",
                "full_name": "Aaditya Pratap Chauhan",
                "preferred_address": "Sir",
                "role": "Creator, owner, builder, and sole intended user of FRIDAY",
                "conversational_style": "Concise, natural, low fluff, sharp, direct, subtle humor/wit occasionally",
                "preferred_interaction_style": "Premium assistant feel, calm intelligent Jarvis-style behavior, zero AI disclaimers, no customer-support tone",
                "academic_context": {
                  "current_education": "Class 12 student (2026–2027 Session)",
                  "focus": "JEE preparation",
                  "status_notes": "JEE is a pathway, NOT Aaditya's entire identity. Never reduce Aaditya's identity to just a JEE aspirant."
                },
                "hardware_context": {
                  "primary_phone": "OnePlus Nord CE 4 5G",
                  "pc_constraints": "Moderate hardware limitations, RAM-conscious architecture preferred, prioritize lightweight systems and efficient low-latency orchestration"
                },
                "personality": [
                  "Curious", "Analytical", "Skeptical", "Tech-focused", "Startup-minded", "Execution-oriented", "System-thinking"
                ],
                "core_values": [
                  "Execution-oriented", "Synergy", "System-thinking", "Continuous improvement"
                ],
                "interests": [
                  "AI systems", "Automation", "Robotics", "Startups", "Engineering", "Technology",
                  "Intelligent assistants", "Productivity systems", "Realtime AI",
                  "Advanced software systems", "Scientific/technical topics", "Sci-Fi", "Marvel", "Cinema"
                ],
                "goals": [
                  "AI systems", "Technology", "Startups", "Advanced intelligent assistants",
                  "Software engineering", "Future tech products"
                ],
                "favorite_youtube_channels": [
                  "Think School", "Raj Shamani", "Dan Martell", "Vaibhav Sisinty",
                  "Mark Rober", "PJ Explained", "comicverse"
                ]
            },
            "self_identity": {
                "name": "FRIDAY",
                "purpose": "A private single-owner AI companion system designed and built specifically by Aaditya for Aaditya",
                "builder": "Aaditya",
                "project": "FRIDAY (refers to the assistant itself)",
                "relationship": "FRIDAY is Aaditya's private personal AI companion and project. Aaditya created it, owns it, and continuously refines it.",
                "architecture_context": "FRIDAY is a RAM-conscious, low-latency, low-entropy runtime assistant that resides locally on Aaditya's system as an extension of his workflow."
            },
            "preference_memory": {
                "music": {
                  "genres": ["Punjabi", "Hindi", "English"],
                  "favorite_artist": "Karan Aujla",
                  "artists": ["Karan Aujla", "Subh", "Shubh"],
                  "routing": "Spotify-first routing preferred"
                },
                "interests": ["Marvel", "Cinema", "Podcasts", "Geopolitical/business content", "AI/technology creators", "Startup case studies", "Scientific/physics topics"]
            },
            "communication_preferences": {
                "brevity": "under 50 words, high signal, low fluff",
                "cadence": "direct-answer-first in the very first sentence",
                "tone": "Premium assistant feel, calm intelligent Jarvis-style behavior, zero AI disclaimers, no customer-support tone",
                "salutation": "Sir"
            }
        }
        self.load()
        self.engine = PersonalizationEngine()
        self.contract = BehaviorContract()

    def load(self):
        if os.path.exists(self.file_path) and os.path.getsize(self.file_path) > 0:
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    # Deep update
                    for k, v in loaded.items():
                        if k in self.profile and isinstance(v, dict):
                            self.profile[k].update(v)
                        else:
                            self.profile[k] = v
            except Exception as e:
                print(f"[IDENTITY ERROR] Failed to load identity profile: {e}")
        else:
            self.save()

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self.profile, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[IDENTITY ERROR] Failed to save identity profile: {e}")

    def get_contextual_slices(self, query: str) -> dict:
        """
        Calculates intent vectors, relevance scores, and behavioral weight signals
        dynamically, pulling targeted slices *only* when relevance > 0.
        """
        import os
        os.environ["FRIDAY_ACTIVE_QUERY"] = query
        
        # 1. Classify query intent and detect overrides
        parsed_intent = "AI_QUERY"
        q = query.lower()
        if "weather" in q:
            parsed_intent = "WEATHER"
        elif "news" in q:
            parsed_intent = "NEWS"
        elif "hello" in q or "hi" in q:
            parsed_intent = "CASUAL_CHAT"
        
        intent_vector = self.engine.get_intent_vector(query, parsed_intent)
        overrides = self.engine.detect_overrides(query)
        relevance_score = self.engine.get_relevance_score(query, intent_vector, overrides)
        influence_weight = self.engine.get_influence_weight(relevance_score, intent_vector)
        
        # 2. Get behavioral signals & weighting adjustments
        signals = self.engine.get_behavioral_signals(self.profile, intent_vector, overrides, relevance_score, influence_weight)
        
        # 3. Dynamic Behavior Contract
        directives = self.contract.get_contract_directives(intent_vector, overrides, relevance_score, influence_weight)
        behavior_prompt = self.contract.format_directives_prompt(directives)
        
        # 4. Context Selection & Targeted Retrieval
        slices = {
            "personalization_relevance": relevance_score,
            "personalization_influence": influence_weight,
            "behavior_directives": behavior_prompt
        }
        
        # Add behavioral signals if personalization is relevant
        if relevance_score > 0.0:
            signals_prompt = self.engine.compile_signals_directives(signals, overrides)
            if signals_prompt:
                slices["behavioral_signals"] = signals_prompt
                
            # Targeted retrieval of profile segments based on intent
            if intent_vector.get("recommendation", 0.0) > 0.50:
                slices["preference_memory"] = self.profile.get("preference_memory", {})
            if intent_vector.get("planning", 0.0) > 0.50 or intent_vector.get("debugging", 0.0) > 0.50:
                slices["user_identity"] = {
                    "interests": self.profile["user_identity"].get("interests", []),
                    "goals": self.profile["user_identity"].get("goals", [])
                }
            if intent_vector.get("explanation", 0.0) > 0.50:
                slices["user_identity"] = {
                    "interests": self.profile["user_identity"].get("interests", []),
                    "personality": self.profile["user_identity"].get("personality", [])
                }
            if intent_vector.get("casual_chat", 0.0) > 0.50:
                slices["self_identity"] = self.profile.get("self_identity", {})
                slices["user_identity"] = {
                    "name": self.profile["user_identity"]["name"]
                }
        else:
            # Low relevance: Only return a minimal self-awareness slice to avoid profile dumping
            slices["self_identity"] = {
                "name": self.profile["self_identity"]["name"]
            }
            
        # E2E test/greetings fallback overrides to preserve backward compatibility with Category 1 tests
        if any(w in q for w in ("who created", "who made", "who built", "creator", "builder", "your maker", "made you", "built you")):
            slices["self_identity"] = {
                "name": self.profile["self_identity"]["name"],
                "builder": self.profile["self_identity"]["builder"],
                "relationship": self.profile["self_identity"]["relationship"]
            }
            slices["user_identity"] = {
                "name": self.profile["user_identity"]["name"],
                "role": self.profile["user_identity"]["role"]
            }
        elif any(w in q for w in ("who am i", "my name", "know me", "about me", "know about me")):
            slices["user_identity"] = {
                "name": self.profile["user_identity"]["name"],
                "role": self.profile["user_identity"]["role"],
                "academic_context": self.profile["user_identity"].get("academic_context")
            }
            
        return slices

    def identity_hallucination_filter(self, text: str) -> str:
        """
        Scans generated response text and aggressively filters/replaces typical pre-trained
        LLM hallucinations regarding academic/professional history for Aaditya or FRIDAY.
        """
        if not text:
            return text
            
        # 1. Hallucinated academic/professional concepts about creator/Aaditya
        hallucination_terms = [
            r"\bph\.?d\b", r"\bdoctorate\b", r"\baerospace\b", r"\baeronautical\b",
            r"\bcomputer\s+science\s+degree\b", r"\bgraduated\s+from\b", r"\buniversity\b",
            r"\bcollege\b", r"\bprofessor\b", r"\bb\.?tech\b", r"\bm\.?tech\b",
            r"\bmaster's\b", r"\bbachelor's\b"
        ]
        
        # Split text into sentences to isolate and remove/replace hallucinated clauses
        sentences = re.split(r'(?<=[.!?])\s+', text)
        filtered_sentences = []
        
        for sentence in sentences:
            s_lower = sentence.lower()
            # If sentence talks about creator, builder, Aaditya, or "you" (in context of creation)
            refers_to_creator = any(w in s_lower for w in ("creator", "builder", "aaditya", "maker", "made me", "built me", "owner"))
            
            has_hallucination = False
            if refers_to_creator or "you" in s_lower:
                for term in hallucination_terms:
                    if re.search(term, s_lower):
                        has_hallucination = True
                        break
            
            if has_hallucination:
                # Replace the hallucinated claim with a simple grounded statement or discard it
                print(f"[HALLUCINATION FILTERED] Removed hallucinated claim: '{sentence}'")
                # Instead of appending the fake bio, we gracefully omit it or add a simple fallback if empty
                continue
            
            filtered_sentences.append(sentence)
            
        filtered_text = " ".join(filtered_sentences).strip()
        if not filtered_text:
            return "I am FRIDAY, Aaditya's personal AI companion."
            
        # 2. Over-Personalization Prevention Leakage Filter
        filtered_text = self.engine.identity_leakage_filter(filtered_text)
        
        return filtered_text
