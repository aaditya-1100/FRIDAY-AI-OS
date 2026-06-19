# LangGraph Status and Viability
# LangGraph was initially skipped during Phase R1 implementation to avoid potential Windows-specific 
# asyncio SelectorEventLoop conflicts and to keep the FSM lightweight and fully deterministic.
# However, a minimal 3-state LangGraph StateGraph test with asyncio has been attempted and succeeded 
# on this Windows host. Therefore, using LangGraph is viable for this system.
# Flagged for future migration: LangGraph can be adopted in a later phase, but for Phase R1, 
# the plain Python CognitiveFSM class remains the active and verified implementation.

import asyncio
import json
from enum import Enum
from typing import Dict, Any, List, Optional
from uuid import UUID, uuid4
from loguru import logger
from friday.core.events import EventEnvelope, EventPriority, TaskStatus
from friday.core.event_bus import event_bus

from brain.intent_parser import parse_intent
from llm.groq_client import ask_groq
from friday.memory.session import SessionMemory
from friday.core.schedulers import process_scheduler, task_scheduler
from friday.memory.semantic import SemanticMemory
from friday.memory.episodic import EpisodicMemory
from friday.memory.knowledge_graph import KnowledgeGraph
from brain.spacy_loader import get_spacy_model

# Ollama availability flag, set once at startup in main.py
OLLAMA_AVAILABLE = False


class UUIDEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, UUID):
            return str(obj)
        return super().default(obj)


class AssistantState(str, Enum):
    IDLE = "IDLE"
    PERCEIVING = "PERCEIVING"
    PLANNING = "PLANNING"
    DELEGATING = "DELEGATING"
    WAITING = "WAITING"
    SYNTHESIZING = "SYNTHESIZING"
    RESPONDING = "RESPONDING"
    REFLECTING = "REFLECTING"
    INTERRUPTED = "INTERRUPTED"
    ERROR = "ERROR"

class FSMTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""
    pass

class CognitiveFSM:
    def __init__(self, session_id: Optional[UUID] = None):
        self.session_id: UUID = session_id or uuid4()
        self.correlation_id: UUID = uuid4()
        self.current_state: AssistantState = AssistantState.IDLE
        self.goal_stack: List[Dict[str, Any]] = []
        self.working_memory: Dict[str, Any] = {}
        self.error_message: Optional[str] = None
        self.session_language: Optional[str] = None

        # Define valid transitions map
        self._transitions = {
            AssistantState.IDLE: {AssistantState.PERCEIVING, AssistantState.INTERRUPTED, AssistantState.ERROR},
            AssistantState.PERCEIVING: {AssistantState.PLANNING, AssistantState.INTERRUPTED, AssistantState.ERROR, AssistantState.IDLE},
            AssistantState.PLANNING: {AssistantState.DELEGATING, AssistantState.SYNTHESIZING, AssistantState.INTERRUPTED, AssistantState.ERROR, AssistantState.IDLE},
            AssistantState.DELEGATING: {AssistantState.WAITING, AssistantState.SYNTHESIZING, AssistantState.INTERRUPTED, AssistantState.ERROR, AssistantState.IDLE},
            AssistantState.WAITING: {AssistantState.DELEGATING, AssistantState.SYNTHESIZING, AssistantState.INTERRUPTED, AssistantState.ERROR, AssistantState.IDLE},
            AssistantState.SYNTHESIZING: {AssistantState.RESPONDING, AssistantState.INTERRUPTED, AssistantState.ERROR, AssistantState.IDLE},
            AssistantState.RESPONDING: {AssistantState.REFLECTING, AssistantState.INTERRUPTED, AssistantState.ERROR},
            AssistantState.REFLECTING: {AssistantState.IDLE, AssistantState.INTERRUPTED, AssistantState.ERROR},
            AssistantState.INTERRUPTED: {AssistantState.PERCEIVING, AssistantState.IDLE, AssistantState.ERROR},
            AssistantState.ERROR: set()  # Terminal within a session
        }

    def reset_for_new_request(self, correlation_id: Optional[UUID] = None):
        """Prepares FSM for a new request/turn."""
        self.correlation_id = correlation_id or uuid4()
        self.working_memory = {}
        self.error_message = None

    def transition_to(self, new_state: AssistantState, reason: str = "", force: bool = False):
        """Transitions to a new state if valid, and publishes a state change event."""
        if not force and self.current_state == AssistantState.ERROR:
            raise FSMTransitionError("Cannot transition out of terminal ERROR state.")

        # Interrupt is always valid unless currently in ERROR
        is_interrupt = new_state == AssistantState.INTERRUPTED
        is_valid = force or is_interrupt or (new_state in self._transitions[self.current_state])

        if not is_valid:
            raise FSMTransitionError(
                f"Invalid transition from {self.current_state.value} to {new_state.value}."
            )

        old_state = self.current_state
        self.current_state = new_state
        
        logger.info(
            f"[FSM] Transition: {old_state.value} -> {new_state.value} "
            f"(reason: '{reason}', correlation_id={self.correlation_id})"
        )

        # Publish state change event
        event_payload = {
            "old_state": old_state.value,
            "new_state": new_state.value,
            "reason": reason,
            "goal_stack": self.goal_stack,
            "working_memory": self.working_memory,
            "error_message": self.error_message
        }
        
        envelope = EventEnvelope(
            topic="friday.core.state_change",
            priority=EventPriority.P1,
            source="cognitive_core.fsm",
            correlation_id=self.correlation_id,
            session_id=self.session_id,
            payload=event_payload
        )
        
        event_bus.publish_sync(envelope)

