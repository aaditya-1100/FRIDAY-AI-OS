"""
Shared async pipeline for CLI and web: wake/context, intent, execute, speak.
Serialized per session to avoid overlapping commands and state races.
"""

import asyncio
import functools
import random
import time
import hashlib
from collections import deque

_recent_speech_hashes = deque(maxlen=20)
_recent_speech_times = {}

def is_duplicate_response(text: str) -> bool:
    """Check if the exact same speech response was triggered within 5 seconds."""
    if not text:
        return False
    h = hashlib.sha256(text.strip().encode("utf-8")).hexdigest()
    now = time.time()
    if h in _recent_speech_times:
        prev_time = _recent_speech_times[h]
        if now - prev_time < 5.0: # 5 second deduplication window
            print(f"[SPEECH DEDUPLICATOR] Ignored duplicate speech response within 5.0s!")
            return True
    _recent_speech_hashes.append(h)
    _recent_speech_times[h] = now
    # Clean up old references from times dict
    for expired_h in list(_recent_speech_times.keys()):
        if now - _recent_speech_times[expired_h] > 10.0:
            _recent_speech_times.pop(expired_h, None)
    return False

from brain.intent_parser import parse_intent
from core.runtime_orchestrator import orchestrator
from brain.planner import PlannerBrain
from core.realtime_emit import emit_json, has_emitters
from core.state_manager import AssistantState, set_state, set_conversational_state, get_conversational_state
from execution.action_executor import execute_action
from voice.speak import speak, cancel_play
from voice.wake_detector import detect_wake_word, remove_wake_word
from brain.context_manager import ContextManager
from memory.short_term import ShortTermMemory
from memory.episodic import EpisodicMemory
from memory.preference import PreferenceMemory
from memory.semantic import SemanticMemory

_EMOTIONAL_SIGNALS = frozenset({
    "long day", "rough day", "bad day", "hard day", "sad", "depressed",
    "tired", "stressed", "exhausted", "happy", "excited", "good news",
    "bad news", "feeling down", "rough week", "long week"
})

def _is_emotional(query: str) -> bool:
    q = query.lower()
    return any(sig in q for sig in _EMOTIONAL_SIGNALS)


def _get_simple_command_intent(q_lower: str) -> dict:
    stripped = q_lower.strip().rstrip("?.! ")
    # Strip conversational filler prefixes (must match _check_simple_command in planner.py)
    for prefix in ("could you ", "can you ", "please ", "hey friday ", "friday "):
        if stripped.startswith(prefix):
            stripped = stripped[len(prefix):].strip()
    # Strip trailing filler
    for suffix in (" please", " for me", " now"):
        if stripped.endswith(suffix):
            stripped = stripped[:-len(suffix)].strip()

    words = stripped.split()
    if not words:
        return {"intent": None}
    
    first = words[0]
    target = " ".join(words[1:]) if len(words) > 1 else ""

    # Strip filler articles from target for open/launch/start commands
    if first in ("open", "start", "launch"):
        filler = {"the", "my", "a", "an", "app", "application", "browser", "website", "site", "web"}
        target_words = [w for w in words[1:] if w not in filler]
        target = " ".join(target_words)
    
    # 1. Applications & Folders Open (Ownership-based Routing)
    if first in ("open", "start", "launch"):
        from system.app_control import is_valid_open_target
        if is_valid_open_target(target):
            return {"intent": "OPEN", "target": target}
        else:
            return {"intent": None}
        
    # 2. Window Controls Close/Minimize/Maximize
    if first == "close":
        if target in ("window", "active window", "current window", "it", "that", ""):
            return {"intent": "WINDOW_CONTROL", "command": "close", "target": ""}
        else:
            return {"intent": "WINDOW_CONTROL", "command": "close", "target": target}
            
    if first == "minimize":
        return {"intent": "WINDOW_CONTROL", "command": "minimize", "target": ""}
        
    if first == "maximize":
        return {"intent": "WINDOW_CONTROL", "command": "maximize", "target": ""}
        
    # 3. System Controls
    if stripped in ("shutdown", "shutdown pc", "shutdown computer"):
        return {"intent": "WINDOW_CONTROL", "command": "shutdown"}
        
    if stripped in ("restart", "restart pc", "restart computer"):
        return {"intent": "WINDOW_CONTROL", "command": "restart"}
        
    if stripped in ("sleep", "sleep pc", "sleep computer", "hibernate"):
        return {"intent": "WINDOW_CONTROL", "command": "sleep"}
        
    if stripped in ("lock", "lock pc", "lock computer", "lock screen"):
        return {"intent": "WINDOW_CONTROL", "command": "lock"}
        
    # 4. Screenshot
    if "screenshot" in stripped or "screen capture" in stripped:
        return {"intent": "SCREENSHOT"}
        
    # 5. Media Controls & Volume
    if "volume" in stripped:
        if "up" in stripped or "louder" in stripped or "increase" in stripped or "turn it up" in stripped:
            return {"intent": "SPOTIFY_CONTROL", "command": "volume_up"}
        if "down" in stripped or "quieter" in stripped or "decrease" in stripped or "turn it down" in stripped:
            return {"intent": "SPOTIFY_CONTROL", "command": "volume_down"}
            
    if stripped in ("mute", "silence", "pause", "pause music"):
        return {"intent": "SPOTIFY_CONTROL", "command": "pause"}
        
    if stripped in ("unmute", "resume", "play", "play music"):
        return {"intent": "SPOTIFY_CONTROL", "command": "play"}
        
    return {"intent": "AI_QUERY", "query": q_lower}

