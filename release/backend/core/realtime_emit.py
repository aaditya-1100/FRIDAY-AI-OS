"""
Optional async fan-out for JSON payloads to WebSocket clients (acks, errors).

Registered only by api.server at startup so pipeline stays transport-agnostic.
"""

from __future__ import annotations

from typing import Awaitable, Callable, List

Emitter = Callable[[dict], Awaitable[None]]

_emitters: List[Emitter] = []


def register_json_emitter(fn: Emitter) -> None:
    if fn not in _emitters:
        _emitters.append(fn)


def unregister_json_emitter(fn: Emitter) -> None:
    if fn in _emitters:
        _emitters.remove(fn)


_client_count_callback: Callable[[], int] | None = None


def register_client_count_callback(fn: Callable[[], int]) -> None:
    global _client_count_callback
    _client_count_callback = fn


def unregister_client_count_callback() -> None:
    global _client_count_callback
    _client_count_callback = None


def has_emitters() -> bool:
    """True when at least one WebSocket client is connected and active."""
    if _client_count_callback is not None:
        return _client_count_callback() > 0
    return len(_emitters) > 0


async def emit_json(payload: dict) -> None:
    dead: list[Emitter] = []
    # Diagnostic: log how many emitters and payload type
    try:
        emitter_count = len(_emitters)
        client_count = _client_count_callback() if _client_count_callback else 0
        print(f"[EMIT] Emitting payload type='{payload.get('type')}' | emitters={emitter_count} | clients={client_count}")
    except Exception:
        print("[EMIT] Emitting payload to emitters (unable to stringify payload type)")
    for fn in list(_emitters):
        try:
            await fn(payload)
        except Exception:
            # Emitter raised — likely a dead WS connection; queue for removal.
            dead.append(fn)
    for fn in dead:
        if fn in _emitters:
            _emitters.remove(fn)


# ── Synchronous fire-and-forget emitter for use from non-async threads ────────
# Used by listen.py to stream mic_level during LISTENING from the PyAudio thread.
# Schedules the coroutine on the running event loop without blocking the caller.

_sync_loop = None


def register_event_loop(loop) -> None:
    """Called by api/server.py after asyncio loop is started."""
    global _sync_loop
    _sync_loop = loop


def emit_json_sync(payload: dict) -> None:
    """
    Thread-safe synchronous emit. Schedules emit_json() on the registered
    asyncio event loop from any thread (e.g. the PyAudio audio capture thread).

    This is a best-effort fire-and-forget: if no loop is registered or the
    loop is closed, the call silently drops \u2014 never crashes the audio thread.
    """
    global _sync_loop
    if _sync_loop is None or _sync_loop.is_closed():
        return
    try:
        import asyncio
        asyncio.run_coroutine_threadsafe(emit_json(payload), _sync_loop)
    except Exception:
        pass  # Silently drop \u2014 never crash the audio capture thread
