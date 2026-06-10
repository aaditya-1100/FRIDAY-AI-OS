import os
import re
import json
import asyncio
from datetime import datetime, timedelta
import uuid

# ─── NATURAL LANGUAGE TIME PARSING ──────────────────────────────────────────

def parse_temporal_expression(expr: str, now: datetime = None) -> tuple[datetime | None, str | None, int | None]:
    """
    Parses a natural language time expression.
    Returns (target_datetime, recurrence_type, duration_seconds).
    recurrence_type can be: "daily", "weekly", or None.
    """
    if now is None:
        now = datetime.now()
    
    expr = expr.lower().strip()
    
    # 1. Timer / Relative Duration: "in 5 minutes", "after 2 hours", "for 15 seconds"
    rel_match = re.search(r'\b(?:in|after|for)\s+(\d+)\s*(sec|second|min|minute|hour|hr|day|d)s?\b', expr)
    if rel_match:
        val = int(rel_match.group(1))
        unit = rel_match.group(2)
        if unit in ('sec', 'second'):
            delta = timedelta(seconds=val)
        elif unit in ('min', 'minute'):
            delta = timedelta(minutes=val)
        elif unit in ('hour', 'hr'):
            delta = timedelta(hours=val)
        elif unit in ('day', 'd'):
            delta = timedelta(days=val)
        else:
            delta = timedelta(minutes=val)
        return now + delta, None, int(delta.total_seconds())

    # 2. Recurring everyday: "every day at 9", "every day at 9 AM", "daily at 10 PM"
    rec_match = re.search(r'\b(?:every\s+day|daily)\s*(?:at\s+(\d+)(?::(\d+))?\s*(am|pm)?)?\b', expr)
    if rec_match:
        hour = 9
        minute = 0
        if rec_match.group(1):
            hour = int(rec_match.group(1))
            if rec_match.group(2):
                minute = int(rec_match.group(2))
            meridian = rec_match.group(3)
            if meridian == 'pm' and hour < 12:
                hour += 12
            elif meridian == 'am' and hour == 12:
                hour = 0
        
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        return target, "daily", None

    # 3. Next day-of-week: "next monday", "next Friday at 6 PM"
    dow_match = re.search(r'\bnext\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b', expr)
    if dow_match:
        dow_str = dow_match.group(1)
        dows = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        target_dow = dows.index(dow_str)
        current_dow = now.weekday()
        days_ahead = target_dow - current_dow
        if days_ahead <= 0:
            days_ahead += 7
        target_date = now.date() + timedelta(days=days_ahead)
        
        hour = 9
        minute = 0
        time_match = re.search(r'\bat\s+(\d+)(?::(\d+))?\s*(am|pm)?\b', expr)
        if time_match:
            hour = int(time_match.group(1))
            if time_match.group(2):
                minute = int(time_match.group(2))
            meridian = time_match.group(3)
            if meridian == 'pm' and hour < 12:
                hour += 12
            elif meridian == 'am' and hour == 12:
                hour = 0
        
        target = datetime.combine(target_date, datetime.min.time()).replace(hour=hour, minute=minute)
        return target, None, None

    # 4. Absolute combinations: "tomorrow at 5 PM", "tomorrow morning"
    tomorrow_match = "tomorrow" in expr
    if tomorrow_match:
        target_date = now.date() + timedelta(days=1)
        hour = 9
        minute = 0
        if "morning" in expr:
            hour = 9
        elif "afternoon" in expr:
            hour = 14
        elif "evening" in expr:
            hour = 18
        elif "night" in expr:
            hour = 21
            
        time_match = re.search(r'\bat\s+(\d+)(?::(\d+))?\s*(am|pm)?\b', expr)
        if time_match:
            hour = int(time_match.group(1))
            if time_match.group(2):
                minute = int(time_match.group(2))
            meridian = time_match.group(3)
            if meridian == 'pm' and hour < 12:
                hour += 12
            elif meridian == 'am' and hour == 12:
                hour = 0
                
        target = datetime.combine(target_date, datetime.min.time()).replace(hour=hour, minute=minute)
        return target, None, None

    # 5. Generic absolute time: "at 6 AM", "at 18:30"
    abs_time_match = re.search(r'\bat\s+(\d+)(?::(\d+))?\s*(am|pm)?\b', expr)
    if abs_time_match:
        hour = int(abs_time_match.group(1))
        minute = 0
        if abs_time_match.group(2):
            minute = int(abs_time_match.group(2))
        meridian = abs_time_match.group(3)
        if meridian == 'pm' and hour < 12:
            hour += 12
        elif meridian == 'am' and hour == 12:
            hour = 0
            
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        return target, None, None

    # 6. Fallback default: minutes match E.g. "in 10m"
    num_match = re.search(r'\b(\d+)\s*(m|min|minutes)\b', expr)
    if num_match:
        delta = timedelta(minutes=int(num_match.group(1)))
        return now + delta, None, int(delta.total_seconds())

    return None, None, None


