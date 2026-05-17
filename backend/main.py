"""
main.py — FRIDAY agent loop (mic listen → pipeline).

Shutdown contract:
- This coroutine is run as a background asyncio.Task by api/server.py.
- When server shuts down it calls agent_task.cancel().
- We catch CancelledError, call voice.listen.request_stop() to unblock
  the listener thread, then re-raise so asyncio cleans up properly.
- pygame mixer is stopped in the finally block.
"""
import asyncio
import sys

from core import pipeline
from core.state_manager import AssistantState, set_state
from voice.listen import listen, request_stop, reset_stop, set_mic_enabled


async def main():
    reset_stop()          # ensure listen is armed on (re)start
    set_mic_enabled(True)

    try:
        await pipeline.safe_speak(pipeline.STARTUP_MESSAGE)

        print("[STARTUP] FRIDAY is ready. Say 'Friday' to wake up.")
        print("-" * 60)

        while True:
            try:
                if pipeline.is_speaking:
                    await asyncio.sleep(0.05)
                    continue

                set_state(AssistantState.LISTENING)

                query = await listen()
                if query is None:
                    # None means silence / timeout — just loop again
                    await asyncio.sleep(0)   # yield to event loop
                    continue

                await pipeline.process_transcript(query, web_mode=False)

            except asyncio.CancelledError:
                # Shutdown signal from server lifespan
                raise
            except KeyboardInterrupt:
                print("\n[SHUTDOWN] Interrupted")
                break
            except Exception as e:
                print(f"[MAIN LOOP ERROR] {e}")
                try:
                    await pipeline.safe_speak("Something went wrong sir")
                except Exception:
                    pass
                continue

    except asyncio.CancelledError:
        print("[SHUTDOWN] Agent task cancelled — stopping mic and TTS")
        request_stop()        # unblock listener thread immediately
        pipeline.cancel_speak()  # stop any in-flight TTS
        # Stop pygame mixer cleanly
        try:
            import pygame
            if pygame.mixer.get_init():
                pygame.mixer.music.stop()
                pygame.mixer.quit()
        except Exception:
            pass
        raise   # re-raise so asyncio marks the task as cancelled
    except Exception as e:
        print(f"[FATAL ERROR] {e}")
    finally:
        print("[SHUTDOWN] FRIDAY offline")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[EXIT] Goodbye sir")
        sys.exit(0)
