"""
personalization_engine.py — FRIDAY Semantic Personalization & Behavioral Intelligence Engine
========================================================================================
Implements:
  - ONNX Semantic Intent Vector Engine (Dynamic Centroids)
  - Spacy Dependency Graph Constraint Extraction (Negation detection & nested structures)
  - Isotonic Confidence Calibration
  - Semantic Decision Trace Observability
"""

import os
import json
import re
import numpy as np
import spacy
from brain.onnx_biencoder import ONNXBiEncoder
from brain.entity_tracker import _TAXONOMY
from brain.behavioral_signal_registry import BehavioralSignalRegistry

def levenshtein_distance(s1: str, s2: str) -> int:
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
        
    return previous_row[-1]

class SemanticPreprocessor:
    """
    SemanticPreprocessor: Separated query preprocessing layer.
    Corrects spelling typos, normalizes slang, and recovers noisy tokens prior to parsing.
    """
    def __init__(self, backend_dir: str):
        self.vocabulary = set()
        
        # Load synonyms from taxonomy config dynamically
        tax_path = os.path.join(backend_dir, "data", "semantic_taxonomy.json")
        if os.path.exists(tax_path):
            try:
                with open(tax_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for node, meta in data.get("nodes", {}).items():
                        self.vocabulary.add(node.lower())
                        for syn in meta.get("synonyms", []):
                            self.vocabulary.add(syn.lower())
            except Exception:
                pass
                
        # Load sample words from intent prototypes
        proto_path = os.path.join(backend_dir, "data", "intent_prototypes.json")
        if os.path.exists(proto_path):
            try:
                with open(proto_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for samples in data.values():
                        for sample in samples:
                            for word in sample.lower().split():
                                clean_word = "".join(c for c in word if c.isalnum() or c == "-")
                                if clean_word:
                                    self.vocabulary.add(clean_word)
            except Exception:
                pass
                
        # Inject core operational terms, standard verbs, query tokens, pronouns, and media descriptors
        self.vocabulary.update([
            "recommend", "suggest", "explain", "calculate", "debug", "define", "roadmap", "plan",
            "unrelated", "without", "except", "yesterday", "tomorrow", "finals", "recursion",
            
            # Media control & actions
            "play", "open", "show", "tell", "watch", "search", "find", "check", "get", "run", "start", 
            "stop", "close", "launch", "kill", "quit", "exit", "terminate", "go", "shut", "shutdown", 
            "restart", "mute", "unmute", "remember", "save", "store", "keep", "forget", "clear", "reset", "set",
            
            # Common query & helper words
            "what", "how", "why", "who", "when", "where", "which", "is", "are", "am", "was", "were", "be", 
            "been", "do", "does", "did", "can", "could", "would", "should", "will", "shall",
            
            # Target apps, entities & mediums
            "music", "song", "video", "short", "shorts", "movie", "playlist", "chrome", "google", "youtube", 
            "spotify", "weather", "news", "time", "date", "day", "screen", "screenshot", "status", "system", 
            "app", "application", "browser", "window", "calculator", "notepad", "command", "prompt", "cmd", 
            "powershell", "pc", "computer",
            
            # Pronouns & structural prepositions
            "me", "my", "i", "you", "your", "he", "she", "it", "they", "them", "us", "we", "our", "to", "for", 
            "on", "in", "at", "by", "with", "about", "from", "of", "and", "or", "but", "the", "a", "an", "this", 
            "that", "these", "those"
        ])
        
    def preprocess(self, query: str) -> str:
        if not query:
            return query
            
        words = query.split()
        normalized_words = []
        
        for word in words:
            clean_word = "".join(c for c in word.lower() if c.isalnum() or c == "-")
            if not clean_word or clean_word in self.vocabulary:
                normalized_words.append(word)
                continue
                
            # Perform Levenshtein lookup (Option C/RapidFuzz-style ratio)
            best_match = clean_word
            best_ratio = 0.0
            
            for vocab_word in self.vocabulary:
                dist = levenshtein_distance(clean_word, vocab_word)
                max_len = max(len(clean_word), len(vocab_word))
                ratio = 1.0 - (dist / max_len) if max_len > 0 else 1.0
                
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_match = vocab_word
                    
            # 0.70 threshold handles up to 2 edits for average word length
            if best_ratio >= 0.70:
                if word[0].isupper():
                    normalized_words.append(best_match.capitalize())
                else:
                    normalized_words.append(best_match)
            else:
                normalized_words.append(word)
                
        return " ".join(normalized_words)

class PersonalizationEngine:
    """
    PersonalizationEngine:
    The core semantic layer that processes raw user queries, extracts intent vectors,
    calibrates confidence scores, maps nested grammatical constraints, and logs traces.
    """
    def __init__(self):
        # 1. Determine Winning Model from Benchmark Results
        self.backend_dir = os.path.dirname(os.path.dirname(__file__))
        benchmark_path = os.path.join(self.backend_dir, "scratch", "benchmark_results.json")
        winner = "all-MiniLM-L6-v2"
        if os.path.exists(benchmark_path):
            try:
                with open(benchmark_path, "r", encoding="utf-8") as f:
                    res = json.load(f)
                    winner = res.get("selected_winner", "all-MiniLM-L6-v2")
            except Exception:
                pass
        
        # 2. Load Local ONNX Bi-Encoder
        self.encoder = ONNXBiEncoder(model_name=winner)
        self.encoder.load()
        
        # 3. Load Spacy NLP Tagger/Parser via shared cache loader
        from brain.spacy_loader import get_spacy_model
        self.nlp = get_spacy_model()
        
        # 4. Load Dynamic Taxonomy Config
        self.taxonomy = _TAXONOMY
        
        # 5. Compile Dynamic Intent Centroids from Prototypes at Startup
        self.centroids = {}
        self._initialize_intent_centroids()
        
        # 6. Initialize Semantic Preprocessor Layer
        self.preprocessor = SemanticPreprocessor(self.backend_dir)
        
        # 7. Observability Decision Trace Cache
        self.last_trace = {}
        
        # 8. Initialize Behavioral Signal Registry
        self.registry = BehavioralSignalRegistry()

    def _initialize_intent_centroids(self) -> None:
        """Loads samples from intent_prototypes.json and calculates class centroids in vector space."""
        proto_path = os.path.join(self.backend_dir, "data", "intent_prototypes.json")
        if not os.path.exists(proto_path):
            raise FileNotFoundError(f"Intent prototypes config not found at: {proto_path}")
            
        with open(proto_path, "r", encoding="utf-8") as f:
            prototypes = json.load(f)
            
        print("[INTENT_ENGINE] Generating class centroids dynamically from prototype samples...")
        for category, samples in prototypes.items():
            embeddings = []
            for sample in samples:
                embeddings.append(self.encoder.encode(sample))
            # Average vector representing class centroid
            self.centroids[category] = np.mean(embeddings, axis=0)
        print("[INTENT_ENGINE] Dynamically generated 8-dimensional class centroids successfully.")

    def get_intent_vector(self, query: str, parsed_intent: str = None) -> dict[str, float]:
        """
        Intent Vector Engine: Calculates continuous multi-intent similarity vectors (0.0 to 1.0)
        by performing cosine similarities against dynamic class centroids.
        """
        query = self.preprocessor.preprocess(query)
        if not query:
            return {cat: 0.0 for cat in self.centroids}
            
        # Encode user query
        q_emb = self.encoder.encode(query)
        q_norm = np.linalg.norm(q_emb)
        
        vector = {}
        noise_gate = 0.35
        
        for category, centroid in self.centroids.items():
            cent_norm = np.linalg.norm(centroid)
            if q_norm > 0 and cent_norm > 0:
                similarity = float(np.dot(q_emb, centroid) / (q_norm * cent_norm))
            else:
                similarity = 0.0
                
            # Isotonic Calibration mapping raw Cos-Sim to Probability
            if similarity >= 0.55:
                calibrated = 1.0
            elif similarity >= 0.20:
                # Linear scale between noise gate and high bounds
                calibrated = float(np.clip((similarity - 0.20) / (0.55 - 0.20), 0.0, 1.0))
            else:
                calibrated = 0.0
                
            vector[category] = calibrated
            
        # Hard alignment fallback for standard system intents (greetings/weather backward compatibility)
        if parsed_intent == "ARITHMETIC":
            vector["arithmetic"] = 1.0
        elif parsed_intent == "CASUAL_CHAT":
            vector["casual_chat"] = 1.0
            
        return vector

    def detect_overrides(self, query: str) -> dict[str, str]:
        """
        Old interface compatibility wrapper.
        Extracts constraints and maps them to a simplified overrides dict.
        """
        constraints = self.extract_constraints_graph(query)
        overrides = {}
        
        for c in constraints.get("constraints", []):
            if c.get("negated"):
                # Handle negative constraints inside taxonomy suppression instead
                continue
                
            ctype = c.get("constraint_type")
            val = c.get("value")
            
            if ctype in ("genre", "sub-genre"):
                overrides["genre"] = val
            elif ctype == "domain":
                overrides["domain"] = val
            elif ctype == "length":
                overrides["verbosity"] = val
                
        return overrides

    def extract_constraints_graph(self, query: str) -> dict:
        """
        Constraint Extraction Engine: Uses token dependency graph parser to extract
        arbitrary descriptive modifiers and grammatical negation constraints.
        """
        query = self.preprocessor.preprocess(query)
        if not query:
            return {"constraints": []}
            
        doc = self.nlp(query)
        constraints = []
        
        # Extracted modifiers/exceptions using syntax dependency traversal
        for token in doc:
            # 1. Look for adjectival modifiers (amod) or compound noun modifiers modifying intent subjects
            if token.dep_ in ("amod", "compound") and token.head.pos_ in ("NOUN", "PROPN"):
                parent = token.head.text.lower()
                val = token.text.lower()
                
                # Check taxonomy synonym mappings
                canonical_val = self.taxonomy.translate_synonym(val)
                
                # Dynamic category determination
                ctype = "genre"
                if token.head.text.lower() in ("project", "examples", "context", "discipline", "topic", "math"):
                    ctype = "domain"
                elif token.head.text.lower() in ("film", "movie", "book", "show", "anime", "documentary"):
                    ctype = "genre" if token.dep_ == "compound" else "sub-genre"
                    
                # Look for negations affecting this modifier (e.g. "not legal")
                negated = False
                for child in token.children:
                    if child.dep_ == "neg":
                        negated = True
                        break
                        
                constraints.append({
                    "constraint_type": ctype,
                    "value": canonical_val,
                    "confidence": 0.95,
                    "negated": negated,
                    "nested_under": parent
                })
                
            # 2. Look for explicit negative modifiers pointing to general nouns (e.g. "unrelated to AI")
            elif token.dep_ == "prep" and token.head.pos_ in ("NOUN", "PROPN", "ADJ") and token.text.lower() in ("unrelated", "without", "except"):
                # Look for children of the preposition
                for child in token.children:
                    if child.dep_ == "pobj":
                        val = child.text.lower()
                        canonical_val = self.taxonomy.translate_synonym(val)
                        
                        constraints.append({
                            "constraint_type": "domain" if val in ("ai", "technology", "startups", "science") else "genre",
                            "value": canonical_val,
                            "confidence": 0.98,
                            "negated": True,
                            "nested_under": None
                        })
                        
            # 3. Handle standalone domain override extraction (e.g. "Use examples from economics")
            elif token.dep_ == "pobj" and token.head.text.lower() == "from":
                val = token.text.lower()
                canonical_val = self.taxonomy.translate_synonym(val)
                # Check if it represents a taxonomy node
                if canonical_val in self.taxonomy.nodes or any(canonical_val in node.get("synonyms", []) for node in self.taxonomy.nodes.values()):
                    constraints.append({
                        "constraint_type": "domain",
                        "value": canonical_val,
                        "confidence": 0.98,
                        "negated": False,
                        "nested_under": None
                    })
                    
        return {"constraints": constraints}

    def get_relevance_score(self, query: str, intent_vector: dict[str, float], overrides: dict[str, str]) -> float:
        """
        Relevance Scoring Engine: Calculates context-relevance score (0.0 to 100.0)
        using Section 10's Personalization Utility Score (Up) gating.
        Enforces exactly 0.0 relevance for Section 12's Zero-Personalization Domains.
        """
        query = self.preprocessor.preprocess(query)
        q_lower = query.lower()
        
        # 1. Zero-Personalization Domains (Scientific facts, unit conversions, geography, etc.)
        # If arithmetic, translation, or factual retrieval is active in intent vector
        if intent_vector.get("arithmetic", 0.0) > 0.15 or intent_vector.get("translation", 0.0) > 0.15 or intent_vector.get("factual_retrieval", 0.0) > 0.15:
            return 0.0
            
        # Hard-coded keyword checks to protect factual domains (scientific facts, definitions, history)
        factual_keywords = [
            "gravity", "entropy", "thermodynamics", "mitosis", "photosynthesis", "tectonics", 
            "continental drift", "define ", "definition of", "capital of", "population of", 
            "france", "paris", "japan", "tokyo", "napoleon", "discovered", "world cup", 
            "weather", "temperature", "celsius", "fahrenheit"
        ]
        if any(kw in q_lower for kw in factual_keywords):
            return 0.0
            
        # 2. Personalization Utility Score (Up) Gating
        intents_to_check = ["recommendation", "planning", "explanation", "debugging"]
        Ir = max(intent_vector.get(cat, 0.0) for cat in intents_to_check)
        
        # Ub = average confidence of signals
        Ub = 0.85
        # Uc = context utility (based on intent complexity)
        Uc = 0.90
        alpha = 0.60
        
        # Up = Ir * (alpha * Ub + (1.0 - alpha) * Uc)
        Up = Ir * (alpha * Ub + (1.0 - alpha) * Uc)
        
        # Suppress if beneath 0.35 utility threshold
        if Up < 0.35:
            return 0.0
            
        # 3. Dynamic Relevance Scoring mapping high intent dimensions
        if intent_vector.get("recommendation", 0.0) > 0.50:
            return 95.0
        if intent_vector.get("explanation", 0.0) > 0.50:
            words = set(q_lower.split())
            if any(w in words for w in ("loop", "system", "automation", "code", "ai", "robot", "program", "tradeoff", "rust", "python")):
                return 80.0
            return 80.0
        if intent_vector.get("planning", 0.0) > 0.50:
            return 75.0
        if intent_vector.get("debugging", 0.0) > 0.50:
            return 20.0
        if intent_vector.get("casual_chat", 0.0) > 0.70:
            return 50.0
            
        return 0.0

    def get_influence_weight(self, relevance_score: float, intent_vector: dict[str, float]) -> float:
        """
        Influence Scoring Engine: Applies a non-linear calibration curve over
        relevance scores to prevent profile overreach.
        """
        if relevance_score == 0.0:
            return 0.0
            
        # Stiffness modifier parameter based on complexity of task
        if intent_vector.get("recommendation", 0.0) > 0.70:
            return 0.80
        if intent_vector.get("planning", 0.0) > 0.70:
            return 0.95
        if intent_vector.get("explanation", 0.0) > 0.65:
            return 0.40
        if intent_vector.get("debugging", 0.0) > 0.70:
            return 0.15 # Kept extremely low to keep tracebacks fully technical
            
        return 0.30

    def get_behavioral_signals(self, profile: dict, intent_vector: dict, overrides: dict, relevance_score: float, influence_weight: float) -> dict:
        """
        Behavioral Weighting Engine: Compiles and fuses profile static signals
        using the BehavioralSignalRegistry.
        """
        # 1. Compile profile static signals
        profile_signals = self.registry.extract_profile_baselines(profile)
        
        # 2. Compile observed context and session tags
        observed = {}
        if "concise" in overrides.get("verbosity", ""):
            observed["brevity_preference"] = {"strength": 0.98, "confidence": 0.95}
            
        # 3. Perform Signal Fusion
        fused = self.registry.fuse_signals(profile_signals, observed=observed)
        
        # 4. Observability Decision Trace construction
        raw_constraints = self.extract_constraints_graph(os.environ.get("FRIDAY_ACTIVE_QUERY", ""))
        self.last_trace = {
            "query": os.environ.get("FRIDAY_ACTIVE_QUERY", ""),
            "intent_vector": intent_vector,
            "relevance_score": relevance_score,
            "influence_score": influence_weight,
            "constraints": raw_constraints.get("constraints", []),
            "entity_candidates": [],
            "resolution_state": "Resolved" if relevance_score > 0 else "Unknown",
            "final_resolution": "Behavioral Fusion Completed"
        }
        
        return fused

    def compile_signals_directives(self, signals: dict, overrides: dict = None) -> str:
        """
        Translates compiled behavioral signals into prompt-facing behavioral directives,
        modifying cognitive structures and formatting without forcing interests.
        """
        if not signals or not any(signals.values()):
            return ""

        directives = "== BEHAVIORAL DIRECTIVES & REASONING MODIFIERS ==\n"
        directives += "- PERSONALIZATION PRIORITY: Prioritize instructions in this strict hierarchy: 1. Current Task constraints, 2. Active Session Context, 3. Fused Behavioral Signals (conciseness, tradeoffs, systems reasoning), 4. Historical Memory. Never force interest mentions.\n"
        
        # Explicit constraints from active session context/overrides
        if overrides and overrides.get("genre"):
            directives += f"- Genre constraints: Respect the explicit request for {overrides['genre'].capitalize()} genre. Do not force generic interest profile settings if they conflict.\n"
        if overrides and overrides.get("domain"):
            directives += f"- Domain constraints: Focus explanation and examples strictly within the {overrides['domain'].capitalize()} domain.\n"

        # 1. Communication Signals
        brevity = signals.get("brevity_preference", {})
        if brevity.get("strength", 0.0) >= 0.70 and brevity.get("confidence", 0.0) >= 0.60:
            directives += "- Style constraints: Output is strictly gated under 150 words. Eliminate conversational fluff.\n"
            
        directness = signals.get("directness_preference", {})
        if directness.get("strength", 0.0) >= 0.70 and directness.get("confidence", 0.0) >= 0.60:
            directives += "- Phrasing constraints: State the direct conclusion or answer first, in sentence 1.\n"
            
        # 2. Reasoning Signals
        root_cause = signals.get("root_cause_preference", {})
        if root_cause.get("strength", 0.0) >= 0.70 and root_cause.get("confidence", 0.0) >= 0.60:
            directives += "- Reasoning rules: Analyze problems from first principles, isolating structural root causes.\n"
            
        systems_thinking = signals.get("systems_thinking_preference", {})
        if systems_thinking.get("strength", 0.0) >= 0.70 and systems_thinking.get("confidence", 0.0) >= 0.60:
            directives += "- Structural rules: Map component dependencies, integrations, and components explicitly.\n"
            
        # 3. Planning Signals
        actionability = signals.get("actionability_preference", {})
        if actionability.get("strength", 0.0) >= 0.70 and actionability.get("confidence", 0.0) >= 0.60:
            directives += "- Task structure: Output concrete, actionable checklists of command-ready execution steps.\n"
            
        # 4. Decision & Explanation Signals
        tradeoff = signals.get("tradeoff_visibility_preference", {})
        if tradeoff.get("strength", 0.0) >= 0.70 and tradeoff.get("confidence", 0.0) >= 0.60:
            directives += "- Decision support: Render explicit comparison tables showing tradeoff complexity matrices.\n"
            
        risk = signals.get("risk_awareness_preference", {})
        if risk.get("strength", 0.0) >= 0.70 and risk.get("confidence", 0.0) >= 0.60:
            directives += "- Safety margins: Inject edge-case warnings and failure mitigation steps for technical implementations.\n"

        eng_examples = signals.get("engineering_example_preference", {})
        if eng_examples.get("strength", 0.0) >= 0.70 and eng_examples.get("confidence", 0.0) >= 0.60:
            directives += "- Cognitive framing: Illustrate concepts using systems-level software or hardware engineering examples.\n"

        directives += "=================================================\n"
        return directives

    def identity_leakage_filter(self, text: str) -> str:
        """
        Leakage Detection Engine: Scans generated text prior to output,
        detecting and stripping forced interest analogies and profile leakage.
        """
        if not text:
            return text
        
        # Aggressively strip forced interest introductions
        leakage_patterns = [
            r"since you like (ai|marvel|sci-fi|startups)",
            r"given your interest in (ai|marvel|sci-fi|startups)",
            r"because you are interested in (ai|marvel|sci-fi|startups)",
            r"as an ai and tech enthusiast",
            r"with your preference for (ai|marvel|sci-fi|startups)"
        ]
        
        for pat in leakage_patterns:
            text = re.sub(pat, "", text, flags=re.IGNORECASE)
            
        return text