_TASK_INTENTS = frozenset({
    "OPEN", "SEARCH", "PLAY_MEDIA", "SCREENSHOT", "SYSTEM_STATUS",
    "SPOTIFY_CONTROL", "MAP", "MAP_ROUTE", "MAP_FOLLOWUP", "WINDOW_CONTROL", "SET_REMINDER",
    "SET_TIMER", "STOPWATCH_CONTROL", "SET_ALARM", "SET_SCHEDULED_TASK",
    "SET_RECURRING_REMINDER", "LIST_REMINDERS", "CANCEL_REMINDER"
})

short_term_memory = ShortTermMemory()
episodic_memory = EpisodicMemory()
preference_memory = PreferenceMemory()
semantic_memory = SemanticMemory()
context_manager = ContextManager()
planner = PlannerBrain()

# Single-flight guard: one transcript at a time (CLI + web share process).
_process_lock = asyncio.Lock()

# =========================================
# SESSION STATE (CLI + web share defaults)
# =========================================

is_speaking      = False
active           = False
last_query       = ""
_speak_cancelled = False   # set by cancel_speak() to interrupt TTS mid-flight
_last_interaction_time = 0.0

STARTUP_MESSAGE = "FRIDAY online sir"

WAKE_RESPONSES = [
    "I'm listening sir",
    "Ready sir",
    "Yes sir",
]

EXIT_WORDS = [
    "bye",
    "goodbye",
    "sleep",
    "stop listening",
    "go idle",
]

# Prefixes with trailing space to avoid false positives (e.g. "android").
CONTEXT_PREFIXES = (
    "and ",
    "also ",
    "then ",
    "what about ",
    "its ",
    "their ",
)

# Conversational presence check-ins — instant response, bypass full pipeline.
_PRESENCE_GREETINGS = frozenset({
    "are you there", "you there", "hey friday", "friday you there",
    "you listening", "are you listening", "hey", "hello", "hi",
    "you awake", "are you awake", "still there", "you still there",
    "are you here", "sup", "yo", "friday"
})

_PRESENCE_ACKS = frozenset({
    "hmm", "okay", "thanks", "thank you", "got it", "gotcha",
    "anytime", "perfect", "good job", "thanks buddy", "awesome",
    "no problem", "sure thing", "cool", "alright"
})

_PRESENCE_GREETING_REPLIES = [
    "Yeah sir.", "I'm here.", "Right here sir.", "At your service.",
    "Listening sir.", "I'm here sir.", "Yes sir."
]

_PRESENCE_ACK_REPLIES = [
    "Got you.", "Anytime sir.", "On it.", "Right away.",
    "My pleasure sir.", "Indeed sir.", "Exactly."
]

_PRESENCE_PATTERNS = _PRESENCE_GREETINGS | _PRESENCE_ACKS
_PRESENCE_REPLIES = _PRESENCE_GREETING_REPLIES + _PRESENCE_ACK_REPLIES


def apply_context(query: str) -> str:
    global last_query
    q = (query or "").strip()
    if last_query and any(q.startswith(p) for p in CONTEXT_PREFIXES):
        return last_query + " " + q
    return q


def cancel_speak() -> None:
    """Signal the current TTS to stop immediately (thread-safe)."""
    global _speak_cancelled, is_speaking
    _speak_cancelled = True
    is_speaking = False
    cancel_play()           # stop pygame immediately from any thread
    
    # Emit cancel_audio event to WebSocket clients
    from core.realtime_emit import emit_json_sync
    emit_json_sync({"type": "cancel_audio"})
    
    from voice.listen import is_mic_enabled
    target_state = AssistantState.LISTENING if is_mic_enabled() else AssistantState.IDLE
    set_state(target_state)
    # Microphone activation must happen only through the main listening lifecycle.
    pass


