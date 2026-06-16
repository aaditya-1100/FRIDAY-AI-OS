/**
 * RemindersPanel.tsx
 * Live countdown panel for active reminders, timers, and alarms.
 * Positioned in the bottom-right corner of the FRIDAY UI.
 */
import { motion, AnimatePresence } from "framer-motion";
import { useAtom } from "jotai";
import { useEffect, useState } from "react";
import { remindersAtom, reminderToastAtom, type ReminderItem } from "../atoms";
import { getWsSocket } from "../hooks/useFridaySocket";

// ─── Icon helpers ─────────────────────────────────────────────────────────────
function TypeIcon({ type }: { type: string }) {
  if (type === "timer") return (
    <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 3" /><path d="M9 2h6" />
    </svg>
  );
  if (type === "alarm") return (
    <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="12" cy="13" r="7" /><path d="M4 5l2 2M20 5l-2 2M12 6V2" />
      <path d="M12 13v-3" />
    </svg>
  );
  // reminder / recurring
  return (
    <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
      <path d="M13.73 21a2 2 0 0 1-3.46 0" />
    </svg>
  );
}

// ─── Countdown formatter ──────────────────────────────────────────────────────
function formatCountdown(seconds: number): string {
  if (seconds <= 0) return "Now";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s.toString().padStart(2, "0")}s`;
  return `${s}s`;
}

// ─── Single Reminder Pill ─────────────────────────────────────────────────────
function ReminderPill({ item, onCancel }: { item: ReminderItem; onCancel: (id: string) => void }) {
  const [remaining, setRemaining] = useState(item.remaining_seconds);

  useEffect(() => {
    setRemaining(item.remaining_seconds);
    const interval = setInterval(() => {
      setRemaining(prev => Math.max(0, prev - 1));
    }, 1000);
    return () => clearInterval(interval);
  }, [item.remaining_seconds]);

  const typeColor =
    item.type === "alarm" ? "text-rose-400 border-rose-400/20 bg-rose-400/5" :
    item.type === "timer" ? "text-amber-400 border-amber-400/20 bg-amber-400/5" :
    "text-cyan-400 border-cyan-400/20 bg-cyan-400/5";

  const label = item.text || (item.type === "alarm" ? "Alarm" : item.type === "timer" ? "Timer" : "Reminder");
  const isRecurring = item.type === "recurring";

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 12 }}
      transition={{ duration: 0.35 }}
      className={`flex items-center gap-2.5 rounded-xl border px-3 py-2.5 backdrop-blur-xl w-full ${typeColor}`}
    >
      {/* Icon */}
      <span className="shrink-0 opacity-80"><TypeIcon type={item.type} /></span>

      {/* Label + countdown */}
      <div className="flex-1 min-w-0">
        <p className="text-[11px] font-semibold truncate opacity-90 leading-tight">{label}</p>
        <p className="text-[10px] font-mono opacity-60 mt-0.5">
          {isRecurring ? "Daily" : remaining > 0 ? formatCountdown(remaining) : "Firing…"}
        </p>
      </div>

      {/* Dismiss button */}
      <button
        onClick={() => onCancel(item.id)}
        className="shrink-0 opacity-45 hover:opacity-85 transition-opacity"
        title="Cancel"
      >
        <svg className="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
          <path d="M18 6L6 18M6 6l12 12" />
        </svg>
      </button>
    </motion.div>
  );
}

// ─── Main Panel ───────────────────────────────────────────────────────────────
export function RemindersPanel() {
  const [reminders, setReminders] = useAtom(remindersAtom);
  const visible = reminders.length > 0;

  const handleCancel = (id: string) => {
    // Optimistic UI removal
    setReminders(prev => prev.filter(r => r.id !== id));
    // Send cancel command to backend
    const ws = getWsSocket();
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "command", text: `cancel reminder ${id}` }));
    }
  };

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 12 }}
          className="w-full flex flex-col gap-2 items-stretch mt-4"
        >
          <p className="text-[9px] tracking-widest text-white/20 font-black font-mono uppercase mb-0.5 pr-1">
            ACTIVE SCHEDULE // TIMERS
          </p>
          <AnimatePresence mode="popLayout">
            {reminders.map(item => (
              <ReminderPill key={item.id} item={item} onCancel={handleCancel} />
            ))}
          </AnimatePresence>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

// ─── Reminder Toast (fires when timer/alarm triggers) ────────────────────────
function toastAccentClass(type: string) {
  if (type === "alarm") return "from-rose-500/20 via-rose-400/10 border-rose-400/30";
  if (type === "timer") return "from-amber-500/20 via-amber-400/10 border-amber-400/30";
  return "from-cyan-500/20 via-cyan-400/10 border-cyan-400/30";
}

function toastIconBg(type: string) {
  if (type === "alarm") return "bg-rose-500/20 text-rose-400";
  if (type === "timer") return "bg-amber-500/20 text-amber-400";
  return "bg-cyan-500/20 text-cyan-400";
}

export function ReminderToastOverlay() {
  const [toast, setToast] = useAtom(reminderToastAtom);

  return (
    <AnimatePresence>
      {toast && (
        <motion.div
          initial={{ opacity: 0, y: -32, scale: 0.94 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: -24, scale: 0.94 }}
          transition={{ type: "spring", stiffness: 380, damping: 30 }}
          className="absolute top-6 inset-x-0 z-50 flex justify-center pointer-events-none px-4"
        >
          <div
            className={`pointer-events-auto flex items-center gap-4 rounded-2xl border bg-gradient-to-br ${toastAccentClass(toast.item_type)} backdrop-blur-2xl px-5 py-3.5 shadow-2xl`}
            style={{ maxWidth: 380 }}
          >
            {/* Icon bubble */}
            <div className={`shrink-0 flex items-center justify-center w-10 h-10 rounded-xl ${toastIconBg(toast.item_type)}`}>
              <TypeIcon type={toast.item_type} />
            </div>

            {/* Text */}
            <div className="flex-1 min-w-0">
              <p className="text-sm font-bold text-white leading-tight">{toast.title}</p>
              <p className="text-xs text-white/60 mt-0.5 truncate">{toast.body}</p>
            </div>

            {/* Dismiss */}
            <button
              onClick={() => setToast(null)}
              className="shrink-0 text-white/30 hover:text-white/80 transition-colors"
            >
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M18 6L6 18M6 6l12 12" />
              </svg>
            </button>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
