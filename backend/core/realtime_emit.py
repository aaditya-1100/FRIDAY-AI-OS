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


def has_emitters() -> bool:
    """True when at least one WebSocket client is connected."""
    return len(_emitters) > 0


async def emit_json(payload: dict) -> None:
    dead: list[Emitter] = []
    for fn in list(_emitters):
        try:
            await fn(payload)
        except Exception:
            # Emitter raised — likely a dead WS connection; queue for removal.
            dead.append(fn)
    for fn in dead:
        if fn in _emitters:
            _emitters.remove(fn)
