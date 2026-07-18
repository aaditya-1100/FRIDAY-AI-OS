"""
core/runtime_stability.py — Persistent Low-Entropy Runtime Janitor for FRIDAY.
Coordinates connection pruning, async task garbage collection, memory reclamation,
and PyGame mixer release cycles to ensure infinite (8+ hour) warm-runtime persistence.
"""
import asyncio
import gc
import time
import os
import re
from friday.core.fsm import cognitive_core, AssistantState

# Global manager instance
stability_manager = None


class RuntimeStabilityManager:
    """Coordinates periodic cleanups and runs a high-speed failure recovery watchdog."""
    
    def __init__(self, loop: asyncio.AbstractEventLoop = None):
        self.loop = loop or asyncio.get_event_loop()
        self._cleanup_task: asyncio.Task | None = None
        self._watchdog_task: asyncio.Task | None = None
        self._last_speak_time = time.monotonic()
        self._mixer_active = True
        
        # Track state durations for recovery watchdog
        self._state_durations = {}
        self._last_state_check = time.monotonic()
        print("[JANITOR] Runtime Stability Manager initialized.")

    def start(self):
        """Register the janitor cleanup loop and recovery watchdog."""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = self.loop.create_task(self._cleanup_loop())
            print("[JANITOR] Background cleanup loop started (ticking every 300s).")
        if self._watchdog_task is None or self._watchdog_task.done():
            self._watchdog_task = self.loop.create_task(self._watchdog_loop())
            print("[JANITOR] High-speed failure recovery watchdog started (ticking every 5s).")

    def stop(self):
        """Stop the background janitor and watchdog cleanly."""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            self._cleanup_task = None
        if self._watchdog_task and not self._watchdog_task.done():
            self._watchdog_task.cancel()
            self._watchdog_task = None
        print("[JANITOR] Background janitor services stopped.")

    def touch_audio(self):
        """Notify janitor of active speech/playback to prevent premature audio resets."""
        self._last_speak_time = time.monotonic()
        from core.realtime_emit import has_emitters
        if has_emitters():
            # In Web Mode (Electron UI), we do not use pygame playback at all.
            # Avoid initializing the local pygame mixer to prevent audio driver/sample-rate contention.
            self._mixer_active = False
            return

        if not self._mixer_active:
            # Dynamically re-initialize mixer if it was previously released
            try:
                import pygame
                if not pygame.mixer.get_init():
                    print("[JANITOR] Re-initializing pygame audio mixer for incoming speech...")
                    pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=4096)
                self._mixer_active = True
            except Exception as e:
                print(f"[JANITOR ERROR] Failed to re-initialize pygame mixer: {e}")

    def run_health_audit(self) -> dict:
        """
        Runs a comprehensive real-time audit of all subsystems (STT, TTS, WebSocket, Audio queue, Search, Memory).
        Gracefully degrades/recovers any failing components.
        """
        audit_results = {}
        
        # 1. STT Health
        try:
            from voice.listen import is_mic_enabled
            mic_active = is_mic_enabled()
            audit_results["stt"] = "OK" if mic_active else "DISABLED"
        except Exception as e:
            audit_results["stt"] = f"ERROR: {e}"

        # 2. TTS Health
        from core.realtime_emit import has_emitters
        if has_emitters():
            audit_results["tts"] = "OK (WEB_MODE)"
        else:
            try:
                import pygame
                mixer_init = bool(pygame.mixer.get_init())
                if not mixer_init and self._mixer_active:
                    pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=4096)
                    mixer_init = bool(pygame.mixer.get_init())
                audit_results["tts"] = "OK" if mixer_init else "UNINITIALIZED"
            except Exception as e:
                audit_results["tts"] = f"ERROR: {e}"

        # 3. WebSocket Health
        try:
            from api.server import clients
            audit_results["websocket"] = f"OK ({len(clients)} active clients)"
        except Exception as e:
            audit_results["websocket"] = f"ERROR: {e}"

        # 4. Audio Queue / Playback Event Health
        try:
            from voice.speak import _playback_events
            pending_events = len(_playback_events)
            if pending_events > 5:
                print(f"[WATCHDOG HEALTH] Pruning {pending_events} stale playback events to prevent memory leak.")
                _playback_events.clear()
            audit_results["audio_queue"] = f"OK ({pending_events} pending events)"
        except Exception as e:
            audit_results["audio_queue"] = f"ERROR: {e}"

        # 5. Search Health
        try:
            from system.live_data import get_retrieval_health
            search_health = get_retrieval_health()
            broken_sources = [k for k, v in search_health.items() if not v.get("available")]
            if broken_sources:
                audit_results["search"] = f"DEGRADED (Broken: {', '.join(broken_sources)})"
            else:
                audit_results["search"] = "OK"
        except Exception as e:
            audit_results["search"] = f"ERROR: {e}"

        # 6. Memory Health
        try:
            import psutil
            process = psutil.Process(os.getpid())
            mem_mb = process.memory_info().rss / (1024 * 1024)
            if mem_mb > 300.0:
                print(f"[WATCHDOG HEALTH] High memory usage detected ({mem_mb:.1f} MB). Running aggressive garbage collection.")
                self.reclaim_memory()
            audit_results["memory"] = f"OK ({mem_mb:.1f} MB)"
        except Exception as e:
            audit_results["memory"] = "OK"

        return audit_results

    async def _watchdog_loop(self):
        """High-speed failure recovery watchdog checking state every 5 seconds."""
        import friday.core.fsm as fsm_module
        from friday.core.fsm import AssistantState
        from voice.speak import cancel_play
        
        while True:
            try:
                await asyncio.sleep(5)
                current = fsm_module.cognitive_core.fsm.current_state
                
                # Run the continuous health audit
                try:
                    audit = self.run_health_audit()
                    for sub, status in audit.items():
                        if "ERROR" in status or "DEGRADED" in status or "UNINITIALIZED" in status:
                            print(f"[WATCHDOG HEALTH WARNING] Subsystem {sub.upper()} is: {status}")
                except Exception as e_health:
                    print(f"[WATCHDOG WARNING] Health audit failed: {e_health}")
                
                # ── CONVERSATIONAL ATTENTION WINDOW TIMEOUT (CRITICAL PACING LAYER) ──
                try:
                    from core import pipeline
                    from core.state_manager import get_conversational_state
                    # Legacy pipeline state tracking compatibility
                    from core.state_manager import AssistantState as SMAssistantState
                    if pipeline.active and current in (AssistantState.IDLE,):
                        conv_state = get_conversational_state()
                        if conv_state == "TASK_MODE":
                            timeout_dur = 20.0
                        elif conv_state == "EMOTIONAL_CONTEXT":
                            timeout_dur = 45.0
                        else:
                            timeout_dur = 30.0

                        inactive_dur = time.time() - pipeline._last_interaction_time
                        if inactive_dur > timeout_dur:
                            print(f"[WATCHDOG] Conversational attention window expired ({inactive_dur:.1f}s of silence in {conv_state}). Reverting to passive wake-word mode.")
                            pipeline.set_web_session_active(False)
                            from voice.listen import is_mic_enabled, get_mic_mode
                            target_state = SMAssistantState.LISTENING if (is_mic_enabled() and get_mic_mode() != "hold_to_talk") else SMAssistantState.IDLE
                            from core.state_manager import set_state as sm_set_state
                            sm_set_state(target_state, force=True)
                except Exception as e_attn:
                    print(f"[WATCHDOG WARNING] Attention window check error: {e_attn}")
                
                # If state has changed, reset duration counters
                now = time.monotonic()
                dt = now - self._last_state_check
                self._last_state_check = now
                
                # Increment active duration for the current state if not IDLE
                if current != AssistantState.IDLE:
                    self._state_durations[current] = self._state_durations.get(current, 0.0) + dt
                else:
                    self._state_durations.clear()
                    
                # 1. ERROR state recovery (force reset back to IDLE after 3 seconds)
                if current == AssistantState.ERROR:
                    dur = self._state_durations.get(current, 0.0)
                    if dur >= 3.0:
                        print(f"[WATCHDOG] Force-recovering from ERROR state (active for {dur:.1f}s) -> IDLE")
                        cancel_play()
                        fsm_module.cognitive_core.fsm.transition_to(AssistantState.IDLE, reason="Watchdog recovery from ERROR", force=True)
                        self._state_durations.clear()
                        
                # 2. Stranded active cognitive/execution states recovery (force reset back to IDLE after 45 seconds)
                elif current in (
                    AssistantState.PERCEIVING,
                    AssistantState.PLANNING,
                    AssistantState.DELEGATING,
                    AssistantState.WAITING,
                    AssistantState.SYNTHESIZING,
                    AssistantState.REFLECTING
                ):
                    dur = self._state_durations.get(current, 0.0)
                    if dur >= 45.0:
                        print(f"[WATCHDOG WARNING] Assistant is stuck in {current} for {dur:.1f}s! Triggering force-recovery state reset.")
                        # Force cancel any active speech and reset state
                        cancel_play()
                        
                        # Clean up stranded tasks
                        self.clean_orphaned_tasks()
                        
                        fsm_module.cognitive_core.abort_current_turn()
                        self._state_durations.clear()

                # 3. Intermediate passive states: IDLE or INTERRUPTED
                elif current in (AssistantState.IDLE, AssistantState.INTERRUPTED):
                    pass

                # 4. Stuck RESPONDING state recovery (force reset back to IDLE after a dynamic timeout based on audio duration)
                elif current == AssistantState.RESPONDING:
                    dur = self._state_durations.get(current, 0.0)
                    # Safe-guard stuck speaking recovery watchdog with a 10s buffer
                    try:
                        from voice.speak import current_audio_duration
                        limit = max(60.0, current_audio_duration + 10.0)
                    except Exception:
                        limit = 60.0
                    if dur >= limit:
                        print(f"[WATCHDOG WARNING] Assistant is stuck in RESPONDING for {dur:.1f}s (limit {limit:.1f}s)! Triggering self-healing recovery.")
                        # Cancel pygame music playback, force release speech lock
                        cancel_play()
                        from voice.speak import force_unlock_speech
                        force_unlock_speech("watchdog_recovery")
                        fsm_module.cognitive_core.fsm.transition_to(AssistantState.IDLE, reason="Watchdog recovery from stuck RESPONDING", force=True)
                        self._state_durations.clear()
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[WATCHDOG ERROR] Watchdog loop exception: {e}")


    async def _cleanup_loop(self):
        """Janitor tick running every 5 minutes."""
        while True:
            try:
                await asyncio.sleep(300) # tick every 5 minutes
                print("[JANITOR] Running periodic low-entropy warm-runtime cleanup...")
                
                # 1. Prune dead WebSockets
                await self.prune_websockets()
                
                # 2. Cancel stale asyncio tasks
                self.clean_orphaned_tasks()
                
                # 3. Reset idle PyGame audio engine
                self.reset_idle_audio()
                
                # 4. Reclaim memory
                self.reclaim_memory()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[JANITOR ERROR] Periodic cleanup encountered an error: {e}")

    async def prune_websockets(self):
        """Sends a lightweight ping to all WebSockets; discards dead connections immediately."""
        try:
            from api.server import clients
            if not clients:
                return
            
            dead = []
            print(f"[JANITOR] Pinging {len(clients)} active WebSocket client(s)...")
            for ws in list(clients):
                try:
                    # Send a lightweight ping with a 2-second timeout to avoid locking the loop
                    await asyncio.wait_for(ws.send_json({"type": "ping"}), timeout=2.0)
                except Exception:
                    dead.append(ws)
            
            for ws in dead:
                print(f"[JANITOR] Pruning dead WebSocket client: {ws.client}")
                clients.discard(ws)
                try:
                    await ws.close(code=1000)
                except Exception:
                    pass
        except ImportError:
            pass # ignore if imported before server is fully initialized
        except Exception as e:
            print(f"[JANITOR WARNING] WebSocket pruning exception: {e}")

    def clean_orphaned_tasks(self):
        """Scans all asyncio tasks and cancels stale/stranded pipeline execution workers."""
        try:
            current_task = asyncio.current_task()
            all_tasks = asyncio.all_tasks(self.loop)
            
            cleaned_count = 0
            for task in all_tasks:
                if task is current_task:
                    continue
                
                coro_name = str(task.get_coro()).lower()
                # Target stale execution and transcript tasks that have been running too long
                # (e.g. stranded search queries, unresolved socket hooks).
                # We skip core system tasks like 'agent_loop', '_cleanup_loop', and server lifespans.
                is_execution_task = "process_transcript" in coro_name or "_run_command" in coro_name or "realtime_web_query" in coro_name
                if is_execution_task:
                    import friday.core.fsm as fsm_module
                    if fsm_module.cognitive_core.fsm.current_state == AssistantState.IDLE:
                        print(f"[JANITOR] Cancelling stranded execution task: {task.get_name()} -> {coro_name}")
                        task.cancel()
                        cleaned_count += 1
            if cleaned_count > 0:
                print(f"[JANITOR] Successfully cleaned up {cleaned_count} orphaned async task(s).")
        except Exception as e:
            print(f"[JANITOR WARNING] Stale task cleaner exception: {e}")

    def reset_idle_audio(self):
        """Cleanly releases PyGame sound mixer when idle for 5+ minutes, freeing Windows audio resources."""
        if not self._mixer_active:
            return
        
        idle_duration = time.monotonic() - self._last_speak_time
        if idle_duration > 300: # 5 minutes
            try:
                import pygame
                if pygame.mixer.get_init():
                    print("[JANITOR] Sound mixer idle for 5 mins — releasing PyGame mixer to free Windows endpoints.")
                    pygame.mixer.music.stop()
                    pygame.mixer.quit()
                    self._mixer_active = False
            except Exception as e:
                print(f"[JANITOR WARNING] Audio mixer reset exception: {e}")

    def reclaim_memory(self):
        """Clears stale caches and triggers gc collection to keep warm-runtime RAM low-entropy."""
        try:
            # 1. Clear old context manager payload cache
            try:
                from friday.core.context_manager import context_manager
                context_manager.clear_expired_payloads()
            except Exception:
                pass
            
            # 2. Run explicit Garbage Collection
            before = gc.mem_free() if hasattr(gc, "mem_free") else 0
            collected = gc.collect()
            after = gc.mem_free() if hasattr(gc, "mem_free") else 0
            
            if before or after:
                print(f"[JANITOR] GC Reclaimed: {collected} objects | Free Memory: {after - before} bytes")
            else:
                print(f"[JANITOR] GC Reclaimed: {collected} objects successfully.")
        except Exception as e:
            print(f"[JANITOR WARNING] Memory reclamation exception: {e}")


def get_stability_manager(loop: asyncio.AbstractEventLoop = None) -> RuntimeStabilityManager:
    global stability_manager
    if stability_manager is None:
        stability_manager = RuntimeStabilityManager(loop)
    return stability_manager
