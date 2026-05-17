"""
Shared async pipeline for CLI and web: wake/context, intent, execute, speak.
Serialized per session to avoid overlapping commands and state races.
"""

import asyncio
import functools
import random

from brain.intent_parser import parse_intent
from core.realtime_emit import emit_json
from core.state_manager import AssistantState, set_state
from execution.action_executor import execute_action
from voice.speak import speak, cancel_play
from voice.wake_detector import detect_wake_word, remove_wake_word

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


async def safe_speak(text: str, web_mode: bool = False) -> None:
    global is_speaking, _speak_cancelled
    try:
        if not text:
            return
        text = str(text).strip()
        if len(text) == 0:
            return
        if _speak_cancelled:
            _speak_cancelled = False
            return
        is_speaking = True
        set_state(AssistantState.SPEAKING)
        if web_mode:
            await emit_json({"type": "speak", "text": text})
        if not _speak_cancelled:
            await speak(text, web_mode=web_mode)
    except asyncio.CancelledError:
        cancel_play()
        raise
    except Exception as e:
        print(f"[SPEAK ERROR] {e}")
    finally:
        _speak_cancelled = False
        is_speaking = False
        set_state(AssistantState.IDLE)


async def process_transcript(raw_query: str, *, web_mode: bool = False) -> None:
    """
    Process one user utterance (from mic STT or web UI).
    web_mode: skip idle gate when wake not used; pre-activate via set_web_session_active.
    """
    global active, last_query

    query = (raw_query or "").lower().strip()
    if len(query) == 0:
        return

    async with _process_lock:
        try:
            if detect_wake_word(query):
                if not active:
                    active = True
                    await safe_speak(random.choice(WAKE_RESPONSES), web_mode)
                query = remove_wake_word(query).strip()
                if len(query) == 0:
                    return

            if not active and not web_mode:
                return

            if any(word in query for word in EXIT_WORDS):
                active = False
                await safe_speak("Going idle sir", web_mode)
                return

            query = apply_context(query)
            last_query = query

            set_state(AssistantState.THINKING)

            # parse_intent calls ask_groq (blocking I/O) — run in thread pool
            loop = asyncio.get_running_loop()
            intent_data = await loop.run_in_executor(
                None,
                functools.partial(parse_intent, query)
            )
            intent = intent_data.get("intent")

            if not intent:
                print("[IGNORED] No valid intent")
                await emit_json({"type": "result", "ok": False, "reason": "no_intent"})
                return

            set_state(AssistantState.EXECUTING)

            result = await execute_action(intent_data)

            if not result:
                await safe_speak("I could not do that sir", web_mode)
                await emit_json({"type": "result", "ok": False, "reason": "execute_failed", "intent": intent})
                return

            if isinstance(result, dict) and result.get("type") == "ai_response":
                await safe_speak(result.get("response"), web_mode)
                await emit_json({"type": "result", "ok": True, "intent": intent, "variant": "ai_response"})
                return

            if intent == "MULTI_ACTION":
                # Sub-actions ran (browser opened etc.). result is True if no verbal response.
                await safe_speak("Done sir", web_mode)
                await emit_json({"type": "result", "ok": True, "intent": intent})
                return

            if intent == "SEARCH":
                await safe_speak("Searching now sir", web_mode)
                await emit_json({"type": "result", "ok": True, "intent": intent})
                return

            if intent == "PLAY_MEDIA":
                await safe_speak("Playing now sir", web_mode)
                await emit_json({"type": "result", "ok": True, "intent": intent})
                return

            if intent == "WEB_SEARCH":
                await safe_speak("Searching Google sir", web_mode)
                await emit_json({"type": "result", "ok": True, "intent": intent})
                return

            await safe_speak("Done sir", web_mode)
            await emit_json({"type": "result", "ok": True, "intent": intent})

        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[PIPELINE ERROR] {e}")
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
