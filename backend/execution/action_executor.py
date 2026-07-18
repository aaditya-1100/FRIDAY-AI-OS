"""
action_executor.py — R8.1 Thin Dispatcher
Zero business logic. Routes intent_data -> agent.handle_task() -> result dict.
All business logic lives in friday/agents/*.py.
"""
import asyncio
import sys
import os
from uuid import uuid4
from loguru import logger
from friday.core.events import TaskDispatch, AgentType, TaskStatus


# ── Agent Type → Intent mapping ──────────────────────────────────────────────
_PC_INTENTS = frozenset({
    "OPEN", "WINDOW_CONTROL", "SCREENSHOT", "SYSTEM_STATUS", "SYSTEM_STATUS_FULL",
    "BLUETOOTH_TOGGLE", "BRIGHTNESS_CONTROL", "DELETE_PATH", "CLEAN_TEMP",
    "SET_REMINDER", "SET_TIMER", "SET_ALARM", "STOPWATCH_CONTROL",
    "SET_SCHEDULED_TASK", "SET_RECURRING_REMINDER", "LIST_REMINDERS", "CANCEL_REMINDER",
    "VOLUME_SET", "VOLUME_MUTE", "CREATE_FOLDER", "OPEN_FOLDER",
    "CLIPBOARD_READ", "CLIPBOARD_WRITE", "APP_FOCUS", "WINDOW_LIST",
    "FILE_READ", "FILE_WRITE", "FILE_CREATE", "FILE_MOVE", "FILE_DELETE",
    "CHECK_DISK_SPACE", "CHECK_SYSTEM_INFO", "PING_HOST", "LIST_DIRECTORY", "LIST_PROCESSES"
})
_WEB_INTENTS = frozenset({
    "WEB_SEARCH", "SEARCH", "WEATHER", "NEWS", "REALTIME_QUERY"
})
_MEDIA_INTENTS = frozenset({
    "YOUTUBE_TOPIC_SEARCH", "LATEST_CREATOR_VIDEO", "LATEST_CREATOR_SHORT",
    "VIDEO_BY_TITLE", "CHANNEL_OPEN", "PLAY_SEARCH_RESULT",
    "PLAY_MEDIA", "URL_OPEN", "SPOTIFY_CONTROL"
})
_VISION_INTENTS = frozenset({
    "SCREEN_UNDERSTANDING", "SCREEN_READ", "SCREEN_FIND",
    "SCREEN_SCREENSHOT", "SCREEN_DESCRIBE", "SCREEN_CLICK"
})
_MEMORY_INTENTS = frozenset({"SET_FACT", "WRITE_MEMORY", "READ_MEMORY", "CONSOLIDATE", "LOAD_SESSION_CONTEXT"})
_KNOWLEDGE_INTENTS = frozenset({"AI_QUERY", "CASUAL_CHAT", "CLARIFICATION", "RETRIEVE_SEMANTIC", "QUERY_GRAPH"})


def _intent_to_agent_type(intent: str) -> AgentType | None:
    if intent in _PC_INTENTS:
        return AgentType.PC_AGENT
    if intent in _WEB_INTENTS:
        return AgentType.WEB_AGENT
    if intent in _MEDIA_INTENTS:
        return AgentType.MEDIA_AGENT
    if intent in _VISION_INTENTS:
        return AgentType.VISION_AGENT
    if intent in _MEMORY_INTENTS:
        return AgentType.MEMORY_AGENT
    if intent in _KNOWLEDGE_INTENTS:
        return AgentType.KNOWLEDGE_AGENT
    return None