_original_spotify_volume = None

def duck_spotify():
    global _original_spotify_volume
    try:
        from system.spotify_control import _spotify_client
        if _spotify_client.is_configured and _spotify_client._token_info:
            devices = _spotify_client.get_devices()
            active_device = next((d for d in devices if d.get("is_active")), None)
            if active_device:
                current_vol = active_device.get("volume_percent", 50)
                _original_spotify_volume = current_vol
                duck_vol = max(10, int(current_vol * 0.3))
                print(f"[AUDIO DUCKING] Ducking Spotify volume from {current_vol}% to {duck_vol}%")
                _spotify_client.set_volume(duck_vol)
    except Exception as e:
        print(f"[AUDIO DUCKING WARNING] Failed to duck Spotify volume: {e}")

def unduck_spotify():
    global _original_spotify_volume
    try:
        from system.spotify_control import _spotify_client
        if _original_spotify_volume is not None and _spotify_client.is_configured and _spotify_client._token_info:
            print(f"[AUDIO DUCKING] Restoring Spotify volume to {_original_spotify_volume}%")
            _spotify_client.set_volume(_original_spotify_volume)
            _original_spotify_volume = None
    except Exception as e:
        print(f"[AUDIO DUCKING WARNING] Failed to unduck Spotify volume: {e}")


async def safe_speak(text: str, web_mode: bool | None = None) -> None:
    """Speak text via WS audio (web_mode=True) or local pygame (False).
    Pass web_mode=None to auto-detect based on active WS clients."""
    global is_speaking, _speak_cancelled
    import uuid
    response_id = str(uuid.uuid4())[:8]
    mic_was_enabled = False  # Initialize early so finally block never hits UnboundLocalError
    
    try:
        if not text:
            print(f"[TRACE] [SPEAK] [{response_id}] safe_speak received empty text, skipping")
            return
        text = str(text).strip()
        if not text:
            print(f"[TRACE] [SPEAK] [{response_id}] safe_speak received whitespace-only text, skipping")
            return

        if is_duplicate_response(text):
            print(f"[TRACE] [SPEAK] [{response_id}] Deduplicator triggered, ignoring duplicate speech response.")
            return

        if web_mode is None:
            web_mode = has_emitters()

        print(f"[TRACE] [SPEAK] [{response_id}] ENTERED SAFE_SPEAK | text='{text[:80]}...' | web_mode={web_mode} | text_len={len(text)}")
        print(f"[E2E_TRACE] [STAGE 9: Response Generated] PASS. Text response formulated: '{text[:80]}...' | web_mode={web_mode} | response_id={response_id}", flush=True)

        if _speak_cancelled:
            print(f"[TRACE] [SPEAK] [{response_id}] Clearing stale _speak_cancelled flag — was set by previous cancel")
            _speak_cancelled = False

        is_speaking = True
        set_state(AssistantState.SPEAKING)
        print(f"[TRACE] [SPEAK] [{response_id}] STATE SET TO SPEAKING | web_mode={web_mode}")
        print(f"[TRACE] [SPEAK] [{response_id}] Emitting speak event via websocket...")
        await emit_json({"type": "speak", "text": text})
        print(f"[TRACE] [SPEAK] [{response_id}] Speak event emitted successfully")

        if _speak_cancelled:
            print(f"[TRACE] [SPEAK] [{response_id}] Cancelled mid-emit — skipping audio")
            return
            
        # Duck Spotify volume if playing
        duck_spotify()
        print(f"[TRACE] [SPEAK] [{response_id}] Spotify ducking complete")
        
        # Release microphone to allow Bluetooth device to switch to high-fidelity A2DP Stereo mode
        from voice.listen import is_mic_enabled, set_mic_enabled, request_stop
        mic_was_enabled = is_mic_enabled()
        if mic_was_enabled:
            print(f"[BLUETOOTH HFP FIX] [{response_id}] Disabling mic stream to unlock A2DP Stereo mode")
            set_mic_enabled(False)
            # Re-enforce SPEAKING state because set_mic_enabled(False) overrides it to IDLE
            set_state(AssistantState.SPEAKING, force=True)
            # NOTE: Removed 1.5s asyncio.sleep here. The delay caused state drift from SPEAKING
            # to LISTENING (listen loop timeout fires) during the wait window, causing the
            # subsequent TTS synthesis result to be discarded by the old state check.
        
        try:
            print(f"[TRACE] [SPEAK] [{response_id}] CALLING voice.speak.speak(...) with response_id")
            await speak(text, web_mode=web_mode, response_id=response_id)
            print(f"[TRACE] [SPEAK] [{response_id}] voice.speak.speak(...) returned successfully")
        except Exception as e_speak:
            print(f"[TRACE] [SPEAK] [{response_id}] speak call failed: {e_speak}")
            raise e_speak

    except asyncio.CancelledError:
        print(f"[TRACE] [SPEAK] [{response_id}] safe_speak task cancelled")
        cancel_play()
        raise
    except Exception as e:
        print(f"[TRACE] [SPEAK] [{response_id}] EXCEPTION: {e}")
        print(f"[SPEAK ERROR] [{response_id}] {type(e).__name__}: {e}")
    finally:
        # Release state FIRST to minimize lock-hold duration, then unduck Spotify
        # in a non-blocking background task. Previously, the Spotify API call during
        # unduck held the lock for 500ms-2s, causing first-attempt command failures.
        _speak_cancelled = False
        is_speaking = False
        
        # Restore microphone stream if it was active before voice playback
        if mic_was_enabled:
            print(f"[BLUETOOTH HFP FIX] [{response_id}] Restoring mic stream context after 0.8s stabilization delay...")
            await asyncio.sleep(0.8)
            from voice.listen import reset_stop, set_mic_enabled
            reset_stop()
            set_mic_enabled(True)
            
        from voice.listen import is_mic_enabled
        target_idle_state = AssistantState.LISTENING if is_mic_enabled() else AssistantState.IDLE
        set_state(target_idle_state)
        print(f"[TRACE] [SPEAK] [{response_id}] STATE SET TO {target_idle_state} | SPEAK FINISHED")
        # Non-blocking Spotify unduck — fire and forget to avoid holding the pipeline lock
        try:
            import threading
            threading.Thread(target=unduck_spotify, daemon=True).start()
        except Exception as e_unduck:
            print(f"[TRACE] [SPEAK] [{response_id}] Unduck background thread failed: {e_unduck}")
            unduck_spotify()  # Fallback to synchronous
        print(f"[TRACE] [SPEAK] [{response_id}] SAFE_SPEAK COMPLETE")


