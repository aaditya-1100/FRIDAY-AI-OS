import asyncio
import re
from typing import Callable, Awaitable, List, Tuple
from loguru import logger
from friday.core.events import EventEnvelope

class EventBus:
    def __init__(self):
        self._queue = asyncio.PriorityQueue()
        self._subscribers: List[Tuple[str, re.Pattern, Callable[[EventEnvelope], Awaitable[None]]]] = []
        self._counter = 0
        self._dispatch_task: asyncio.Task | None = None
        self._running = False
        self._loop = None

    def start(self, loop: asyncio.AbstractEventLoop = None):
        """Start the background dispatch loop."""
        current_loop = loop or asyncio.get_running_loop()
        if self._loop is not current_loop:
            self._loop = current_loop
            self._queue = asyncio.PriorityQueue()
            if self._running and self._dispatch_task:
                self._dispatch_task.cancel()
                self._dispatch_task = self._loop.create_task(self._dispatch_loop())
        if self._running:
            return
        self._running = True
        self._dispatch_task = self._loop.create_task(self._dispatch_loop())
        logger.info("[EVENT_BUS] Background dispatch loop started.")

    async def stop(self):
        """Stop the background dispatch loop."""
        self._running = False
        if self._dispatch_task:
            self._dispatch_task.cancel()
            try:
                await self._dispatch_task
            except asyncio.CancelledError:
                pass
            self._dispatch_task = None
        logger.info("[EVENT_BUS] Background dispatch loop stopped.")

    def subscribe(self, topic_pattern: str, callback: Callable[[EventEnvelope], Awaitable[None]]):
        """Subscribe to a topic pattern (supports * wildcards)."""
        # Convert topic pattern wildcard to regex
        parts = topic_pattern.split(".")
        regex_parts = []
        for i, part in enumerate(parts):
            if part == "*":
                if i == len(parts) - 1:
                    regex_parts.append(".*")
                else:
                    regex_parts.append("[^.]+")
            else:
                regex_parts.append(re.escape(part))
        pattern_regex = re.compile("^" + r"\.".join(regex_parts) + "$")
        self._subscribers.append((topic_pattern, pattern_regex, callback))
        logger.debug(f"[EVENT_BUS] Subscribed to pattern: {topic_pattern}")

    def unsubscribe(self, topic_pattern: str, callback: Callable[[EventEnvelope], Awaitable[None]]):
        """Unsubscribe a callback from a topic pattern."""
        self._subscribers = [
            sub for sub in self._subscribers
            if not (sub[0] == topic_pattern and sub[2] == callback)
        ]
        logger.debug(f"[EVENT_BUS] Unsubscribed from pattern: {topic_pattern}")

    async def publish(self, envelope: EventEnvelope) -> None:
        """Asynchronously publish an event to the queue."""
        self._counter += 1
        priority_val = envelope.priority.to_int()
        # Tuple of (priority_int, counter, envelope) ensures FIFO ordering for same priority
        await self._queue.put((priority_val, self._counter, envelope))
        logger.debug(
            f"[EVENT_BUS] Published event {envelope.event_id} on topic '{envelope.topic}' "
            f"with priority {envelope.priority} (correlation_id={envelope.correlation_id})"
        )

    def publish_sync(self, envelope: EventEnvelope) -> None:
        """Synchronously publish an event (thread-safe)."""
        loop = self._loop
        if not loop:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

        if loop and loop.is_running():
            try:
                # Check if we are running in the loop's thread
                loop.create_task(self.publish(envelope))
            except RuntimeError:
                # Call from foreign thread
                loop.call_soon_threadsafe(
                    lambda: loop.create_task(self.publish(envelope))
                )
        else:
            # Fallback if no loop is running
            new_loop = asyncio.new_event_loop()
            try:
                new_loop.run_until_complete(self.publish(envelope))
            finally:
                new_loop.close()

    async def _dispatch_loop(self):
        """Background coroutine to pop and dispatch events."""
        while self._running:
            try:
                priority_val, count, envelope = await self._queue.get()
                logger.info(
                    f"[EVENT_BUS_DISPATCH] Processing {envelope.topic} "
                    f"(Priority={envelope.priority}, correlation_id={envelope.correlation_id})"
                )
                
                # Match against subscribers
                matched_subscribers = []
                for pattern_str, pattern_regex, callback in self._subscribers:
                    if pattern_regex.match(envelope.topic):
                        matched_subscribers.append(callback)

                # Dispatch concurrently to all matched subscribers
                for callback in matched_subscribers:
                    self._loop.create_task(self._safe_invoke(callback, envelope))
                
                self._queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[EVENT_BUS_ERROR] Exception in dispatch loop: {e}")
                await asyncio.sleep(0.1)

    async def _safe_invoke(self, callback: Callable[[EventEnvelope], Awaitable[None]], envelope: EventEnvelope):
        try:
            await callback(envelope)
        except Exception as e:
            logger.error(
                f"[EVENT_BUS_CALLBACK_ERROR] Exception in subscriber callback for "
                f"topic {envelope.topic} (correlation_id={envelope.correlation_id}): {e}",
                exc_info=True
            )

# Global singleton event bus
event_bus = EventBus()