async def _dispatch_to_agent(intent_data: dict, memory=None) -> dict | bool:
    """Route a single intent to the correct agent and return its result."""
    intent = intent_data.get("intent")
    if not intent:
        return None

    # CASUAL_CHAT → AI_QUERY alias
    if intent == "CASUAL_CHAT":
        intent = "AI_QUERY"
        intent_data = {**intent_data, "intent": "AI_QUERY"}

    agent_type = _intent_to_agent_type(intent)
    if agent_type is None:
        logger.warning(f"[Dispatcher] No agent mapping for intent: {intent}")
        return False

    from friday.core.agent_store import get as agent_get
    agent = agent_get(agent_type)
    if agent is None:
        logger.error(f"[Dispatcher] Agent not found in registry for type: {agent_type}")
        return False

    parameters = {k: v for k, v in intent_data.items() if k != "intent"}
    if memory is not None:
        parameters["_memory_obj"] = memory

    dispatch = TaskDispatch(
        task_id=uuid4(),
        agent_type=agent_type,
        intent=intent,
        parameters=parameters,
        correlation_id=intent_data.get("correlation_id") or uuid4(),
        session_id=intent_data.get("session_id") or uuid4(),
    )

    result = await agent.handle_task(dispatch)

    if result.status == TaskStatus.SUCCESS:
        payload = result.payload
        if "response" in payload:
            return {"type": "ai_response", "response": payload["response"]}
        return payload
    else:
        error = result.payload.get("error", "unknown error")
        logger.warning(f"[Dispatcher] Agent returned failure for {intent}: {error}")
        return False


async def execute_action(intent_data: dict, memory=None):
    """
    Public entry point — thin dispatcher only.
    Business logic lives in agents. This file: routing + MULTI_ACTION chaining only.
    """
    try:
        intent = intent_data.get("intent")
        if intent is None:
            return None

        # ── Self-Referential System Actions (FRIDAY self-control) ─────────────
        q_clean = (intent_data.get("query") or "").lower().strip()
        temporal_intents = {
            "SET_REMINDER", "SET_TIMER", "SET_ALARM", "SET_SCHEDULED_TASK",
            "SET_RECURRING_REMINDER", "LIST_REMINDERS", "CANCEL_REMINDER", "STOPWATCH_CONTROL"
        }
        has_self_ref = any(w in q_clean for w in ("friday", "yourself", "the assistant", "assistant"))
        if intent not in temporal_intents and has_self_ref:
            loop = asyncio.get_running_loop()
            if any(t in q_clean for t in ("exit", "close", "turn off", "shut down", "shutdown", "power off", "deactivate")):
                from core.state_manager import set_state, AssistantState
                set_state(AssistantState.IDLE)
                loop.call_later(1.0, lambda: sys.exit(0))
                return {"type": "ai_response", "response": "Shutting down system services now, sir. Goodbye."}
            if any(t in q_clean for t in ("mute", "silence")):
                from voice.listen import set_mic_enabled
                set_mic_enabled(False)
                return {"type": "ai_response", "response": "Muting microphone, sir. You can re-enable my microphone from the UI panel."}
            if any(t in q_clean for t in ("restart", "reboot")):
                loop.call_later(1.0, lambda: os.execv(sys.executable, ['python'] + sys.argv))
                return {"type": "ai_response", "response": "Restarting system services now, sir."}

        # ── MULTI_ACTION: chain up to 3 sub-intents ───────────────────────────
        if intent == "MULTI_ACTION":
            actions = intent_data.get("actions", [])
            if len(actions) > 3:
                logger.warning(f"[Dispatcher] MULTI_ACTION contains {len(actions)} actions. Truncating to first 3.")
                actions = actions[:3]
            
            responses = []
            for idx, action in enumerate(actions):
                try:
                    result = await _dispatch_to_agent(action, memory)
                    if isinstance(result, dict):
                        if result.get("type") == "ai_response" and result.get("response"):
                            responses.append(result["response"])
                        elif "response" in result:
                            responses.append(result["response"])
                        else:
                            act_intent = action.get("intent", "action")
                            responses.append(f"Completed step {idx+1}: {act_intent}.")
                    elif result is True:
                        act_intent = action.get("intent", "action")
                        responses.append(f"Completed step {idx+1}: {act_intent}.")
                    else:
                        act_intent = action.get("intent", "action")
                        responses.append(f"Step {idx+1} ({act_intent}) failed.")
                except Exception as e_step:
                    logger.error(f"[Dispatcher] Error executing MULTI_ACTION step {idx+1}: {e_step}")
                    act_intent = action.get("intent", "action")
                    responses.append(f"Step {idx+1} ({act_intent}) failed.")
            if responses:
                return {"type": "ai_response", "response": " ".join(responses)}
            return {"type": "ai_response", "response": "I processed the actions, sir."}

        # ── Single intent dispatch ────────────────────────────────────────────
        return await _dispatch_to_agent(intent_data, memory)

    except Exception as e:
        logger.error("[Dispatcher] Unhandled exception: {}", repr(e))
        return False