async def process_transcript(raw_query: str, *, web_mode: bool | None = None, is_voice: bool = False) -> None:
    """
    Process one user utterance from mic or web UI.
    web_mode=None (default) → auto-detect: True if WS clients connected, else False.
    This ensures mic speech works correctly whether frontend is open or not.
    """
    global active, last_query, _last_interaction_time
    import time
    _last_interaction_time = time.time()
    print(f"[E2E_TRACE] [STAGE 6: process_transcript Called] raw_query='{raw_query}' | web_mode={web_mode}", flush=True)

    # Auto-detect web_mode: if any WS client is connected, treat as web session
    # so the active-gate bypass works correctly for the packaged app.
    if web_mode is None:
        web_mode = has_emitters()

    query = (raw_query or "").lower().strip()
    if not query:
        print("[TRACE] [PIPELINE] Empty transcript received. Aborting.")
        return

    # ── INSTANT VISUAL FEEDBACK: emit transcript + THINKING before any gate checks ──
    # User must see immediate reaction as soon as their voice is received.
    await emit_json({"type": "transcript", "text": raw_query})
    set_state(AssistantState.THINKING)

    # Increment active generation ID to cancel any stale sessions or audio streams
    orchestrator.increment_generation()

    # Update Layer 1 Passive Visual Context Awareness silently in the backend
    try:
        context_manager.update_passive_visual_context()
    except Exception as e_pass:
        print(f"[AMBIENT WARNING] Failed updating passive visual context: {e_pass}")

    # ── Task isolation: cancel any in-flight TTS from previous request ────
    if is_speaking:
        print("[TRACE] [PIPELINE] New request received — cancelling stale TTS")
        cancel_speak()

    if _process_lock.locked():
        # Lock is held (system is in THINKING or EXECUTING state).
        # We must allow critical interruption control commands to cancel execution,
        # but discard any duplicate launches or general command queries.
        control_keywords = ("stop", "cancel", "interrupt", "never mind", "be quiet")
        if any(kw in query for kw in control_keywords):
            print(f"[TRACE] [PIPELINE] Lock is active, but control command '{query}' detected. Cancelling active execution tasks and speak...")
            cancel_speak()
            try:
                current_task = asyncio.current_task()
                all_tasks = asyncio.all_tasks()
                cancelled_count = 0
                for task in all_tasks:
                    if task is current_task:
                        continue
                    coro_name = str(task.get_coro()).lower()
                    is_execution_task = "process_transcript" in coro_name or "_run_command" in coro_name or "realtime_web_query" in coro_name
                    if is_execution_task:
                        print(f"[TRACE] [PIPELINE] Cancelling active execution task: {task.get_name()} -> {coro_name}")
                        task.cancel()
                        cancelled_count += 1
                if cancelled_count > 0:
                    print(f"[TRACE] [PIPELINE] Successfully cancelled {cancelled_count} active execution task(s).")
            except Exception as e_cancel:
                print(f"[TRACE] [PIPELINE] Error cancelling active execution tasks: {e_cancel}")
            
            # Immediately force release backend state to IDLE or LISTENING
            from voice.listen import is_mic_enabled
            target_state = AssistantState.LISTENING if is_mic_enabled() else AssistantState.IDLE
            set_state(target_state, force=True)
            return
        else:
            print(f"[TRACE] [PIPELINE] Lock is active. Command '{raw_query}' received but system is busy — discarding to prevent lag.")
            # Reset state so the orb doesn't stay stuck on THINKING
            from voice.listen import is_mic_enabled
            busy_state = AssistantState.LISTENING if is_mic_enabled() else AssistantState.IDLE
            set_state(busy_state)
            # Give user feedback that their command was heard but system is busy
            await emit_json({"type": "hint", "text": "One moment sir, still processing..."})
            return

    async with _process_lock:
        task_id = orchestrator.register_task("process_transcript")
        try:
            print(f"[TRACE] [PIPELINE] process_transcript entered with raw='{raw_query}' | web_mode={web_mode}")

            query = raw_query.lower().strip()
            print("[TRACE] [PIPELINE] Stage: detect_wake_word checking...")
            if detect_wake_word(raw_query):
                print("[TRACE] [PIPELINE] Wake word 'Friday' detected!")
                print(f"[E2E_TRACE] [WAKE_WORD_CHECK] PASS. Wake word 'Friday' detected.", flush=True)
                cleaned_without_wake = remove_wake_word(raw_query).strip()
                _last_interaction_time = time.time()
                
                if not active:
                    active = True
                    print("[TRACE] [PIPELINE] Activation complete.")
                    print("[E2E_TRACE] [WAKE_WORD_CHECK] PASS. Activation complete (active=True).", flush=True)
                
                # If standalone wake word, always respond
                if not cleaned_without_wake:
                    print("[E2E_TRACE] [STAGE 9: Response Generated] Standalone wake word response triggered.", flush=True)
                    await safe_speak(random.choice(WAKE_RESPONSES))
                    print("[TRACE] [PIPELINE] Standalone wake word processed. Exiting process_transcript.")
                    return
                
                query = cleaned_without_wake.lower().strip()
                print(f"[TRACE] [PIPELINE] Query after wake-word removal: '{query}'")

            if not active and (is_voice or not web_mode):
                print(f"[TRACE] [PIPELINE] Assistant inactive and wake word required (is_voice={is_voice}, web_mode={web_mode}). Emitting UI wake hint.")
                print(f"[E2E_TRACE] [WAKE_WORD_CHECK] FAIL. Assistant inactive. is_voice={is_voice} | web_mode={web_mode}. Wake word required.", flush=True)
                # Emit a UI hint so the user knows FRIDAY is waiting for wake word.
                await emit_json({"type": "hint", "text": "Say 'Friday' to wake me up"})
                return

            if any(word in query for word in EXIT_WORDS):
                print("[TRACE] [PIPELINE] Exit word detected! Going idle.")
                active = False
                await safe_speak("Going idle sir")
                short_term_memory.add("user", query)
                short_term_memory.add("assistant", "Going idle sir")
                return

            # ── Conversational presence fast-path (< 10ms) ──────────────
            cleaned_query = query.lower().rstrip("?!. ").strip()
            if cleaned_query in _PRESENCE_GREETINGS:
                reply = random.choice(_PRESENCE_GREETING_REPLIES)
                print(f"[TRACE] [PIPELINE] Presence greeting fast-path: '{query}' → '{reply}'")
                print(f"[E2E_TRACE] [STAGE 9: Response Generated] PASS. Fast-path greeting reply triggered: '{reply}'", flush=True)
                await safe_speak(reply)
                short_term_memory.add("user", query)
                short_term_memory.add("assistant", reply)
                return

            if cleaned_query in _PRESENCE_ACKS:
                reply = random.choice(_PRESENCE_ACK_REPLIES)
                print(f"[TRACE] [PIPELINE] Presence ack fast-path: '{query}' → '{reply}'")
                print(f"[E2E_TRACE] [STAGE 9: Response Generated] PASS. Fast-path ack reply triggered: '{reply}'", flush=True)
                await safe_speak(reply)
                short_term_memory.add("user", query)
                short_term_memory.add("assistant", reply)
                return

            print(f"[TRACE] [PIPELINE] Stage: PlannerBrain analyzing query='{query}'...")
            print(f"[E2E_TRACE] [STAGE 7: Planner Invoked] routing/planning started for: '{query}'", flush=True)
            # Let the PlannerBrain analyze the query, resolve references, and suggest the target brain
            plan = planner.plan(query, context_manager, preference_memory, episodic_memory)
            query = plan.enriched_query
            print(f"[TRACE] [PIPELINE] PlannerBrain output: target_brain={plan.target_brain} | enriched_query='{query}'")
            print(f"[E2E_TRACE] [STAGE 7: Planner Invoked] PASS. target_brain='{plan.target_brain}' | enriched_query='{query}'", flush=True)

            # Determine and set initial conversational state
            if _is_emotional(query):
                set_conversational_state(AssistantState.EMOTIONAL_CONTEXT)
            elif plan.target_brain in ("RETRIEVAL", "WEATHER", "NEWS"):
                set_conversational_state(AssistantState.RETRIEVAL_MODE)
            else:
                set_conversational_state(AssistantState.CASUAL_CHAT)

            # Update ContextManager with raw query + intent hint BEFORE intent parsing.
            # The graph extracts entities from raw text (preserves casing for proper nouns).
            context_manager.update(raw_query, intent=None)

            # apply_context uses last_query for prefix continuation.
            # Store the topic-resolved query (before prefix expansion) so the NEXT
            # turn's prefix check resolves against the actual last topic, not the
            # already-expanded concatenation which would grow unboundedly.
            last_query = query
            query = apply_context(query)
            print(f"[TRACE] [PIPELINE] Query after context resolution: '{query}'")

            print(f"[STATE] THINKING — Parsed query: '{query}'")
            set_state(AssistantState.THINKING)

            print("[TRACE] [PIPELINE] Emitting websocket thinking event...")
            # Emit a thinking event with brain routing info so the frontend orb responds instantly
            await emit_json({
                "type": "thinking",
                "brain": plan.target_brain,
                "priority": plan.priority,
                "freshness": plan.requires_freshness,
                "clarification": plan.requires_clarification,
                "multi_task": plan.is_multi_task
            })

            if getattr(plan, "is_simple_command", False):
                print(f"[TRACE] [PIPELINE] Bypassing IntentParser LLM for direct simple command: '{query}'")
                intent_data = _get_simple_command_intent(query)
            else:
                print(f"[TRACE] [PIPELINE] Stage: IntentParser dispatching query='{query}' to Groq (llama-3.3-70b-versatile)...")
                # parse_intent calls ask_groq (blocking I/O) — run in thread pool with strict 10s async timeout
                loop = asyncio.get_running_loop()
                try:
                    intent_data = await asyncio.wait_for(
                        loop.run_in_executor(
                            None,
                            functools.partial(
                                parse_intent,
                                query,
                                short_term_memory.get(),
                                preference_memory.preferences,
                                semantic_memory.knowledge,
                                episodic_memory.events,
                                plan.target_brain
                            )
                        ),
                        timeout=10.0
                    )
                except asyncio.TimeoutError:
                    print("[TRACE] [PIPELINE] IntentParser timed out after 10.0s! Applying resilient keyword fallback.")
                    print("[E2E_TRACE] [STAGE 8: Intent Generated] WARNING. IntentParser timed out. Applying fallback.", flush=True)
                    from brain.intent_parser import _keyword_fallback, validate_intent_sanity
                    intent_data = _keyword_fallback(query, short_term_memory.get())
                    intent_data["query"] = query
                    intent_data = validate_intent_sanity(intent_data, query, plan.target_brain)
            intent = intent_data.get("intent")
            print(f"[TRACE] [PIPELINE] IntentParser resolved intent: {intent} | intent_data={intent_data}")
            print(f"[E2E_TRACE] [STAGE 8: Intent Generated] PASS. Resolved intent: '{intent}' | intent_data={intent_data}", flush=True)

            # ── Post-LLM safety net: LLM sometimes misclassifies "open X" ────
            # as WINDOW_CONTROL with command="open" instead of OPEN intent.
            # Correct this deterministically to prevent routing inconsistency.
            if intent == "WINDOW_CONTROL" and str(intent_data.get("command", "")).lower() == "open":
                corrected_target = intent_data.get("target", "")
                print(f"[TRACE] [PIPELINE] SAFETY NET: Correcting WINDOW_CONTROL+open → OPEN for target='{corrected_target}'")
                intent_data["intent"] = "OPEN"
                intent_data["target"] = corrected_target
                intent = "OPEN"

            # ── Phase 2: Confidence Core Integration ──
            from brain.confidence_engine import confidence_engine
            from brain.routing_telemetry import telemetry_engine
            import sys

            # Calculate raw component scores dynamically based on execution flow
            components_score = {
                "asr": 0.98 if len(query) > 3 else 0.40,
                "intent": 0.30 if intent_data.get("_quota_limited") else (0.75 if getattr(plan, "is_simple_command", False) or "timed out" in sys.argv else 0.96),
                "domain": 0.95 if intent else 0.30,
                "routing": 0.95 if plan.target_brain != "LLM" or intent == "AI_QUERY" else 0.80,
                "memory": 0.90 if "it" not in query and "that" not in query else 0.50,
                "execution": 0.98
            }
            conf_res = confidence_engine.calculate_unified_confidence(intent, components_score)
            unified_score = conf_res["unified_score"]
            policy = conf_res["policy"]
            print(f"[PIPELINE CONFIDENCE] Unified Turn Confidence: {unified_score:.4f} | Policy: {policy} | Action: {conf_res['action']}")

            # Telemetry Turn Logging Setup
            state_str = str(get_conversational_state())
            latency_ms = int((time.time() - _last_interaction_time) * 1000)
            
            trigger_matrix = [
                {
                    "name": plan.target_brain,
                    "semantic_intent_score": components_score["intent"],
                    "capability_confidence": components_score["execution"],
                    "historical_reliability": 0.95,
                    "priority_weight": 1.0,
                    "final_score": unified_score
                }
            ]
            
            telemetry_id = telemetry_engine.log_turn(
                query=query,
                system_state=state_str,
                winner=plan.target_brain,
                runner_up="LLM" if plan.target_brain != "LLM" else "RETRIEVAL",
                winning_score=unified_score,
                runner_up_score=0.40,
                margin=float(round(unified_score - 0.40, 4)),
                is_tiebreak_invoked=getattr(plan, "is_tiebreak_invoked", False),
                confidence_score=unified_score,
                latency_ms=latency_ms,
                trigger_matrix=trigger_matrix,
                confidence_breakdown=components_score
            )

            # Confidence Policy Enforcement
            if policy == "LOW":
                print(f"[PIPELINE CONFIDENCE] Low confidence block! Prompting active clarification.")
                clarification_msg = "I'm not entirely sure I understood that command, Sir. Could you please clarify?"
                await safe_speak(clarification_msg)
                short_term_memory.add("user", query)
                short_term_memory.add("assistant", clarification_msg)
                telemetry_engine.register_correction(telemetry_id, 0.0)
                await emit_json({"type": "result", "ok": False, "reason": "low_confidence", "intent": intent})
                return

            # If quota-limited and intent is AI/REALTIME (not a command), speak the quota message now
            if intent_data.get("_quota_limited") and intent in ("AI_QUERY", "REALTIME_QUERY", None):
                from llm.groq_client import ask_groq as _ask_groq_quota
                # Get the retry time from a fresh quota check attempt to give accurate feedback
                print("[TRACE] [PIPELINE] Quota-limited conversational query — speaking quota message")
                quota_msg = "My thinking engine needs a short breather sir. Ask me again in a minute."
                await safe_speak(quota_msg)
                short_term_memory.add("user", query)
                short_term_memory.add("assistant", quota_msg)
                return

            # Update context with resolved intent so follow-up detection works immediately.
            context_manager.update(raw_query, intent=intent)

            # If resolved intent represents an operational task, shift to TASK_MODE
            if intent in _TASK_INTENTS and get_conversational_state() != AssistantState.EMOTIONAL_CONTEXT:
                set_conversational_state(AssistantState.TASK_MODE)

            if not intent:
                # Don't silently ignore — give the user feedback.
                print("[TRACE] [PIPELINE] No valid intent parsed — speaking fallback feedback")
                await safe_speak("I didn't quite catch that sir. Could you repeat?")
                return

            # Update context with resolved intent for follow-up awareness
            context_manager.last_intent = intent

            set_state(AssistantState.EXECUTING)

            print(f"[TRACE] [PIPELINE] Stage: ActionExecutor executing intent='{intent}'...")
            result = await execute_action(intent_data, short_term_memory)
            print(f"[TRACE] [PIPELINE] ActionExecutor execution complete. result={result}")

            # Update context graph from execution result (captures video titles, track names, etc.)
            # This enables follow-ups like "play it again" after "playing Mark Rober video"
            try:
                context_manager.update_from_result(intent or "", result)
            except Exception as _ctx_err:
                print(f"[CTX_GRAPH] update_from_result error: {_ctx_err}")

            spoken_response = "Done sir"
            variant = None

            if not result:
                print(f"[TRACE] [PIPELINE] Action execution failed or returned False.")
                spoken_response = "I could not do that sir"
                print(f"[TRACE] [PIPELINE] Speaking execution failure feedback...")
                await safe_speak(spoken_response)
                short_term_memory.add("user", query)
                short_term_memory.add("assistant", spoken_response)
                episodic_memory.log_event(query, intent, False, intent_data)
                telemetry_engine.register_correction(telemetry_id, 0.0)
                from brain.trigger_intelligence import trigger_intel_mgr
                trigger_intel_mgr.register_feedback(plan.target_brain, success=False)
                print(f"[TRACE] [PIPELINE] Emitting websocket execution failure event...")
                await emit_json({"type": "result", "ok": False, "reason": "execute_failed", "intent": intent})
                return

            if isinstance(result, dict) and result.get("type") == "ai_response":
                spoken_response = result.get("response")
                print(f"[STATE] LLM_RESPONSE — Response generated: '{spoken_response}'")
                variant = "ai_response"
            elif intent == "MULTI_ACTION":
                spoken_response = "Done sir"
            elif intent == "SEARCH":
                platform = intent_data.get("platform", "YouTube") or "YouTube"
                q = intent_data.get("query", "")
                spoken_response = f"Searching {platform} for {q} sir" if q else f"Opening {platform} sir"
            elif intent == "PLAY_MEDIA":
                q = intent_data.get("query", "")
                spoken_response = f"Playing {q} sir" if q else "Playing now sir"
            elif intent == "WEB_SEARCH":
                q = intent_data.get("query", "")
                spoken_response = f"Searching Google for {q} sir" if q else "Searching Google sir"
            elif intent == "OPEN":
                target = intent_data.get("target", "")
                spoken_response = f"Opening {target} sir" if target else "Done sir"
            else:
                spoken_response = "Done sir"

            print(f"[TRACE] [PIPELINE] Stage: TTS/safe_speak emitting spoken_response='{spoken_response[:80]}'...")
            await safe_speak(spoken_response)
            short_term_memory.add("user", query)
            short_term_memory.add("assistant", spoken_response)
            
            # Log successful execution to memory
            print(f"[TRACE] [PIPELINE] Logging successful event to episodic memory...")
            episodic_memory.log_event(query, intent, True, intent_data)
            telemetry_engine.register_success(telemetry_id)
            from brain.trigger_intelligence import trigger_intel_mgr
            trigger_intel_mgr.register_feedback(plan.target_brain, success=True)
            if intent == "OPEN":
                target = intent_data.get("target")
                if target:
                    preference_memory.update_favorite_app(target)

            print("[TRACE] [PIPELINE] Stage: finished execution, emitting success result...")
            print("[STATE] FINISHED — Pipeline execution complete.")
            emit_payload = {"type": "result", "ok": True, "intent": intent}
            if variant:
                emit_payload["variant"] = variant
            await emit_json(emit_payload)

        except asyncio.CancelledError:
            print("[TRACE] [PIPELINE] process_transcript execution was CANCELLED.")
            raise
        except Exception as e:
            print(f"[TRACE] [PIPELINE] Pipeline encountered fatal exception: {e}")
            print(f"[STATE] ERROR — Pipeline execution failed: {e}")
            set_state(AssistantState.ERROR)
            print("[TRACE] [PIPELINE] Emitting pipeline error event...")
            await emit_json({"type": "result", "ok": False, "reason": "pipeline_error", "detail": str(e)[:200]})
            try:
                await safe_speak("Something went wrong sir")
            except Exception:
                pass
        finally:
            orchestrator.deregister_task(task_id)
            context_manager.clear_expired_payloads()
            if not is_speaking:
                from voice.listen import is_mic_enabled
                target_idle_state = AssistantState.LISTENING if is_mic_enabled() else AssistantState.IDLE
                set_state(target_idle_state)
                # Trigger proactive low-entropy cleanup when returning to IDLE
                try:
                    from core.runtime_stability import get_stability_manager
                    mgr = get_stability_manager()
                    mgr.clean_orphaned_tasks()
                    mgr.reclaim_memory()
                except Exception as e_clean:
                    print(f"[JANITOR PROACTIVE WARNING] Proactive IDLE cleanup exception: {e_clean}")


def set_web_session_active(value: bool = True) -> None:
    global active, _last_interaction_time
    active = value
    if value:
        import time
        _last_interaction_time = time.time()
