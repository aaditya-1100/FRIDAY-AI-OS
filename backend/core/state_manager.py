import asyncio
from typing import Awaitable, Callable, List

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


current_state = AssistantState.IDLE


def set_main_loop(loop: asyncio.AbstractEventLoop):
    global _main_loop
    _main_loop = loop


def register_state_callback(callback: StateCallback) -> None:

    if callback not in _callbacks:

        _callbacks.append(callback)


def unregister_state_callback(callback: StateCallback) -> None:

    if callback in _callbacks:

        _callbacks.remove(callback)


def set_state(state):

    global current_state, _main_loop

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