# ─── TEMPORAL STATE PERSISTENCE & MANAGEMENT ─────────────────────────────────

class TemporalEngine:
    def __init__(self):
        self.reminders = []
        self.stopwatch = {
            "start_time": None,
            "elapsed_seconds": 0.0,
            "running": False
        }
        # Unified persistent state path
        self.state_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "temporal_state.json")
        self._scheduler_task = None
        self._lock = asyncio.Lock()

    def load_state(self):
        """Loads temporal reminders and stopwatch state from JSON file."""
        if not os.path.exists(self.state_file):
            # Create data folder if not exists
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            self.save_state()
            return
        
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                state = json.load(f)
                self.reminders = state.get("reminders", [])
                self.stopwatch = state.get("stopwatch", {
                    "start_time": None,
                    "elapsed_seconds": 0.0,
                    "running": False
                })
                print(f"[TEMPORAL] State loaded cleanly. Reminders active: {len(self.reminders)}")
        except Exception as e:
            print(f"[TEMPORAL WARNING] Failed to load persistent state: {e}")

    def save_state(self):
        """Saves current state persistently to JSON file using an atomic write pattern."""
        try:
            dir_name = os.path.dirname(self.state_file)
            os.makedirs(dir_name, exist_ok=True)
            state = {
                "reminders": self.reminders,
                "stopwatch": self.stopwatch
            }
            import tempfile
            # Write to a temporary file in the same directory to ensure atomic replace
            with tempfile.NamedTemporaryFile("w", dir=dir_name, delete=False, encoding="utf-8") as f:
                temp_path = f.name
                json.dump(state, f, indent=2)
            
            os.replace(temp_path, self.state_file)
        except Exception as e:
            print(f"[TEMPORAL WARNING] Failed to save persistent state: {e}")
            if 'temp_path' in locals() and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass

    # ─── REMINDER & TIMER OPERATIONS ──────────────────────────────────────────

    async def add_reminder(self, item_type: str, text: str, time_expr: str) -> str:
        """Parses time expression and registers a new active reminder/timer."""
        now = datetime.now()
        target_time, recurrence, duration = parse_temporal_expression(time_expr, now)
        
        if not target_time:
            return "I could not resolve that time expression, sir."
        
        new_id = str(uuid.uuid4())[:8]
        new_item = {
            "id": new_id,
            "type": item_type,
            "text": text,
            "created_at": now.isoformat(),
            "target_time": target_time.isoformat(),
            "recurrence": recurrence,
            "duration_seconds": duration,
            "active": True
        }
        
        async with self._lock:
            self.reminders.append(new_item)
            self.save_state()

        # Broadcast updated list to frontend
        try:
            await self._emit_reminder_list()
        except Exception as e_emit:
            print(f"[TEMPORAL] Failed to emit reminder_list after add: {e_emit}")

        time_str = target_time.strftime("%I:%M %p")
        if item_type == "timer" and duration:
            return f"Timer set for {self._format_seconds(duration)} sir."
        elif item_type == "recurring":
            return f"Recurring reminder set for {text} daily at {time_str} sir."
        elif "tomorrow" in time_expr.lower():
            return f"Reminder set for {text} tomorrow at {time_str} sir."
        else:
            delta = target_time - now
            if delta.total_seconds() < 3600:
                mins = int(delta.total_seconds() // 60)
                return f"Reminder set for {text} in {mins} minute{'s' if mins != 1 else ''} sir."
            return f"Reminder set for {text} at {time_str} sir."

    async def list_reminders(self) -> str:
        """Lists active reminders, countdown timers, and alarms."""
        async with self._lock:
            active_items = [r for r in self.reminders if r.get("active", True)]
        
        if not active_items:
            return "There are no active reminders, timers, or alarms currently scheduled, sir."
        
        out = []
        for it in active_items:
            t = datetime.fromisoformat(it["target_time"])
            time_str = t.strftime("%I:%M %p")
            text = it.get("text", "").strip()
            
            short_id = it['id'][:6]
            if it["type"] == "timer":
                rem_seconds = int((t - datetime.now()).total_seconds())
                if rem_seconds > 0:
                    out.append(f"• Timer [{short_id}]: {self._format_seconds(rem_seconds)} remaining")
                else:
                    out.append(f"• Timer [{short_id}]: completed")
            elif it["type"] == "recurring":
                out.append(f"• Daily reminder [{short_id}]: \"{text}\" at {time_str}")
            elif it["type"] == "alarm":
                out.append(f"• Alarm [{short_id}]: set for {time_str}")
            else:
                out.append(f"• Reminder [{short_id}]: \"{text}\" at {time_str}")
                
        return "Here is your active schedule, sir:\n" + "\n".join(out)

    async def cancel_reminder(self, query: str) -> str:
        """Cancels a reminder or timer by matching keyword query."""
        q = query.lower().strip()
        if not q:
            return "Please specify which reminder to cancel, sir."
            
        response_text = "I couldn't find a matching active reminder to cancel, sir."
        async with self._lock:
            active_items = [r for r in self.reminders if r.get("active", True)]
            match = None
            for it in active_items:
                # Match by ID or text content
                if it["id"] in q or (it.get("text") and it["text"].lower() in q) or (it["type"] in q and len(active_items) == 1):
                    match = it
                    break
            
            if not match and active_items:
                # Fallback to the latest set item
                match = active_items[-1]
                
            if match:
                match["active"] = False
                self.save_state()
                name = match.get("text") or match["type"]
                response_text = f"Stood down the {name} schedule, sir."
        
        # Broadcast updated list to frontend
        try:
            await self._emit_reminder_list()
        except Exception as e_emit:
            print(f"[TEMPORAL] Failed to emit reminder_list after cancel: {e_emit}")
        
        return response_text

    # ─── STOPWATCH SYSTEM ─────────────────────────────────────────────────────

    def start_stopwatch(self) -> str:
        """Starts the stopwatch."""
        if self.stopwatch["running"]:
            return "Stopwatch is already running, sir."
        
        self.stopwatch["start_time"] = datetime.now().isoformat()
        self.stopwatch["running"] = True
        self.save_state()
        return "Stopwatch started, sir."

    def stop_stopwatch(self) -> str:
        """Stops the stopwatch and returns the elapsed time."""
        if not self.stopwatch["running"]:
            if self.stopwatch["elapsed_seconds"] > 0:
                elapsed = self.stopwatch["elapsed_seconds"]
                return f"Stopwatch is not running. Stored elapsed split is {self._format_seconds(elapsed)} sir."
            return "Stopwatch is not running, sir."
        
        start = datetime.fromisoformat(self.stopwatch["start_time"])
        now = datetime.now()
        delta = (now - start).total_seconds()
        total = self.stopwatch["elapsed_seconds"] + delta
        
        self.stopwatch["elapsed_seconds"] = total
        self.stopwatch["start_time"] = None
        self.stopwatch["running"] = False
        self.save_state()
        
        return f"Stopwatch stopped, sir. Total elapsed time: {self._format_seconds(total)}."

    def pause_stopwatch(self) -> str:
        """Pauses the stopwatch."""
        if not self.stopwatch["running"]:
            return "Stopwatch is not currently running, sir."
            
        start = datetime.fromisoformat(self.stopwatch["start_time"])
        now = datetime.now()
        delta = (now - start).total_seconds()
        
        self.stopwatch["elapsed_seconds"] += delta
        self.stopwatch["start_time"] = None
        self.stopwatch["running"] = False
        self.save_state()
        return f"Stopwatch paused at {self._format_seconds(self.stopwatch['elapsed_seconds'])} sir."

    def resume_stopwatch(self) -> str:
        """Resumes the paused stopwatch."""
        if self.stopwatch["running"]:
            return "Stopwatch is already running, sir."
        
        self.stopwatch["start_time"] = datetime.now().isoformat()
        self.stopwatch["running"] = True
        self.save_state()
        return "Resuming stopwatch, sir."

    def reset_stopwatch(self) -> str:
        """Resets the stopwatch."""
        self.stopwatch = {
            "start_time": None,
            "elapsed_seconds": 0.0,
            "running": False
        }
        self.save_state()
        return "Stopwatch reset to zero, sir."

    def get_stopwatch_status(self) -> str:
        """Returns the current stopwatch reading."""
        if self.stopwatch["running"]:
            start = datetime.fromisoformat(self.stopwatch["start_time"])
            now = datetime.now()
            delta = (now - start).total_seconds()
            total = self.stopwatch["elapsed_seconds"] + delta
            return f"Stopwatch is currently running, sir. Reading: {self._format_seconds(total)}."
        elif self.stopwatch["elapsed_seconds"] > 0:
            return f"Stopwatch is paused at {self._format_seconds(self.stopwatch['elapsed_seconds'])} sir."
        return "Stopwatch is stopped and reset, sir."

    # ─── BACKGROUND SCHEDULER TICK LOOP ───────────────────────────────────────

    def start_scheduler(self, loop):
        """Starts the persistent background async loop."""
        self.load_state()
        self._scheduler_task = loop.create_task(self._scheduler_loop())
        print("[TEMPORAL] Background tick scheduler thread registered.")

    async def _scheduler_loop(self):
        while True:
            try:
                await self._tick()
            except Exception as e:
                print(f"[TEMPORAL TICK ERROR] {e}")
            await asyncio.sleep(1.0)

    async def _tick(self):
        now = datetime.now()
        triggered = []
        
        async with self._lock:
            for it in self.reminders:
                if not it.get("active", True):
                    continue
                
                target = datetime.fromisoformat(it["target_time"])
                if now >= target:
                    triggered.append(it)

            for it in triggered:
                # Execute trigger async so it doesn't block the scheduler thread
                asyncio.create_task(self._trigger_item(it))
                
                if it["recurrence"] == "daily":
                    # Reschedule for tomorrow
                    next_target = datetime.fromisoformat(it["target_time"]) + timedelta(days=1)
                    it["target_time"] = next_target.isoformat()
                elif it["recurrence"] == "weekly":
                    # Reschedule for next week
                    next_target = datetime.fromisoformat(it["target_time"]) + timedelta(weeks=1)
                    it["target_time"] = next_target.isoformat()
                else:
                    it["active"] = False
            
            if triggered:
                self.save_state()

    async def _trigger_item(self, item):
        """Triggers direct TTS, visual sync, and WebSocket event on reminder fire."""
        it_type = item["type"]
        text = item.get("text", "").strip()
        target_time = datetime.fromisoformat(item["target_time"])
        time_str = target_time.strftime("%I:%M %p")
        
        if it_type == "timer" and item.get("duration_seconds"):
            dur_str = self._format_seconds(item["duration_seconds"])
            speech = f"Sir, your {dur_str} timer is up."
            toast_title = "Timer Complete"
            toast_body = f"{dur_str} timer finished."
        elif it_type == "alarm":
            speech = f"Sir, your alarm is going off. The time is {time_str}."
            toast_title = "Alarm"
            toast_body = f"Alarm set for {time_str}."
        elif it_type == "recurring":
            speech = f"Sir, your daily reminder: {text}."
            toast_title = "Daily Reminder"
            toast_body = text
        else:
            speech = f"Sir, reminder: {text}."
            toast_title = "Reminder"
            toast_body = text
            
        print(f"[TEMPORAL TRIGGER] Firing schedule: {it_type} - {text!r}")
        
        # Emit reminder_fired event to all connected WebSocket clients
        try:
            from core.realtime_emit import emit_json
            await emit_json({
                "type": "reminder_fired",
                "item_type": it_type,
                "title": toast_title,
                "body": toast_body,
                "id": item.get("id", ""),
            })
        except Exception as e_ws:
            print(f"[TEMPORAL TRIGGER] WS emit failed: {e_ws}")
        
        try:
            # Dynamically import to prevent circular import chain
            from core.pipeline import safe_speak
            await safe_speak(speech)
        except Exception as e:
            print(f"[TEMPORAL TRIGGER ERROR] safe_speak call failed: {e}")
        
        # After firing, broadcast updated reminder list
        try:
            await self._emit_reminder_list()
        except Exception as e_list:
            print(f"[TEMPORAL TRIGGER] Failed to emit updated reminder list: {e_list}")

    async def _emit_reminder_list(self):
        """Broadcasts the current active reminder list to all WS clients."""
        try:
            from core.realtime_emit import emit_json
            async with self._lock:
                active = [r for r in self.reminders if r.get("active", True)]
            items = []
            now = datetime.now()
            for it in active:
                t = datetime.fromisoformat(it["target_time"])
                rem_secs = max(0, int((t - now).total_seconds()))
                items.append({
                    "id": it["id"],
                    "type": it["type"],
                    "text": it.get("text", ""),
                    "target_time": it["target_time"],
                    "recurrence": it.get("recurrence"),
                    "duration_seconds": it.get("duration_seconds"),
                    "remaining_seconds": rem_secs,
                })
            await emit_json({"type": "reminder_list", "items": items})
        except Exception as e:
            print(f"[TEMPORAL] _emit_reminder_list error: {e}")

    # ─── UTILITIES ────────────────────────────────────────────────────────────

    def _format_seconds(self, seconds: float) -> str:
        s = int(seconds)
        if s < 60:
            return f"{s} second{'s' if s != 1 else ''}"
        m = s // 60
        rem_s = s % 60
        if rem_s == 0:
            return f"{m} minute{'s' if m != 1 else ''}"
        return f"{m} minute{'s' if m != 1 else ''} and {rem_s} second{'s' if rem_s != 1 else ''}"


def item_id_prefix(item_id: str) -> str:
    return f"ID: {item_id}"


# Global Singleton Instance
temporal_engine = TemporalEngine()