class CognitiveCore:
    def __init__(self, fsm: Optional[CognitiveFSM] = None):
        self.fsm = fsm or CognitiveFSM()
        self.pending_requests: Dict[UUID, asyncio.Future] = {}
        self._loop = None
        self._is_running = False
        self.active_correlation_id = None
        self.current_turn_task = None

    @property
    def current_state(self) -> AssistantState:
        return self.fsm.current_state

    @current_state.setter
    def current_state(self, val: AssistantState):
        self.fsm.current_state = val

    def start(self, loop: Optional[asyncio.AbstractEventLoop] = None):
        if self._is_running:
            return
        self._loop = loop or asyncio.get_running_loop()
        self._is_running = True
        event_bus.subscribe("friday.perception.text.input", self.on_perception_input)
        event_bus.subscribe("friday.perception.voice.raw", self.on_perception_input)
        event_bus.subscribe("friday.agent.*.result", self.on_agent_result)
        event_bus.subscribe("friday.core.proactive_trigger", self.on_proactive_trigger)
        logger.info("[CognitiveCore] Started. Subscribed to perception, agent result, and proactive events.")

    def stop(self):
        if not self._is_running:
            return
        self._is_running = False
        event_bus.unsubscribe("friday.perception.text.input", self.on_perception_input)
        event_bus.unsubscribe("friday.perception.voice.raw", self.on_perception_input)
        event_bus.unsubscribe("friday.agent.*.result", self.on_agent_result)
        event_bus.unsubscribe("friday.core.proactive_trigger", self.on_proactive_trigger)
        for future in list(self.pending_requests.values()):
            if not future.done():
                future.cancel()
        self.pending_requests.clear()
        logger.info("[CognitiveCore] Stopped.")

    def abort_current_turn(self):
        if hasattr(self, "current_turn_task") and self.current_turn_task is not None:
            if not self.current_turn_task.done():
                logger.info("[CognitiveCore] Aborting current turn task.")
                self.current_turn_task.cancel()
        
        self.fsm.working_memory = {}
        self.active_correlation_id = None
        self.fsm.transition_to(AssistantState.IDLE, reason="Forced abort to IDLE", force=True)
    def _detect_language(self, text: str) -> str:
        if not text or not text.strip():
            return "en"
        # 1. Devanagari script check
        if any("\u0900" <= char <= "\u097F" for char in text):
            return "hi"
        # 2. Hinglish stopwords check
        hinglish_words = {
            "hai", "karo", "bhai", "bhi", "kya", "kar", "se", "ko", "par", "ek",
            "yeh", "woh", "ki", "ka", "ke", "mein", "toh", "naam", "batao", "likho",
            "acha", "theek", "sab", "kuch", "hota", "sakte", "yahi", "daru", "sari",
            "jo", "ho", "tum", "aap", "mera", "meri", "hum", "mujhe", "apna", "apni",
            "hoga", "raha", "rahi", "rahe", "gaya", "gayi", "karna", "kr", "rha",
            "rhi", "hu", "hoon", "tha", "thi", "the"
        }
        import re
        words = set(re.findall(r'\b\w+\b', text.lower()))
        if words.intersection(hinglish_words):
            return "hi"
        # 3. Langdetect fallback
        try:
            import langdetect
            det = langdetect.detect(text)
            if det == "hi":
                return "hi"
        except Exception:
            pass
        return "en"

    async def _retrieve_memory_context(self, raw_input: str, intent: str, app_id: str = "general") -> Dict[str, Any]:
        """Retrieves semantic, episodic, and entity relations context with a 500ms timeout."""
        loop = asyncio.get_running_loop()
        
        def fetch_all():
            # 1. Semantic Memory
            try:
                sem = SemanticMemory()
                sem_results = sem.search(raw_input, limit=3, app_id=app_id)
                semantic_facts = [hit.get("payload", {}).get("text", "") for hit in sem_results if hit.get("payload")]
            except Exception as e:
                logger.error(f"[FSM] SemanticMemory search failed: {e}")
                semantic_facts = []

            # 2. Episodic Memory
            try:
                epi = EpisodicMemory()
                if hasattr(epi, "get_recent"):
                    recent_episodes = epi.get_recent(limit=3, app_id=app_id)
                else:
                    recent_episodes = epi.get_recent_episodes(limit=3, app_id=app_id)
            except Exception as e:
                logger.error(f"[FSM] EpisodicMemory search failed: {e}")
                recent_episodes = []

            # 3. Entity relations via spaCy and KnowledgeGraph
            try:
                nlp = get_spacy_model()
                entity_context = []
                if nlp:
                    doc = nlp(raw_input)
                    entities = [ent.text for ent in doc.ents]
                    graph = KnowledgeGraph()
                    for ent in entities:
                        rels = graph.get_relations(ent)
                        for r in rels:
                            entity_context.append({
                                "source": r[0],
                                "relation": r[1],
                                "target": r[2],
                                "weight": r[3]
                            })
            except Exception as e:
                logger.error(f"[FSM] KnowledgeGraph query failed: {e}")
                entity_context = []

            return {
                "semantic_facts": semantic_facts,
                "recent_episodes": recent_episodes,
                "entity_context": entity_context
            }

        try:
            return await asyncio.wait_for(
                loop.run_in_executor(None, fetch_all),
                timeout=0.5
            )
        except asyncio.TimeoutError:
            logger.warning("[FSM] Memory retrieval timed out (500ms limit). Returning empty context.")
            return {
                "semantic_facts": [],
                "recent_episodes": [],
                "entity_context": []
            }
        except Exception as e:
            logger.error(f"[FSM] Error retrieving memory context: {e}")
            return {
                "semantic_facts": [],
                "recent_episodes": [],
                "entity_context": []
            }

    async def on_perception_input(self, envelope: EventEnvelope):
        if self._loop:
            self.active_correlation_id = envelope.correlation_id
            self.current_turn_task = self._loop.create_task(self._process_request_turn(envelope))

    async def on_proactive_trigger(self, envelope: EventEnvelope):
        if not self._loop:
            return
        if self.current_state != AssistantState.IDLE:
            logger.info(f"[CognitiveCore] Suppressed proactive trigger '{envelope.payload.get('rule')}' because FSM is not IDLE (state={self.current_state.value}).")
            return
        self.active_correlation_id = envelope.correlation_id
        self.current_turn_task = self._loop.create_task(self._process_proactive_turn(envelope))

    async def _process_proactive_turn(self, envelope: EventEnvelope):
        corr_id = envelope.correlation_id
        rule_name = envelope.payload.get("rule", "PROACTIVE")
        message = envelope.payload.get("message", "")
        logger.info(f"[CognitiveCore] Starting proactive turn for rule '{rule_name}' (correlation_id={corr_id})")

        # 1. Reset FSM and set active correlation ID
        self.fsm.reset_for_new_request(correlation_id=corr_id)
        self.active_correlation_id = corr_id
        
        # 1b. Extract app_id and detect language
        from friday.system.context import system_context
        ctx = system_context.get_context()
        app_id = ctx.get("app_id", "general")
        self.fsm.working_memory["current_app_id"] = app_id
        
        detected_language = self.fsm.session_language or self._detect_language(message)
        self.fsm.working_memory["detected_language"] = detected_language
        logger.info(f"[CognitiveCore] Proactive turn: app_id='{app_id}' detected_language='{detected_language}'")

        # Set the required working_memory fields
        self.fsm.working_memory["intent"] = rule_name
        self.fsm.working_memory["confidence"] = 1.0
        self.fsm.working_memory["raw_input"] = message
        self.fsm.working_memory["plan_type"] = "DIRECT_LLM"
        self.fsm.working_memory["clarification"] = False
        self.fsm.working_memory["agent_type"] = None
        self.fsm.working_memory["parsed_intent"] = {"intent": rule_name}

        # 2. Transition directly to PLANNING
        self.fsm.transition_to(AssistantState.PLANNING, reason="Proactive trigger received, entering planning state")

        # Retrieve memory context
        memory_context = await self._retrieve_memory_context(message, rule_name, app_id=app_id)
        self.fsm.working_memory["memory_context"] = memory_context

        # 3. Transition directly to SYNTHESIZING (skipping DELEGATING & WAITING)
        self.fsm.transition_to(AssistantState.SYNTHESIZING, reason="Proactive turn: direct LLM synthesis")

        # Fetch history turns (last 6 turns/messages)
        session = SessionMemory()
        full_history = session.get("conversation_history", app_id=app_id) or []
        history_turns = full_history[-6:]
        self.fsm.working_memory["conversation_history"] = history_turns

        # Assemble system prompt (screen_context is None as VisionAgent was not involved)
        from friday.system.context import system_context
        from friday.core.system_prompt import assemble_system_prompt
        system_prompt = assemble_system_prompt(self.fsm.working_memory, system_context.get_context(), screen_context=None)

        # Call Groq inference using message as query_input
        async def run_groq_inference():
            import functools
            func = functools.partial(
                ask_groq,
                message,
                system_prompt=system_prompt,
                model="llama-3.3-70b-versatile",
                history=history_turns,
                timeout=5.0
            )
            return await process_scheduler.schedule_llm(func)

        async def call_ollama_fallback():
            import functools
            func = functools.partial(
                ask_ollama,
                message,
                system_prompt=system_prompt,
                model="qwen2.5:14b",
                history=history_turns,
                timeout=3.0
            )
            return await process_scheduler.schedule_llm(func)

        final_response = "I encountered an error while formulating my proactive thought."
        try:
            final_response = await run_groq_inference()
        except Exception as e_groq:
            logger.warning(f"[CognitiveCore] Groq synthesis failed: {e_groq}. Retrying with Ollama fallback...")
            try:
                final_response = await call_ollama_fallback()
            except Exception as e_ollama:
                logger.error(f"[CognitiveCore] Ollama fallback failed: {e_ollama}")
                final_response = "I detected an alert but both my brain engines are currently offline, sir."

        self.fsm.working_memory["synthesis_result"] = final_response

        # 4. Transition to RESPONDING
        self.fsm.transition_to(AssistantState.RESPONDING, reason="Response synthesized, entering responding phase")

        # Publish the response event so backend server / UI gets it
        resp_envelope = EventEnvelope(
            topic="friday.core.response",
            priority=EventPriority.P1,
            source="cognitive_core.orchestrator",
            correlation_id=corr_id,
            session_id=self.fsm.session_id,
            payload={"response": final_response}
        )
        await event_bus.publish(resp_envelope)

        # Voice Responding (standard TTS)
        tts_req_envelope = EventEnvelope(
            topic="friday.agent.voice.tts_request",
            priority=EventPriority.P1,
            source="cognitive_core.orchestrator",
            correlation_id=corr_id,
            session_id=self.fsm.session_id,
            payload={"text": final_response}
        )
        await event_bus.publish(tts_req_envelope)

        # Await tts_complete or timeout
        loop = asyncio.get_running_loop()
        tts_completed_event = asyncio.Event()

        async def on_tts_complete(env: EventEnvelope):
            if env.correlation_id == corr_id:
                tts_completed_event.set()

        event_bus.subscribe("friday.agent.voice.tts_complete", on_tts_complete)
        try:
            await asyncio.wait_for(tts_completed_event.wait(), timeout=10.0)
            logger.info(f"[CognitiveCore] TTS playback complete (correlation_id={corr_id})")
        except asyncio.TimeoutError:
            logger.warning(f"[CognitiveCore] TTS playback timed out (correlation_id={corr_id})")
        finally:
            event_bus.unsubscribe("friday.agent.voice.tts_complete", on_tts_complete)

        # 5. Transition to REFLECTING
        self.fsm.transition_to(AssistantState.REFLECTING, reason="Entering reflection phase")

        import datetime
        now_iso = datetime.datetime.utcnow().isoformat() + "Z"

        # Build interaction record for memory write
        interaction_record = {
            "raw_input": message,
            "intent": rule_name,
            "success": True,
            "response": final_response,
            "confidence": 1.0,
            "agent_results": [],
            "session_id": str(self.fsm.session_id),
            "correlation_id": str(corr_id),
            "timestamp": now_iso
        }
        
        # Serialize UUIDs for memory write event
        try:
            interaction_record = json.loads(json.dumps(interaction_record, cls=UUIDEncoder))
        except Exception as ex:
            logger.error(f"[FSM] Failed to JSON-serialize proactive interaction_record: {ex}")

        memory_envelope = EventEnvelope(
            topic="friday.memory.write",
            priority=EventPriority.P3,
            source="cognitive_core.orchestrator",
            correlation_id=corr_id,
            session_id=self.fsm.session_id,
            payload=interaction_record
        )
        await event_bus.publish(memory_envelope)

        # Record proactive turn in UserProfile
        try:
            from friday.memory.user_profile import user_profile
            asyncio.create_task(
                user_profile.record_turn(
                    intent=rule_name,
                    entities=[],
                    active_window=system_context.get_context().get("active_window", ""),
                    hour=datetime.datetime.now().hour
                )
            )
        except Exception as e_prof:
            logger.error(f"[FSM] Failed to record proactive turn in user profile: {e_prof}")

        # Ensure conversation history is updated in SessionMemory
        new_history = history_turns + [
            {"role": "user", "content": message},
            {"role": "assistant", "content": final_response}
        ]
        
        # Enforce history limit
        while (len(json.dumps(new_history)) / 3) > 2000 and len(new_history) > 2:
            new_history = new_history[2:]
            
        session.set("conversation_history", new_history, app_id=app_id)

        # Let the event bus loop run to deliver the event
        await asyncio.sleep(0.05)

        # Clear working memory
        self.fsm.working_memory = {}

        # 6. Transition to IDLE
        self.fsm.transition_to(AssistantState.IDLE, reason="Turn completed successfully")
        logger.info(f"[CognitiveCore] Proactive turn completed successfully (correlation_id={corr_id})")

    async def _process_request_turn(self, envelope: EventEnvelope):
        corr_id = envelope.correlation_id
        text = envelope.payload.get("text", "")
        logger.info(f"[CognitiveCore] Starting turn for input: '{text}' (correlation_id={corr_id})")

        # 1. Reset FSM and set active correlation ID
        self.fsm.reset_for_new_request(correlation_id=corr_id)
        self.active_correlation_id = corr_id
        self.fsm.working_memory["raw_input"] = text

        # 1b. Extract app_id and detect language
        from friday.system.context import system_context
        ctx = system_context.get_context()
        app_id = ctx.get("app_id", "general")
        self.fsm.working_memory["current_app_id"] = app_id

        # Language lock and override logic
        text_lower = text.lower()
        if "speak in hindi" in text_lower or "switch to hindi" in text_lower:
            self.fsm.session_language = "hi"
            logger.info("[CognitiveCore] session_language explicitly overridden to Hindi")
        elif "speak in english" in text_lower or "switch to english" in text_lower:
            self.fsm.session_language = "en"
            logger.info("[CognitiveCore] session_language explicitly overridden to English")
        elif self.fsm.session_language is None:
            try:
                import langdetect
                probs = langdetect.detect_langs(text)
                if probs:
                    top_lang = probs[0]
                    if top_lang.prob >= 0.85:
                        self.fsm.session_language = top_lang.lang
                        logger.info(f"[CognitiveCore] Locked session_language to '{top_lang.lang}' with confidence {top_lang.prob}")
                    else:
                        logger.info(f"[CognitiveCore] Ambiguous language confidence {top_lang.prob} for '{top_lang.lang}'. Not locking.")
            except Exception as e:
                logger.warning(f"[CognitiveCore] Langdetect failed: {e}")

        detected_language = self.fsm.session_language or self._detect_language(text)
        self.fsm.working_memory["detected_language"] = detected_language
        logger.info(f"[CognitiveCore] Request turn: app_id='{app_id}' detected_language='{detected_language}'")

        # 2. Transition to PERCEIVING
        self.fsm.transition_to(AssistantState.PERCEIVING, reason="Raw input received, starting perception")
        
        intent = "CLARIFICATION"
        confidence = 0.0
        parsed_result = {}
        
        try:
            # Call parse_intent(text) with a 3.0s timeout in threadpool
            loop = asyncio.get_running_loop()
            parsed_result = await asyncio.wait_for(
                loop.run_in_executor(None, parse_intent, text),
                timeout=3.0
            )
            intent = parsed_result.get("intent", "AI_QUERY")
            confidence = parsed_result.get("confidence", 1.0 if intent != "CLARIFICATION" else 0.5)
        except asyncio.TimeoutError:
            logger.warning(f"[CognitiveCore] parse_intent timed out after 3.0s (correlation_id={corr_id})")
            intent = "CLARIFICATION"
            confidence = 0.0
            parsed_result = {"intent": "CLARIFICATION", "question": "Could you please clarify your request, sir?"}
        except Exception as e:
            logger.error(f"[CognitiveCore] Error in parse_intent: {e} (correlation_id={corr_id})")
            intent = "AI_QUERY"
            confidence = 0.5
            parsed_result = {"intent": "AI_QUERY", "query": text}

        # Store in FSM state dict
        self.fsm.working_memory["intent"] = intent
        self.fsm.working_memory["confidence"] = confidence
        self.fsm.working_memory["parsed_intent"] = parsed_result

        # Publish friday.perception.intent_classified event
        classified_envelope = EventEnvelope(
            topic="friday.perception.intent_classified",
            priority=EventPriority.P1,
            source="cognitive_core.orchestrator",
            correlation_id=corr_id,
            session_id=self.fsm.session_id,
            payload={"intent": intent, "confidence": confidence}
        )
        await event_bus.publish(classified_envelope)

        # 3. Transition to PLANNING (always, no exceptions)
        self.fsm.transition_to(AssistantState.PLANNING, reason="Input perceived, constructing execution plan")

        # Retrieve memory context during PLANNING state
        memory_context = await self._retrieve_memory_context(text, intent, app_id=app_id)
        self.fsm.working_memory["memory_context"] = memory_context

        try:
            from friday.memory.knowledge_graph import KnowledgeGraph
            kg = KnowledgeGraph()
            kg_nodes_count = len(kg.graph.nodes)
        except Exception as e:
            logger.warning(f"[FSM] Failed to load Knowledge Graph node count: {e}")
            kg_nodes_count = 0

        logger.info(f"[FSM PLANNING] Retrieved memory context: {memory_context}")
        logger.info(f"[FSM PLANNING] Knowledge Graph nodes count: {kg_nodes_count}")

        from friday.core.routing_table import INTENT_TO_AGENT, DIRECT_LLM_INTENTS, MULTI_ACTION_INTENT

        # Direct LLM check or low-confidence/clarification
        if intent in DIRECT_LLM_INTENTS or confidence < 0.6:
            self.fsm.working_memory["plan_type"] = "DIRECT_LLM"
            self.fsm.working_memory["agent_type"] = None
            if confidence < 0.6:
                self.fsm.working_memory["clarification"] = True
            # Transition to SYNTHESIZING directly (skipping DELEGATING and WAITING)
            self.fsm.transition_to(AssistantState.SYNTHESIZING, reason="Direct LLM route or low-confidence clarification")
        elif intent == MULTI_ACTION_INTENT:
            self.fsm.working_memory["plan_type"] = "MULTI"
            self.fsm.transition_to(AssistantState.DELEGATING, reason="MULTI_ACTION task, decomposing execution")
        else:
            agent_type = INTENT_TO_AGENT.get(intent, "PC_AGENT")
            self.fsm.working_memory["plan_type"] = "SINGLE"
            self.fsm.working_memory["agent_type"] = agent_type
            self.fsm.transition_to(AssistantState.DELEGATING, reason=f"Routing single task to {agent_type}")

        plan_type = self.fsm.working_memory.get("plan_type")

        # 4. DELEGATING state execution
        if plan_type in ("SINGLE", "MULTI"):
            dispatched_task_ids = []

            if plan_type == "SINGLE":
                from friday.core.events import TaskDispatch, AgentType
                agent_type_str = self.fsm.working_memory.get("agent_type")
                task_id = uuid4()

                parameters = self.fsm.working_memory.get("parsed_intent", {})
                if "query" not in parameters:
                    parameters["query"] = text

                dispatch = TaskDispatch(
                    task_id=task_id,
                    session_id=self.fsm.session_id,
                    agent_type=AgentType(agent_type_str),
                    intent=intent,
                    parameters=parameters,
                    correlation_id=corr_id
                )

                dispatched_task_ids.append(task_id)

                # Publish TaskDispatch on correct agent topic
                dispatch_envelope = EventEnvelope(
                    topic=f"friday.agent.{agent_type_str.lower()}.dispatch",
                    priority=EventPriority.P2,
                    source="cognitive_core.orchestrator",
                    correlation_id=corr_id,
                    session_id=self.fsm.session_id,
                    payload=dispatch.model_dump()
                )
                await event_bus.publish(dispatch_envelope)

                self.fsm.working_memory["dispatched_tasks"] = dispatched_task_ids
                self.fsm.transition_to(AssistantState.WAITING, reason=f"Awaiting PC/Web Agent response (SINGLE task)")

            elif plan_type == "MULTI":
                from friday.core.events import TaskDispatch, AgentType
                from friday.core.schedulers import task_scheduler

                actions = self.fsm.working_memory.get("parsed_intent", {}).get("actions", [])
                tasks_to_submit = []

                for act in actions:
                    sub_intent = act.get("intent")
                    sub_agent = INTENT_TO_AGENT.get(sub_intent)
                    if sub_agent is None or sub_agent == "None":
                        continue

                    sub_task_id = uuid4()
                    dispatch = TaskDispatch(
                        task_id=sub_task_id,
                        session_id=self.fsm.session_id,
                        agent_type=AgentType(sub_agent),
                        intent=sub_intent,
                        parameters=act,
                        correlation_id=corr_id
                    )
                    tasks_to_submit.append(dispatch)
                    dispatched_task_ids.append(sub_task_id)

                if tasks_to_submit:
                    task_scheduler.submit_dag(tasks_to_submit, corr_id, self.fsm.session_id)
                else:
                    logger.warning("[CognitiveCore] MULTI_ACTION decomposed into 0 actionable agent tasks!")

                self.fsm.working_memory["dispatched_tasks"] = dispatched_task_ids
                self.fsm.transition_to(AssistantState.WAITING, reason=f"Awaiting task DAG completion (MULTI task)")

            # 5. WAITING state execution (single-threaded subscription, no asyncio.gather)
            collected_results = []
            waiting_event = asyncio.Event()
            expected_ids = {str(tid) for tid in dispatched_task_ids}

            async def on_agent_result(env: EventEnvelope) -> None:
                if self.active_correlation_id is not None and env.correlation_id != self.active_correlation_id:
                    logger.info(f"late result discarded for correlation_id {env.correlation_id}")
                    return
                payload = env.payload
                t_id = payload.get("task_id")
                if t_id and str(t_id) in expected_ids:
                    if not any(str(r.get("task_id")) == str(t_id) for r in collected_results):
                        collected_results.append(payload)
                        if len(collected_results) >= len(expected_ids):
                            waiting_event.set()

            event_bus.subscribe("friday.agent.*.result", on_agent_result)

            timeout_limit = 10.0 if plan_type == "SINGLE" else 15.0
            try:
                await asyncio.wait_for(waiting_event.wait(), timeout=timeout_limit)
                logger.info(f"[CognitiveCore] All expected agent task results received (correlation_id={corr_id})")
            except asyncio.TimeoutError:
                logger.warning(f"[CognitiveCore] WAITING state timed out after {timeout_limit}s. Collecting partial results.")
                self.fsm.working_memory["partial"] = True
            finally:
                event_bus.unsubscribe("friday.agent.*.result", on_agent_result)

            self.fsm.working_memory["agent_results"] = collected_results

            # Check for failed agent tasks
            has_failed = False
            error_msg = "Unknown task execution error"
            for res in collected_results:
                status_val = res.get("status")
                if status_val == TaskStatus.FAILED or status_val == "FAILED" or status_val == TaskStatus.TIMEOUT or status_val == "TIMEOUT":
                    has_failed = True
                    error_msg = res.get("payload", {}).get("error") or res.get("payload", {}).get("reason") or "Agent task failed"
                    break
            
            if has_failed:
                logger.warning(f"[CognitiveCore] Agent task failed: {error_msg}. Entering ERROR state.")
                self.fsm.error_message = error_msg
                self.fsm.transition_to(AssistantState.ERROR, reason=f"Task execution failed: {error_msg}")
                return

            # Transition to SYNTHESIZING
            self.fsm.transition_to(AssistantState.SYNTHESIZING, reason="Agent execution phase finished, generating response")

        # 6. SYNTHESIZING state execution
        if self.fsm.working_memory.get("clarification", False) or intent == "CLARIFICATION":
            query_input = f"The user command was ambiguous or low confidence. Ask for clarification. Raw input: '{text}'"
        else:
            query_input = text

        # Fetch history turns (last 6 turns/messages)
        session = SessionMemory()
        full_history = session.get("conversation_history", app_id=app_id) or []
        history_turns = full_history[-6:]
        
        # Populate history in working memory for the prompt assembler
        self.fsm.working_memory["conversation_history"] = history_turns
        
        # Extract screen context from VisionAgent results if available
        screen_context_data = None
        for r in self.fsm.working_memory.get("agent_results", []):
            payload = {}
            is_vision = False
            if hasattr(r, "payload"):
                payload = r.payload or {}
                if "ocr_text" in payload or "full_text" in payload:
                    is_vision = True
            elif isinstance(r, dict):
                payload = r.get("payload") or {}
                if "ocr_text" in payload or "full_text" in payload:
                    is_vision = True
            if is_vision:
                screen_context_data = {
                    "ocr_text": payload.get("ocr_text") or payload.get("full_text") or "",
                    "active_window": payload.get("active_window") or ""
                }
                break
        
        from friday.system.context import system_context
        from friday.core.system_prompt import assemble_system_prompt
        system_prompt = assemble_system_prompt(self.fsm.working_memory, system_context.get_context(), screen_context=screen_context_data)

        async def run_groq_inference():
            import functools
            func = functools.partial(
                ask_groq,
                query_input,
                system_prompt=system_prompt,
                model="llama-3.3-70b-versatile",
                history=history_turns,
                timeout=5.0
            )
            return await process_scheduler.schedule_llm(func)

        async def call_ollama_fallback():
            import httpx
            logger.info("[CognitiveCore] Triggering Ollama fallback (qwen2.5:14b) with 3s timeout.")
            messages = [{"role": "system", "content": system_prompt}]
            for turn in history_turns:
                messages.append({
                    "role": turn.get("role", "user"),
                    "content": str(turn.get("content", ""))
                })
            messages.append({"role": "user", "content": query_input})

            payload = {
                "model": "qwen2.5:14b",
                "messages": messages,
                "stream": False
            }

            async with httpx.AsyncClient() as client:
                r = await client.post("http://localhost:11434/api/chat", json=payload, timeout=3.0)
                r.raise_for_status()
                resp_json = r.json()
                return resp_json["message"]["content"]

        # Check empty search results gate
        is_empty_search = False
        if intent in ("WEB_SEARCH", "SEARCH"):
            agent_results = self.fsm.working_memory.get("agent_results", [])
            for res in agent_results:
                payload = res.get("payload", {})
                if res.get("status") == "FAILED" or res.get("status") == TaskStatus.FAILED:
                    if payload.get("reason") == "no_results" or "no_results" in str(payload.get("error")):
                        is_empty_search = True
                        break
                elif "results" in payload and not payload["results"]:
                    is_empty_search = True
                    break
            else:
                if not agent_results:
                    is_empty_search = True

        response_text = None
        if is_empty_search:
            logger.info("[CognitiveCore] Empty search results detected. Skipping LLM synthesis.")
            response_text = "No current results found for that query, Sir."
        else:
            try:
                logger.info(f"[CognitiveCore] Attempting Groq synthesis (correlation_id={corr_id})")
                response_text = await run_groq_inference()
                logger.info(f"[CognitiveCore] Groq response: '{response_text}'")
            except Exception as e_groq:
                logger.error(f"[CognitiveCore] Groq synthesis failed: {e_groq}")
                if OLLAMA_AVAILABLE:
                    try:
                        response_text = await call_ollama_fallback()
                    except Exception as e_ollama:
                        logger.error(f"[CognitiveCore] Ollama fallback failed: {e_ollama}")
                
                if response_text is None:
                    response_text = "I encountered an issue processing that. Please try again."

            # Append search attribution URLs if results exist
            if response_text and intent in ("WEB_SEARCH", "SEARCH"):
                agent_results = self.fsm.working_memory.get("agent_results", [])
                urls = []
                for res in agent_results:
                    payload = res.get("payload", {})
                    results_list = payload.get("results", [])
                    for item in results_list:
                        url = item.get("url")
                        if url and url not in urls:
                            urls.append(url)
                if urls:
                    top_urls = urls[:3]
                    attribution = "\n\nSources:\n" + "\n".join(f"- {u}" for u in top_urls)
                    response_text += attribution

        # Store response
        self.fsm.working_memory["response"] = response_text

        # 7. Transition to RESPONDING
        self.fsm.transition_to(AssistantState.RESPONDING, reason="Response synthesized, entering responding phase")

        # Publish response event to client (existing logic)
        response_envelope = EventEnvelope(
            topic="friday.core.response",
            priority=EventPriority.P1,
            source="cognitive_core.orchestrator",
            correlation_id=corr_id,
            session_id=self.fsm.session_id,
            payload={"text": response_text}
        )
        await event_bus.publish(response_envelope)

        # Publish friday.agent.voice.tts_request
        tts_request_payload = {
            "text": response_text,
            "correlation_id": str(corr_id)
        }
        tts_request_envelope = EventEnvelope(
            topic="friday.agent.voice.tts_request",
            priority=EventPriority.P1,
            source="cognitive_core.orchestrator",
            correlation_id=corr_id,
            session_id=self.fsm.session_id,
            payload=tts_request_payload
        )
        await event_bus.publish(tts_request_envelope)

        tts_completed_event = asyncio.Event()

        async def on_tts_complete(env: EventEnvelope) -> None:
            if env.correlation_id == corr_id:
                tts_completed_event.set()

        event_bus.subscribe("friday.agent.voice.tts_complete", on_tts_complete)

        try:
            await asyncio.wait_for(tts_completed_event.wait(), timeout=10.0)
            logger.info(f"[CognitiveCore] TTS playback complete (correlation_id={corr_id})")
        except asyncio.TimeoutError:
            logger.warning(f"[CognitiveCore] TTS playback completion timed out (10s limit) (correlation_id={corr_id})")
        finally:
            event_bus.unsubscribe("friday.agent.voice.tts_complete", on_tts_complete)

        # 8. Transition to REFLECTING
        self.fsm.transition_to(AssistantState.REFLECTING, reason="Entering reflection phase")

        # Build interaction record for memory write
        raw_input = self.fsm.working_memory.get("raw_input", text)
        classified_intent = self.fsm.working_memory.get("intent", "AI_QUERY")
        confidence = self.fsm.working_memory.get("confidence", 1.0)
        agent_results = self.fsm.working_memory.get("agent_results", [])

        import datetime
        now_iso = datetime.datetime.utcnow().isoformat() + "Z"

        interaction_record = {
            "raw_input": raw_input,
            "intent": classified_intent,
            "confidence": confidence,
            "agent_results": agent_results,
            "response": response_text,
            "session_id": str(self.fsm.session_id),
            "correlation_id": str(corr_id),
            "timestamp": now_iso
        }

        # Convert all UUID instances to str to ensure JSON serializability
        try:
            interaction_record = json.loads(json.dumps(interaction_record, cls=UUIDEncoder))
        except Exception as ex:
            logger.error(f"[FSM] Failed to JSON-serialize interaction_record: {ex}")

        memory_envelope = EventEnvelope(
            topic="friday.memory.write",
            priority=EventPriority.P3,
            source="cognitive_core.orchestrator",
            correlation_id=corr_id,
            session_id=self.fsm.session_id,
            payload=interaction_record
        )
        await event_bus.publish(memory_envelope)

        # Record turn in UserProfile
        try:
            from brain.spacy_loader import get_spacy_model
            nlp = get_spacy_model()
            entities_list = []
            if nlp:
                doc = nlp(raw_input)
                entities_list = [ent.text for ent in doc.ents]
                
            from friday.memory.user_profile import user_profile
            from friday.system.context import system_context
            import datetime
            
            asyncio.create_task(
                user_profile.record_turn(
                    intent=classified_intent,
                    entities=entities_list,
                    active_window=system_context.get_context().get("active_window", ""),
                    hour=datetime.datetime.now().hour
                )
            )
        except Exception as e_prof:
            logger.error(f"[FSM] Failed to record turn in user profile: {e_prof}")

        # Update conversation history in session memory
        session = SessionMemory()
        full_history = session.get("conversation_history", app_id=app_id) or []
        full_history.append({"role": "user", "content": raw_input})
        full_history.append({"role": "assistant", "content": response_text})
        
        while (len(json.dumps(full_history)) / 3) > 2000 and len(full_history) > 2:
            full_history = full_history[2:]
            
        session.set("conversation_history", full_history, app_id=app_id)

        # Let the event bus loop run to deliver the event
        await asyncio.sleep(0.05)

        # Clear working_memory (but keep history/session_id)
        self.fsm.working_memory = {}

        # 9. Transition back to IDLE
        self.fsm.transition_to(AssistantState.IDLE, reason="Turn completed successfully")
        logger.info(f"[CognitiveCore] Turn completed successfully (correlation_id={corr_id})")

    async def on_agent_result(self, envelope: EventEnvelope):
        corr_id = envelope.correlation_id
        if self.active_correlation_id is not None and corr_id != self.active_correlation_id:
            logger.info(f"late result discarded for correlation_id {corr_id}")
            return
        if corr_id in self.pending_requests:
            future = self.pending_requests[corr_id]
            if not future.done():
                logger.info(f"[CognitiveCore] Received agent result for correlation_id={corr_id}")
                future.set_result(envelope.payload)

# Global singleton cognitive core
cognitive_core = CognitiveCore()

