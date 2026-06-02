"""
FRIDAY Weighted Semantic Router — v2
====================================

Pre-routing orchestrator that runs BEFORE intent parsing.

Uses a high-performance Weighted Semantic Routing algorithm (zero LLM calls,
zero network calls) to make fast, deterministic, and explainable decisions.

Routes:
  - MEMORY: Triggers on Aaditya, creator, companion identity, or personal goals/preferences.
  - NATIVE_OS / MEDIA / TEMPORAL: Direct Command bypasses for simple patterns.
  - RETRIEVAL: Fresh information (score > 6.0 threshold).
  - LLM: timeless knowledge or fallback conversation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from brain.context_manager import ContextManager
    from memory.preference import PreferenceMemory
    from memory.episodic import EpisodicMemory


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  PlannerDecision — structured output of the planning pass                  ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

@dataclass
class PlannerDecision:
    """Immutable routing decision produced by :class:`PlannerBrain`."""

    requires_freshness: bool = False
    requires_clarification: bool = False
    is_multi_task: bool = False
    is_simple_command: bool = False
    target_brain: str = "LLM"
    enriched_query: str = ""
    freshness_signals: list[str] = field(default_factory=list)
    freshness_score: float = 0.0
    priority: str = "NORMAL"


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  Weighted Routing Signal Database                                            ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

_FRESHNESS_WORDS = (
    "latest", "current", "currently", "recent", "recently",
    "today", "tonight", "this week", "this month", "this year",
    "right now", "now", "at the moment", "as of",
    "new", "newest", "updated", "update", "updates",
    "upcoming", "soon", "trending", "viral", "breaking",
    "live", "ongoing", "active", "who is the", "who won",
    "who leads", "who heads", "what happened", "what's happening",
    "news", "headline", "headlines", "announcement",
    "score", "scores", "match", "schedule", "standings", "leaderboard",
    "weather", "temperature", "forecast", "rain", "raining", "humidity",
    "stock", "price", "prices", "bitcoin", "crypto", "market",
    "prime minister", "president", "election", "government",
    "ipl", "nba", "nfl", "cricket", "world cup",
)

_COMMAND_VERBS = (
    "open", "launch", "start", "close", "quit", "exit",
    "minimize", "maximize", "restore", "shutdown", "restart",
    "sleep", "lock", "mute", "unmute", "volume", "brightness",
    "screenshot", "take screenshot", "cpu", "ram", "task manager",
    "play", "pause", "resume", "skip", "next", "previous", "song", "music",
    "lofi", "track", "map", "show map", "show me a map", "navigate to", "navigate",
    "route", "route to", "directions", "directions to", "way to", "drive to",
    "show my", "show me my", "focus", "bring to front", "bring", "hide", "louder", "quieter",
)

_KNOWLEDGE_WORDS = (
    "explain", "what is", "what are", "how does", "how do",
    "define", "meaning of", "difference between", "why does",
    "why is", "why do", "recursion", "code", "write a function",
    "calculate", "solve", "math", "derive",
)

_CONVERSATIONAL_WORDS = (
    "hello", "hi", "hey", "how are you", "thank you", "thanks",
    "tell me a joke", "joke", "sup", "yo", "what's up", "good morning",
    "good afternoon", "good evening", "good night", "got it", "nice",
)


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  PlannerBrain — high performance Weighted Semantic Router                     ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

class PlannerBrain:
    """Weighted Semantic Router for FRIDAY.

    Calculates path scores based on weights and triggers direct command
    bypasses or memory gates, ensuring infinite reliability and low latency.
    """

    def plan(
        self,
        query: str,
        context_manager: "ContextManager | None" = None,
        preference_memory: "PreferenceMemory | None" = None,
        episodic_memory: "EpisodicMemory | None" = None,
    ) -> PlannerDecision:
        if not query or not query.strip():
            decision = PlannerDecision(
                requires_clarification=True,
                target_brain="LLM",
                enriched_query="",
                priority="LOW",
            )
            self._log(query or "", decision, reason="Empty query", scores={})
            return decision

        q = query.strip()
        q_lower = q.lower()
        # ── Phase 3: Trigger Intelligence Dynamic Scoring ──
        from brain.trigger_intelligence import trigger_intel_mgr
        from brain.conflict_engine import conflict_resolver

        # Resolve command targets first to assign correct sub-class intent
        # ── Step 1: Memory-First Gate Check ──────────────────────────────────
        memory_score, memory_signals = self._calculate_memory_score(q_lower)
        
        # ── Step 2: Calculate Routing Scores ─────────────────────────────────
        freshness_signals = []
        for w in _FRESHNESS_WORDS:
            if re.search(r'\b' + re.escape(w) + r'\b', q_lower):
                freshness_signals.append(w)
        freshness_score = self._calculate_freshness_score(freshness_signals, q_lower)
        
        command_score = self._calculate_command_score(q_lower)
        knowledge_score = self._calculate_knowledge_score(q_lower)
        conversational_score = self._calculate_conversational_score(q_lower)

        cmd_brain = self._resolve_command_brain(q_lower) if command_score > 0.0 else None
        
        raw_intents = {
            "MEMORY": memory_score,
            "MEDIA": command_score if cmd_brain == "MEDIA" else 0.0,
            "NATIVE_OS": command_score if cmd_brain == "NATIVE_OS" else 0.0,
            "TEMPORAL": command_score if cmd_brain == "TEMPORAL" else 0.0,
            "RETRIEVAL": freshness_score,
            "LLM": max(knowledge_score, conversational_score)
        }

        # Calculate Trigger Intelligence Scores for all candidates
        trigger_scores = {}
        for trigger, intent_score in raw_intents.items():
            trigger_scores[trigger] = trigger_intel_mgr.calculate_trigger_score(trigger, intent_score)

        # Sort candidate triggers by their dynamic Trigger Intelligence Scores
        sorted_candidates = sorted(trigger_scores.items(), key=lambda x: x[1], reverse=True)
        t1, s1 = sorted_candidates[0]
        t2, s2 = sorted_candidates[1] if len(sorted_candidates) > 1 else (None, 0.0)

        # ── Phase 4: Dynamic Syntactic Conflict Engine Arbitration ──
        margin = float(round(abs(s1 - s2), 4))
        epsilon = 0.05
        is_tiebreak_invoked = False

        # Soft State Context extraction (Weak state Context bias)
        from core.state_manager import get_conversational_state
        state_str = str(get_conversational_state())

        if t2 is not None and margin < epsilon:
            print(f"[PIPELINE CONFLICT DETECTED] Margin between '{t1}' ({s1:.4f}) and '{t2}' ({s2:.4f}) is {margin:.4f} < {epsilon}. Invoking Conflict Engine...")
            is_tiebreak_invoked = True
            
            # Compute high-resolution Fused Conflict Scores
            c_score1 = conflict_resolver.calculate_fused_conflict_score(
                trigger=t1,
                semantic_intent_score=raw_intents[t1],
                query=query,
                system_state=state_str,
                historical_reliability=trigger_intel_mgr.get_reliability(t1)
            )
            c_score2 = conflict_resolver.calculate_fused_conflict_score(
                trigger=t2,
                semantic_intent_score=raw_intents[t2],
                query=query,
                system_state=state_str,
                historical_reliability=trigger_intel_mgr.get_reliability(t2)
            )
            
            print(f"[CONFLICT RESULT] Fused Conflict Scores: '{t1}' = {c_score1:.4f} | '{t2}' = {c_score2:.4f}")
            if c_score2 > c_score1:
                target_brain = t2
                route_reason = f"Conflict resolved in favor of '{t2}' (Conflict Score: {c_score2:.4f} > {c_score1:.4f})"
            else:
                target_brain = t1
                route_reason = f"Conflict resolved in favor of '{t1}' (Conflict Score: {c_score1:.4f} >= {c_score2:.4f})"
        else:
            target_brain = t1
            route_reason = f"Arbitrated cleanly to '{t1}' with high scoring margin ({margin:.4f} >= {epsilon})"

        # Map dynamic triggers to corresponding core brains
        if target_brain == "MEMORY" and s1 >= 8.0:
            target_brain = "MEMORY"
            route_reason = f"Memory-First Gate triggered: {', '.join(memory_signals)}"
        elif target_brain == "RETRIEVAL":
            target_brain = "RETRIEVAL"
            route_reason = f"Retrieval Route chosen due to dynamic freshness score {s1:.4f}"
        elif target_brain in ("MEDIA", "NATIVE_OS", "TEMPORAL"):
            route_reason = f"Command Route '{target_brain}' chosen dynamically"
        else:
            target_brain = "LLM"
            route_reason = f"Conversational fallback brain chosen dynamically"

        # Dynamically attach attributes for pipeline telemetry collection
        self.is_tiebreak_invoked = is_tiebreak_invoked
        self.trigger_scores = trigger_scores

        # Overrides for mixed map queries containing pronouns or corrections
        if "map" in q_lower:
            mixed_indicators = ("there", "here", "instead", "no", "wait", "actually", "scratch")
            if any(ind in q_lower for ind in mixed_indicators):
                target_brain = "LLM"
                route_reason = "Mixed map query with pronouns/corrections routed to LLM"

        # Explicit URL checks override everything except memory
        if target_brain != "MEMORY":
            url_pattern = re.compile(
                r"https?://[^\s]+|www\.[^\s]+|\b[\w\-]+\.(com|org|net|io|co|dev|ai|app|edu|gov)\b",
                re.IGNORECASE,
            )
            if url_pattern.search(q_lower):
                target_brain = "BROWSER"
                route_reason = "Direct URL link detected"

        # ── Step 4: Simple Command Bypass Check ─────────────────────────────
        is_simple_command = False
        if target_brain in ("NATIVE_OS", "MEDIA", "TEMPORAL"):
            is_simple_command = self._check_simple_command(q_lower)

        # ── Step 5: Ambiguity / multi-task checks ───────────────────────────
        requires_clarification = self._detect_ambiguity(q_lower)
        if requires_clarification:
            target_brain = "LLM"
            route_reason = "Ambiguity / clarification required"
        is_multi_task = self._detect_multi_task(q_lower)

        # ── Step 6: Memory context enrichment ────────────────────────────────
        enriched_query = self._enrich_query(q, context_manager, preference_memory)

        # ── Step 7: Priority & freshness flags assignment ───────────────────
        requires_freshness = freshness_score >= 6.0 or (target_brain == "RETRIEVAL")
        priority = "NORMAL"
        if target_brain in ("NATIVE_OS", "TEMPORAL") or requires_freshness:
            priority = "HIGH"
        elif requires_clarification:
            priority = "LOW"

        decision = PlannerDecision(
            requires_freshness=requires_freshness,
            requires_clarification=requires_clarification,
            is_multi_task=is_multi_task,
            is_simple_command=is_simple_command,
            target_brain=target_brain,
            enriched_query=enriched_query,
            freshness_signals=freshness_signals,
            freshness_score=freshness_score,
            priority=priority,
        )

        self._log(q, decision, reason=route_reason, scores=trigger_scores)
        return decision

    # ── internal: scores ─────────────────────────────────────────────────────

    @staticmethod
    def _calculate_memory_score(q_lower: str) -> tuple[float, list[str]]:
        """
        Memory-First Gate scoring: matches creator identity, companion identity,
        or personal goals/preferences.
        Filters day-of-week 'friday' references carefully!
        """
        score = 0.0
        matched = []

        # 1. Creator Identity Keywords
        creator_keys = (
            "aaditya", "creator", "builder", "developer", "master", "owner", 
            "built you", "made you", "who built", "who developed", "who designed", 
            "built by"
        )
        for kw in creator_keys:
            if kw in q_lower:
                score = max(score, 10.0)
                matched.append(kw)

        # 2. Companion Identity Keywords (Filter days of week like "on Friday")
        is_day_of_week = False
        if "friday" in q_lower:
            day_indicators = ("on friday", "this friday", "next friday", "last friday", "every friday", "is friday", "was friday", "friday is", "friday was", "friday the", "friday a")
            time_indicators = ("forecast", "weather", "rain", "raining", "temperature", "match", "score", "scores", "standings", "schedule", "date", "play", "plan", "plans", "night", "evening", "afternoon", "morning")
            if any(di in q_lower for di in day_indicators) or any(ti in q_lower and "friday" in q_lower for ti in time_indicators):
                is_day_of_week = True

            if not is_day_of_week:
                # If it's a casual greeting/acknowledgment addressing Friday, route to LLM, not MEMORY
                conversational_greetings = (
                    "hello", "hi", "hey", "yo", "sup", "good morning", "good afternoon", 
                    "good evening", "good night", "perfect", "thanks", "thank you", "nice", 
                    "how's your day", "how is your day", "how are you"
                )
                if any(re.search(r'\b' + re.escape(g) + r'\b', q_lower) for g in conversational_greetings):
                    pass # Do not trigger MEMORY gate for casual greeting addressing friday
                else:
                    score = max(score, 9.5)
                    matched.append("friday")

        # 3. User info / Preferences / Goals
        memory_keys = (
            "my name", "who am i", "know about me", "my goals", "my class", "my preferences",
            "my favorite", "my workspace", "my jee", "remember me", "my target", "my goal",
            "my profile", "my default", "my relational", "facts about me", "logged in",
            "my preferred", "who are you", "your name", "whats your name", "what is your name",
            "yourself", "who is friday", "who's friday", "are you friday", "are you a robot",
            "what is your function", "who is the assistant", "explain yourself", "introduce yourself",
            "do you know me", "remember my details", "identity", "personal details", "my details", 
            "remember my details", "about me", "want to achieve", "goals", "profile", "remember", 
            "know of me", "favorite"
        )
        for kw in memory_keys:
            if kw in q_lower:
                score = max(score, 9.8)
                matched.append(kw)

        return score, matched

    @staticmethod
    def _calculate_command_score(q_lower: str) -> float:
        """Score based on Command Verbs and PC action structures."""
        score = 0.0
        words = q_lower.split()
        if not words:
            return 0.0

        # Suppress command score if it's an explanation query
        explanation_indicators = ("what is", "what are", "explain", "define", "meaning of", "difference between", "why does", "why is", "why do")
        if any(ind in q_lower for ind in explanation_indicators):
            return 0.0

        first_word = words[0]
        # Direct starts get highest Command score
        if first_word in ("open", "launch", "start", "close", "quit", "exit", "minimize", "maximize", "shutdown", "restart", "sleep", "lock", "play", "pause", "resume", "skip", "next", "previous"):
            score = max(score, 9.5)
        
        # Word counts checks using word boundary search
        for verb in _COMMAND_VERBS:
            if re.search(r'\b' + re.escape(verb) + r'\b', q_lower):
                score = max(score, 8.5)

        # Local systems controls check using word boundary search
        sys_indicators = ("volume", "brightness", "screenshot", "mute", "unmute", "cpu", "ram", "task manager", "pc status", "system status")
        for ind in sys_indicators:
            if re.search(r'\b' + re.escape(ind) + r'\b', q_lower):
                score = max(score, 9.0)

        return score

    @staticmethod
    def _calculate_freshness_score(signals: list[str], q_lower: str) -> float:
        """Calculate a numerical freshness score between 0.0 and 10.0."""
        if not signals:
            return 0.0

        score = 0.0
        high_urgency = {
            "live", "breaking", "score", "scores", "match", "matches", "ipl", "nba", "nfl", 
            "cricket", "world cup", "trending", "viral", "latest", "who won", "won the", 
            "game tonight", "tonight"
        }
        mod_urgency = {
            "today", "weather", "temperature", "forecast", "rain", "raining", "humidity", 
            "news", "headline", "headlines", "currently", "at the moment", "now", "right now", 
            "stock", "price", "prices", "bitcoin", "crypto", "market", "announcement", 
            "updates", "update", "prime minister", "president", "election", "government", 
            "who is the", "who leads", "who heads", "what happened", "what's happening", 
            "schedule", "standings", "leaderboard", "championship", "events now", "current"
        }
        mild_urgency = {
            "recent", "recently", "upcoming", "new", "newest", "soon", "as of", 
            "this week", "this month", "this year"
        }

        for sig in signals:
            if any(hu in sig for hu in high_urgency):
                score = max(score, 9.5)
            elif any(mu in sig for mu in mod_urgency):
                score = max(score, 7.5)
            elif any(mi in sig for mi in mild_urgency):
                score = max(score, 5.0)

        # Casual chat context-inhibitor: "how are you today" has 'today' but is conversation
        greetings = ("how are you", "how are you today", "hello", "good morning", "good evening", "are you awake", "you awake", "are you there", "are you alive", "awake right now")
        if any(g in q_lower for g in greetings):
            score = max(0.0, score - 6.0)

        return score

    @staticmethod
    def _calculate_knowledge_score(q_lower: str) -> float:
        """Score based on timeless logical or knowledge explanations."""
        # Suppress knowledge score for real-time/news/weather queries
        realtime_indicators = ("happening", "trending", "weather", "news", "score", "match", "price", "stock", "current", "latest")
        if any(ind in q_lower for ind in realtime_indicators):
            return 0.0

        score = 0.0
        for kw in _KNOWLEDGE_WORDS:
            if kw in q_lower:
                score = max(score, 8.0)
        return score

    @staticmethod
    def _calculate_conversational_score(q_lower: str) -> float:
        """Score based on general conversational dialog or greetings."""
        score = 0.0
        for kw in _CONVERSATIONAL_WORDS:
            if kw in q_lower:
                score = max(score, 7.5)
        return score

    # ── internal: command helper ─────────────────────────────────────────────

    @staticmethod
    def _resolve_command_brain(q_lower: str) -> str:
        """Splits commands into correct NATIVE_OS, MEDIA, or TEMPORAL brains."""
        temporal_triggers = ("remind", "timer", "stopwatch", "stop watch", "alarm", "wake me up")
        if any(kw in q_lower for kw in temporal_triggers):
            return "TEMPORAL"

        # If it's a launch or close command targeting spotify, route to NATIVE_OS instead of MEDIA
        words = q_lower.split()
        if len(words) >= 2 and words[0] in ("open", "start", "launch", "close", "quit", "exit", "stop") and "spotify" in q_lower:
            if not any(v in q_lower for v in ("play", "pause", "resume", "volume", "mute", "unmute", "skip", "next", "previous")):
                return "NATIVE_OS"

        # Media controls matching (include Spotify specific closing controls!)
        media_triggers = ("play", "pause", "resume", "volume", "mute", "unmute", "skip", "spotify", "youtube music", "lofi", "music", "song", "track", "louder", "quieter", "video", "youtube")
        if any(kw in q_lower for kw in media_triggers):
            return "MEDIA"

        return "NATIVE_OS"

    @staticmethod
    def _check_simple_command(q_lower: str) -> bool:
        """
        Direct command bypass gate: returns True if query is a simple, direct command.
        Strips conversational filler words to normalize "Could you open the Spotify app please"
        down to "open spotify" before checking.
        """
        stripped = q_lower.strip().rstrip("?.! ")
        # Strip conversational filler prefixes
        for prefix in ("could you ", "can you ", "please ", "hey friday ", "friday "):
            if stripped.startswith(prefix):
                stripped = stripped[len(prefix):].strip()
        # Strip trailing filler
        for suffix in (" please", " for me", " now"):
            if stripped.endswith(suffix):
                stripped = stripped[:-len(suffix)].strip()

        words = stripped.split()
        if not words:
            return False

        # Simple 1-word commands
        if len(words) == 1:
            if words[0] in ("shutdown", "restart", "sleep", "lock", "mute", "unmute", "screenshot", "minimize", "maximize"):
                return True

        # Open/Launch/Start commands — accept ANY word count.
        # Strip filler articles ("the", "my", "a") and noise ("app", "application", "browser")
        # to extract the real target, then check if it's a known app/folder/site.
        verb = words[0]
        if verb in ("open", "start", "launch"):
            filler = {"the", "my", "a", "an", "app", "application", "browser", "website", "site", "web"}
            target_words = [w for w in words[1:] if w not in filler]
            target = " ".join(target_words)
            if target:
                # Media Command Protection: prevent media/YouTube queries from entering simple command bypass
                media_keywords = {"video", "videos", "latest", "newest", "short", "shorts", "reel", "reels", "by", "channel", "song", "playlist", "spotify", "youtube"}
                if any(w in target.split() for w in media_keywords):
                    return False
                return True  # Any open/launch/start with a target is a simple command

        # Simple 2-word or 3-word commands (verb + target)
        if len(words) in (2, 3):
            target = " ".join(words[1:])

            # Simple closings
            if verb == "close":
                simple_close = {"chrome", "spotify", "vscode", "notepad", "calculator", "paint", "cmd", "command prompt", "powershell", "settings", "explorer", "file explorer", "window", "current window", "active window", "it", "that", "tab", "this"}
                if target in simple_close:
                    return True

            # Simple media controls
            if verb == "volume" and target in ("up", "down"):
                return True
            if verb == "brightness" and target in ("up", "down"):
                return True
            if verb == "lock" and target == "pc":
                return True

        return False

    @staticmethod
    def _detect_ambiguity(q_lower: str) -> bool:
        # Strip conversational prefix "please"
        s = q_lower.strip().rstrip("?.! ")
        if s.startswith("please "):
            s = s[7:].strip()
        elif s.startswith("please"):
            s = s[6:].strip()
            
        bare_commands = {"open", "start", "launch", "play", "search", "find", "show", "close", "run", "browse"}
        if s in bare_commands:
            return True
            
        words = s.split()
        if len(words) == 1 and words[0] in bare_commands:
            return True
        return False

    @staticmethod
    def _detect_multi_task(q_lower: str) -> bool:
        conjunctions = re.compile(r"\b(and then|and also|and\b|then\b|also\b|after that|plus\b)", re.IGNORECASE)
        conj_match = conjunctions.search(q_lower)
        if not conj_match:
            return False

        parts = conjunctions.split(q_lower, maxsplit=1)
        if len(parts) < 3:
            return False

        left, right = parts[0].strip(), parts[2].strip()
        if not left or not right:
            return False

        action_words = (
            "open", "launch", "start", "close", "play", "search",
            "show", "tell", "find", "what", "who", "how", "where",
            "get", "check", "run", "browse", "navigate",
            "explain", "write", "create", "define", "weather",
            "news", "map", "screenshot", "minimize", "maximize",
        )

        left_has_action = any(w in left.split() for w in action_words)
        right_has_action = any(w in right.split() for w in action_words)

        return left_has_action and right_has_action

    @staticmethod
    def _enrich_query(
        query: str,
        context_manager: "ContextManager | None",
        preference_memory: "PreferenceMemory | None",
    ) -> str:
        enriched = query

        if context_manager is not None:
            try:
                resolved = context_manager.enrich_query(query)
                if resolved and resolved != query:
                    enriched = resolved
                    print(f"[PLANNER] Enriched pronoun: '{query}' -> '{enriched}'")
            except Exception as exc:
                print(f"[PLANNER WARNING] Context enrichment exception: {exc}")

        if preference_memory is not None:
            e_lower = enriched.lower()
            weather_words = ("weather", "temperature", "forecast", "rain", "humidity")
            if any(w in e_lower for w in weather_words):
                loc_preps = (" in ", " of ", " for ", " at ", " near ")
                if not any(p in e_lower for p in loc_preps):
                    city = preference_memory.get("default_city")
                    if city:
                        enriched = f"{enriched} in {city}"
                        print(f"[PLANNER] Enjected default city: '{enriched}'")

        return enriched

    @staticmethod
    def _log(query: str, decision: PlannerDecision, reason: str = "", scores: dict = None) -> None:
        flags = []
        if decision.requires_freshness:
            flags.append("FRESH")
        if decision.requires_clarification:
            flags.append("CLARIFY")
        if decision.is_multi_task:
            flags.append("MULTI")
        if decision.is_simple_command:
            flags.append("SIMPLE_BYPASS")

        flag_str = " | ".join(flags) if flags else "-"
        signals_str = ", ".join(decision.freshness_signals[:5]) if decision.freshness_signals else "none"
        truncated_query = (query[:60] + "...") if len(query) > 60 else query

        score_log = ""
        if scores:
            score_log = " ".join([f"{k}:{v:.1f}" for k, v in scores.items()])

        print(
            f"[PLANNER] Query: \"{truncated_query}\"\n"
            f"[PLANNER]   Target: {decision.target_brain}  Priority: {decision.priority}  Flags: [{flag_str}]  Freshness Score: {decision.freshness_score:.1f}\n"
            f"[PLANNER]   Scores: [{score_log}]\n"
            f"[PLANNER]   Reason: {reason}\n"
            f"[PLANNER]   Enriched: \"{decision.enriched_query[:80]}\""
        )
