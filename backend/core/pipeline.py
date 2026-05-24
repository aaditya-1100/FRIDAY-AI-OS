"""
Shared async pipeline for CLI and web: wake/context, intent, execute, speak.
Serialized per session to avoid overlapping commands and state races.
"""

import asyncio
import functools
import random

from brain.intent_parser import parse_intent
from core.realtime_emit import emit_json, has_emitters
from core.state_manager import AssistantState, set_state
from execution.action_executor import execute_action
from voice.speak import speak, cancel_play
from voice.wake_detector import detect_wake_word, remove_wake_word
from brain.context_manager import ContextManager
from memory.short_term import ShortTermMemory
from memory.episodic import EpisodicMemory
from memory.preference import PreferenceMemory
from memory.semantic import SemanticMemory

short_term_memory = ShortTermMemory()
episodic_memory = EpisodicMemory()
preference_memory = PreferenceMemory()
semantic_memory = SemanticMemory()
context_manager = ContextManager()

# Single-flight guard: one transcript at a time (CLI + web share process).
_process_lock = asyncio.Lock()

# =========================================
# SESSION STATE (CLI + web share defaults)
# =========================================

is_speaking      = False
active           = False
last_query       = ""
_speak_cancelled = False   # set by cancel_speak() to interrupt TTS mid-flight

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
    set_state(AssistantState.IDLE)


async def safe_speak(text: str, web_mode: bool | None = None) -> None:
    """Speak text via WS audio (web_mode=True) or local pygame (False).
    Pass web_mode=None to auto-detect based on active WS clients."""
    global is_speaking, _speak_cancelled
    try:
        if not text:
            return
        text = str(text).strip()
        if not text:
            return

        # Auto-detect delivery mode: WS if frontend connected, pygame otherwise.
        if web_mode is None:
            web_mode = has_emitters()

        # Clear any stale cancellation from a previous stop_speaking.
        # Do NOT exit here — a stale flag must not silently drop the next response.
        if _speak_cancelled:
            print("[SPEAK] Clearing stale _speak_cancelled flag — was set by previous cancel")
            _speak_cancelled = False

        is_speaking = True
        set_state(AssistantState.SPEAKING)
        print(f"[STATE] SPEAKING | web_mode={web_mode} | text='{text[:80]}'")
        await emit_json({"type": "speak", "text": text})

        if _speak_cancelled:
            print("[SPEAK] Cancelled mid-emit — skipping audio")
            return
        await speak(text, web_mode=web_mode)

    except asyncio.CancelledError:
        cancel_play()
        raise
    except Exception as e:
        print(f"[SPEAK ERROR] {type(e).__name__}: {e}")
    finally:
        _speak_cancelled = False
        is_speaking = False
        set_state(AssistantState.IDLE)
        print("[STATE] IDLE — speak finished")


async def process_transcript(raw_query: str, *, web_mode: bool | None = None) -> None:
    """
    Process one user utterance from mic or web UI.
    web_mode=None (default) → auto-detect: True if WS clients connected, else False.
    This ensures mic speech works correctly whether frontend is open or not.
    """
    global active, last_query

    # Auto-detect web_mode: if any WS client is connected, treat as web session
    # so the active-gate bypass works correctly for the packaged app.
    if web_mode is None:
        web_mode = has_emitters()

    query = (raw_query or "").lower().strip()
    if not query:
        return

    async with _process_lock:
        try:
            print(f"[TRANSCRIBED] raw='{raw_query}' | web_mode={web_mode}")
            await emit_json({"type": "transcript", "text": raw_query})

            if detect_wake_word(query):
                if not active:
                    active = True
                    await safe_speak(random.choice(WAKE_RESPONSES))
                query = remove_wake_word(query).strip()
                if not query:
                    return

            if not active and not web_mode:
                # Emit a UI hint so the user knows FRIDAY is waiting for wake word.
                await emit_json({"type": "hint", "text": "Say 'Friday' to wake me up"})
                return

            if any(word in query for word in EXIT_WORDS):
                active = False
                await safe_speak("Going idle sir")
                short_term_memory.add("user", query)
                short_term_memory.add("assistant", "Going idle sir")
                return

            # Resolve pronoun references using enriched context first (against previous history)
            query = context_manager.enrich_query(query)
            if query != (raw_query or "").lower().strip():
                print(f"[CONTEXT] Enriched query: '{query}'")

            # Update ContextManager with raw query (preserves casing for entity extraction of this turn)
            context_manager.update(raw_query)

            # apply_context uses last_query for prefix continuation.
            # Store the topic-resolved query (before prefix expansion) so the NEXT
            # turn's prefix check resolves against the actual last topic, not the
            # already-expanded concatenation which would grow unboundedly.
            last_query = query
            query = apply_context(query)

            print(f"[STATE] THINKING — Parsed query: '{query}'")
            set_state(AssistantState.THINKING)

            # parse_intent calls ask_groq (blocking I/O) — run in thread pool
            loop = asyncio.get_running_loop()
            intent_data = await loop.run_in_executor(
                None,
                functools.partial(
                    parse_intent,
                    query,
                    short_term_memory.get(),
                    preference_memory.preferences,
                    semantic_memory.knowledge,
                    episodic_memory.events
                )
            )
            intent = intent_data.get("intent")

            if not intent:
                # Don't silently ignore — give the user feedback.
                print("[PIPELINE] No valid intent parsed — speaking fallback")
                await safe_speak("I didn't quite catch that sir. Could you repeat?")
                return

            # Update context with resolved intent for follow-up awareness
            context_manager.last_intent = intent

            set_state(AssistantState.EXECUTING)

            result = await execute_action(intent_data, short_term_memory)

            spoken_response = "Done sir"
            variant = None

            if not result:
                spoken_response = "I could not do that sir"
                await safe_speak(spoken_response)
                short_term_memory.add("user", query)
                short_term_memory.add("assistant", spoken_response)
                episodic_memory.log_event(query, intent, False, intent_data)
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

            await safe_speak(spoken_response)
            short_term_memory.add("user", query)
            short_term_memory.add("assistant", spoken_response)
            
            # Log successful execution to memory
            episodic_memory.log_event(query, intent, True, intent_data)
            if intent == "OPEN":
                target = intent_data.get("target")
                if target:
                    preference_memory.update_favorite_app(target)

            print("[STATE] FINISHED — Pipeline execution complete.")
            emit_payload = {"type": "result", "ok": True, "intent": intent}
            if variant:
                emit_payload["variant"] = variant
            await emit_json(emit_payload)

        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[STATE] ERROR — Pipeline execution failed: {e}")
            set_state(AssistantState.ERROR)
            await emit_json({"type": "result", "ok": False, "reason": "pipeline_error", "detail": str(e)[:200]})
            try:
                await safe_speak("Something went wrong sir")
            except Exception:
                pass
        finally:
            if not is_speaking:
                set_state(AssistantState.IDLE)


def set_web_session_active(value: bool = True) -> None:
    global active
    active = value
