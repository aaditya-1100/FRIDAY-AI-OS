import asyncio
from datetime import datetime
from loguru import logger
from friday.core.events import EventEnvelope, EventPriority
from friday.core.event_bus import event_bus
from friday.core.fsm import cognitive_core, AssistantState
from friday.memory.user_profile import user_profile

class ProactiveEngine:
    def __init__(self):
        self.rule_last_fired = {}  # {rule_name: datetime}
        self.consecutive_cpu_ticks = 0
        self.fsm_idle_since = datetime.now()  # Default to boot time
        self._prev_app = ""
        self._is_running = False

    def start(self):
        if self._is_running:
            return
        self._is_running = True
        event_bus.subscribe("friday.system.context_update", self._on_context_update)
        event_bus.subscribe("friday.core.state_change", self._on_state_change)
        logger.info("[ProactiveEngine] Started.")

    def stop(self):
        if not self._is_running:
            return
        self._is_running = False
        event_bus.unsubscribe("friday.system.context_update", self._on_context_update)
        event_bus.unsubscribe("friday.core.state_change", self._on_state_change)
        logger.info("[ProactiveEngine] Stopped.")

    async def _on_state_change(self, envelope: EventEnvelope):
        new_state = envelope.payload.get("new_state")
        if new_state == "IDLE":
            if self.fsm_idle_since is None:
                self.fsm_idle_since = datetime.now()
        else:
            self.fsm_idle_since = None

    def _can_fire(self, rule_name: str) -> bool:
        last = self.rule_last_fired.get(rule_name)
        if last is None:
            return True
        return (datetime.now() - last).total_seconds() >= 300.0

    def _extract_app_name(self, active_window: str) -> str:
        if not active_window:
            return ""
        known_apps = ["VS Code", "Visual Studio Code", "Notepad", "Excel", "Word", "PyCharm", "Chrome", "Firefox", "Edge", "Explorer"]
        title_lower = active_window.lower()
        for app in known_apps:
            if app.lower() in title_lower:
                if app == "Visual Studio Code":
                    return "VS Code"
                return app
        return active_window

    def _is_user_active_at_hour(self, hour: int) -> bool:
        hours = user_profile.get_active_hours()
        if not hours:
            return True
        total = sum(hours.values())
        if total < 5:
            return True
        hour_count = hours.get(str(hour), 0)
        return (hour_count / total) >= 0.05

    async def _on_context_update(self, envelope: EventEnvelope):
        context = envelope.payload or {}
        
        # Guard: FSM must be IDLE to trigger proactive turns
        if cognitive_core.current_state != AssistantState.IDLE:
            return

        now = datetime.now()
        
        # Rule 1: LOW_BATTERY
        battery = context.get("battery_level")
        if battery is not None and battery < 0.20:
            if self._can_fire("LOW_BATTERY"):
                msg = f"Your battery is at {int(battery * 100)}%. Consider plugging in."
                await self._trigger_proactive("LOW_BATTERY", msg)

        # Rule 2: HIGH_CPU
        cpu = context.get("cpu_percent")
        if cpu is not None:
            if cpu > 85.0:
                self.consecutive_cpu_ticks += 1
            else:
                self.consecutive_cpu_ticks = 0

            if self.consecutive_cpu_ticks >= 2:
                if self._can_fire("HIGH_CPU"):
                    msg = f"CPU usage is very high at {cpu}%. Check running processes."
                    await self._trigger_proactive("HIGH_CPU", msg)

        # Rule 3: HIGH_MEMORY
        memory = context.get("memory_percent")
        if memory is not None and memory > 90.0:
            if self._can_fire("HIGH_MEMORY"):
                msg = f"Memory usage is at {memory}%. Applications may slow down."
                await self._trigger_proactive("HIGH_MEMORY", msg)

        # Rule 4: IDLE_REMINDER
        if self.fsm_idle_since is not None:
            idle_seconds = (now - self.fsm_idle_since).total_seconds()
            if idle_seconds > 600.0:
                if self._can_fire("IDLE_REMINDER"):
                    current_hour = now.hour
                    # Suppression rule A: Usually active at 9am suppression
                    if current_hour == 9 and user_profile.get_active_hours().get("9", 0) > 0:
                        logger.info("[ProactiveEngine] Suppressed IDLE_REMINDER because it's 9am and user is active at 9am in profile.")
                    # Suppression rule B: General inactive hours suppression
                    elif not self._is_user_active_at_hour(current_hour):
                        logger.info(f"[ProactiveEngine] Suppressed IDLE_REMINDER because user is usually inactive at hour {current_hour}.")
                    else:
                        msg = "You haven't interacted in a while. Anything I can help with?"
                        await self._trigger_proactive("IDLE_REMINDER", msg)

        # Rule 5: APP_DETECTED
        active_window = context.get("active_window", "")
        current_app = self._extract_app_name(active_window)
        if current_app and current_app != self._prev_app:
            old_app = self._prev_app
            self._prev_app = current_app
            # Only trigger on change, and verify it's a known productive app
            known_productive = ["VS Code", "Notepad", "Excel", "Word", "PyCharm"]
            if current_app in known_productive and old_app != "":
                if self._can_fire("APP_DETECTED"):
                    # Personalization check
                    top_apps = user_profile.get_top_n("app", 1)
                    is_top_vscode = top_apps and top_apps[0][0] == "VS Code"
                    
                    if current_app == "VS Code" and is_top_vscode:
                        msg = "Welcome back to your favorite editor, VS Code! Let's get coding."
                    else:
                        msg = f"Looks like you opened {current_app}. Need any help getting started?"
                        
                    await self._trigger_proactive("APP_DETECTED", msg)

    async def _trigger_proactive(self, rule_name: str, message: str):
        # Double check state just before publishing
        if cognitive_core.current_state != AssistantState.IDLE:
            return
            
        self.rule_last_fired[rule_name] = datetime.now()
        logger.info(f"[ProactiveEngine] Triggering proactive rule '{rule_name}': {message}")
        
        from uuid import uuid4
        envelope = EventEnvelope(
            topic="friday.core.proactive_trigger",
            priority=EventPriority.P2,
            source="proactive_engine",
            correlation_id=uuid4(),
            session_id=uuid4(),
            payload={
                "rule": rule_name,
                "message": message
            }
        )
        await event_bus.publish(envelope)


proactive_engine = ProactiveEngine()
