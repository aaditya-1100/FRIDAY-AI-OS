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
from core.realtime_emit import has_emitters
from voice.listen import listen, request_stop, reset_stop, set_mic_enabled


async def main():
    reset_stop()
    set_mic_enabled(True)
    # In the packaged Electron app the user opened FRIDAY intentionally —
    # activate immediately so mic works without a wake word.
    pipeline.set_web_session_active(True)

    try:
        await pipeline.safe_speak(pipeline.STARTUP_MESSAGE)

        print("[STARTUP] FRIDAY is ready. Say 'Friday' to wake up.")
        print("-" * 60)

        while True:
            try:
                # Only listen if the assistant is completely IDLE
                from core.state_manager import get_state
                if get_state() not in (AssistantState.IDLE, AssistantState.LISTENING):
                    await asyncio.sleep(0.1)
                    continue

                # Check if mic is enabled to prevent tight looping when muted
                from voice.listen import is_mic_enabled
                if not is_mic_enabled():
                    set_state(AssistantState.IDLE)
                    await asyncio.sleep(0.3)
                    continue

                set_state(AssistantState.LISTENING)
                print("[LISTENING] Waiting for speech...")

                query = await listen()
                if query is None:
                    await asyncio.sleep(0.1)
                    continue

                print(f"[TRANSCRIBED] '{query}'")
                # web_mode=None → auto-detected inside process_transcript/safe_speak
                # based on whether WS clients are connected (has_emitters()).
                await pipeline.process_transcript(query)

            except asyncio.CancelledError:
                # Shutdown signal from server lifespan
                raise
            except KeyboardInterrupt:
                print("\n[SHUTDOWN] Interrupted")
                break
            except Exception as e:
                print(f"[MAIN LOOP ERROR] {e}")
                set_state(AssistantState.IDLE)
                # Tight loop protection: sleep for 4.0 seconds on recurring audio/OS errors
                # to allow PortAudio and USB interfaces to dynamically re-enumerate and self-heal.
                await asyncio.sleep(4.0)
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
