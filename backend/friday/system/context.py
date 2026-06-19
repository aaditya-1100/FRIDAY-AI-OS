# backend/friday/system/context.py

import asyncio
import datetime
from typing import Dict, Any, Optional
from uuid import uuid4
from loguru import logger
from friday.core.events import EventEnvelope, EventPriority

class SystemContext:
    def __init__(self):
        self.current_time: str = ""
        self.current_date: str = ""
        self.battery_level: Optional[float] = None
        self.active_window: Optional[str] = None
        self.cpu_percent: float = 0.0
        self.memory_percent: float = 0.0
        self._bus = None
        self._task = None
        self._running = False
        
    async def start(self, bus) -> None:
        if self._running:
            return
        self._bus = bus
        self._running = True
        self.collect_metrics()
        self._task = asyncio.create_task(self._loop())
        logger.info("[SystemContext] Background loop started.")
        
    def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("[SystemContext] Background loop stopped.")
        
    def collect_metrics(self) -> None:
        try:
            import psutil
            import pygetwindow
            
            now = datetime.datetime.now()
            self.current_time = now.isoformat()
            self.current_date = now.date().isoformat()
            
            try:
                battery = psutil.sensors_battery()
                self.battery_level = float(battery.percent) if battery else None
            except Exception as e:
                logger.warning(f"[SystemContext] Failed to get battery level: {e}")
                self.battery_level = None
                
            try:
                win = pygetwindow.getActiveWindow()
                self.active_window = win.title if win else None
            except Exception as e:
                logger.warning(f"[SystemContext] Failed to get active window: {e}")
                self.active_window = None
                
            self.cpu_percent = float(psutil.cpu_percent(interval=None))
            self.memory_percent = float(psutil.virtual_memory().percent)
        except Exception as e:
            logger.error(f"[SystemContext] Critical error collecting metrics: {e}")
            
    def get_app_id(self, title: Optional[str]) -> str:
        if not title:
            return "general"
        title_lower = title.lower()
        if "visual studio code" in title_lower or "code -" in title_lower:
            return "vscode"
        if "chrome" in title_lower or "chromium" in title_lower:
            return "chrome"
        if "firefox" in title_lower:
            return "firefox"
        if "premiere" in title_lower:
            return "premiere"
        if "spotify" in title_lower:
            return "spotify"
        if "explorer" in title_lower:
            return "explorer"
        return "general"

    def get_context(self) -> Dict[str, Any]:
        app_id = self.get_app_id(self.active_window)
        return {
            "current_time": self.current_time,
            "current_date": self.current_date,
            "battery_level": self.battery_level,
            "active_window": self.active_window,
            "app_id": app_id,
            "cpu_percent": self.cpu_percent,
            "memory_percent": self.memory_percent
        }
        
    async def _loop(self) -> None:
        # Publish first update immediately
        await self._publish_update()
        while self._running:
            try:
                await asyncio.sleep(60)
                self.collect_metrics()
                await self._publish_update()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[SystemContext] Error in context loop: {e}")
                await asyncio.sleep(5)
                
    async def _publish_update(self) -> None:
        if not self._bus:
            return
        envelope = EventEnvelope(
            topic="friday.system.context_update",
            priority=EventPriority.P3,
            source="system.context",
            correlation_id=uuid4(),
            session_id=uuid4(),
            payload=self.get_context()
        )
        await self._bus.publish(envelope)
        logger.debug(f"[SystemContext] Published context_update: {self.get_context()}")

system_context = SystemContext()
