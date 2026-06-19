import asyncio
from typing import Awaitable, Callable, List, Dict, Any

StateCallback = Callable[[str], Awaitable[None]]

_callbacks: List[StateCallback] = []
_main_loop = None

class AssistantState:
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    THINKING = "THINKING"
    EXECUTING = "EXECUTING"
    SPEAKING = "SPEAKING"
    ERROR = "ERROR"
    
    # Advanced Conversational States
    CASUAL_CHAT = "CASUAL_CHAT"
    TASK_MODE = "TASK_MODE"
    RETRIEVAL_MODE = "RETRIEVAL_MODE"
    EMOTIONAL_CONTEXT = "EMOTIONAL_CONTEXT"

current_state = AssistantState.IDLE
current_conversational_state = AssistantState.CASUAL_CHAT

# Central Orchestration State variables
active_tasks: List[str] = []
audio_state: Dict[str, Any] = {"playing": False, "volume": 100, "playback_session_id": None}
websocket_state: str = "DISCONNECTED"
retrieval_state: Dict[str, Any] = {"active": False, "query": ""}
vision_state: Dict[str, Any] = {"active": False, "query": ""}
maps_state: Dict[str, Any] = {"active": False, "action": ""}
interruptions: int = 0
queued_actions: List[Dict[str, Any]] = []

def track_task_start(task_name: str) -> None:
    if task_name not in active_tasks:
        active_tasks.append(task_name)
        print(f"[STATE] Task Started: {task_name}")

def track_task_end(task_name: str) -> None:
    if task_name in active_tasks:
        active_tasks.remove(task_name)
        print(f"[STATE] Task Ended: {task_name}")

def set_audio_state(playing: bool, volume: int = 100, session_id: str = None) -> None:
    global audio_state
    audio_state["playing"] = playing
    audio_state["volume"] = volume
    if session_id:
        audio_state["playback_session_id"] = session_id

def set_websocket_state(state: str) -> None:
    global websocket_state
    websocket_state = state
    print(f"[STATE] WebSocket Connection: {state}")

def set_retrieval_state(active: bool, query: str = "") -> None:
    global retrieval_state
    retrieval_state["active"] = active
    retrieval_state["query"] = query

def set_vision_state(active: bool, query: str = "") -> None:
    global vision_state
    vision_state["active"] = active
    vision_state["query"] = query

def set_maps_state(active: bool, action: str = "") -> None:
    global maps_state
    maps_state["active"] = active
    maps_state["action"] = action

def register_interruption() -> None:
    global interruptions
    interruptions += 1
    print(f"[STATE] System Interruption Registered. Total count: {interruptions}")

def queue_action(action: Dict[str, Any]) -> None:
    queued_actions.append(action)
    print(f"[STATE] Action Queued: {action.get('intent')}")

def clear_queued_actions() -> None:
    queued_actions.clear()

def set_conversational_state(state: str) -> None:
    global current_conversational_state
    if state in (AssistantState.CASUAL_CHAT, AssistantState.TASK_MODE, AssistantState.RETRIEVAL_MODE, AssistantState.EMOTIONAL_CONTEXT):
        current_conversational_state = state
        print(f"[STATE] Conversational Mode: {state}")

def get_conversational_state() -> str:
    global current_conversational_state
    return current_conversational_state

def set_main_loop(loop: asyncio.AbstractEventLoop):
    global _main_loop
    _main_loop = loop

def register_state_callback(callback: StateCallback) -> None:
    if callback not in _callbacks:
        _callbacks.append(callback)

def unregister_state_callback(callback: StateCallback) -> None:
    if callback in _callbacks:
        _callbacks.remove(callback)

def set_state(state, force=False):
    global current_state, _main_loop

    # Globally enforce that IDLE is only allowed if mic is disabled
    try:
        from voice.listen import is_mic_enabled, get_mic_mode
        if state == AssistantState.IDLE and is_mic_enabled() and get_mic_mode() != "hold_to_talk":
            print(f"[STATE SYSTEM] Intercepted transition to IDLE while microphone is ON. Forcing state to LISTENING instead.")
            state = AssistantState.LISTENING
    except Exception as e:
        print(f"[STATE SYSTEM WARNING] Failed to verify mic status: {e}")

    if state == current_state:
        return
    # Deterministic State Ownership block
    if state == AssistantState.IDLE and not force:
        try:
            from core import pipeline
            is_speaking_active = getattr(pipeline, "is_speaking", False)
        except Exception:
            is_speaking_active = False

        # Block transition to IDLE if pipeline tasks or text-to-speech are active.
        # We only block transition to IDLE if there are actual running pipeline tasks
        # (active_tasks is not empty) or if the text-to-speech is playing.
        if active_tasks:
            print(f"[STATE SYSTEM] Blocked transition to IDLE during active pipeline tasks: {active_tasks}")
            return
        if is_speaking_active:
            print(f"[STATE SYSTEM] Blocked transition to IDLE while text-to-speech is playing.")
            return

    current_state = state
    print(f"[STATE] {state}")

    if not _callbacks:
        return

    # Determine the active loop
    loop = _main_loop
    if loop is None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

    if not loop.is_running():
        return

    for cb in list(_callbacks):
        try:
            # If we're already on the event loop thread, schedule directly.
            # If called from another thread, use thread-safe bridge.
            try:
                running = asyncio.get_running_loop()
            except RuntimeError:
                running = None

            if running is loop:
                # Same thread — create task directly
                loop.create_task(cb(state))
            else:
                # Foreign thread — schedule via thread-safe call
                loop.call_soon_threadsafe(loop.create_task, cb(state))
        except Exception as e:
            print(f"[STATE] Error dispatching callback: {e}")

def get_state():
    return current_state
