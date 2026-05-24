import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useAtomValue } from "jotai";
import { mapModeAtom, wsConnectedAtom, aiStateAtom } from "../atoms";

export function ClockWidget() {
  const mapMode = useAtomValue(mapModeAtom);
  const connected = useAtomValue(wsConnectedAtom);
  const aiState = useAtomValue(aiStateAtom);
  const [time, setTime] = useState(new Date());

  useEffect(() => {
    const timer = setInterval(() => {
      setTime(new Date());
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  const formattedTime = time.toLocaleTimeString("en-IN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: true,
  });

  const formattedDate = time.toLocaleDateString("en-IN", {
    weekday: "short",
    month: "short",
    day: "numeric",
    year: "numeric",
  }).toUpperCase();

  const show = !mapMode;

  // Change aura color based on assistant state
  const getGlowColor = () => {
    switch (aiState) {
      case "LISTENING": return "rgba(6, 182, 212, 0.15)";
      case "THINKING": return "rgba(168, 85, 247, 0.15)";
      case "EXECUTING": return "rgba(245, 158, 11, 0.15)";
      case "SPEAKING": return "rgba(34, 197, 94, 0.15)";
      case "ERROR": return "rgba(239, 68, 68, 0.15)";
      default: return "rgba(99, 102, 241, 0.15)";
    }
  };

  const getAccentColor = () => {
    switch (aiState) {
      case "LISTENING": return "#06b6d4";
      case "THINKING": return "#a855f7";
      case "EXECUTING": return "#f59e0b";
      case "SPEAKING": return "#22c55e";
      case "ERROR": return "#ef4444";
      default: return "#6366f1";
    }
  };

  const accent = getAccentColor();

  return (
    <AnimatePresence>
      {show && (
        <motion.div
          key="clock-widget"
          initial={{ opacity: 0, y: -20, scale: 0.96 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: -16, scale: 0.96 }}
          transition={{ type: "spring", stiffness: 240, damping: 26, delay: 0.2 }}
          className="absolute top-28 right-4 z-30 md:top-32 md:right-5"
          style={{ width: 220 }}
        >
          <div
            className="relative overflow-hidden rounded-2xl border border-white/[0.07] select-none"
            style={{
              background: "linear-gradient(135deg, rgba(4,6,15,0.85) 0%, rgba(8,10,24,0.9) 100%)",
              backdropFilter: "blur(22px)",
              WebkitBackdropFilter: "blur(22px)",
              boxShadow: `0 0 0 1px rgba(255,255,255,0.04), 0 16px 40px rgba(0,0,0,0.50), 0 0 24px ${getGlowColor()}`,
            }}
          >
            {/* Top scanning HUD element */}
            <motion.div
              className="absolute inset-x-0 top-0 h-px"
              style={{ background: `linear-gradient(90deg, transparent, ${accent}cc, transparent)` }}
              animate={{ opacity: [0.4, 0.9, 0.4] }}
              transition={{ duration: 2.5, repeat: Infinity, ease: "easeInOut" }}
            />

            {/* Inner visual scanner */}
            <motion.div
              className="absolute right-3 top-3 h-2 w-2 rounded-full"
              style={{
                background: connected ? "#22c55e" : "#ef4444",
                boxShadow: connected ? "0 0 8px #22c55e" : "0 0 8px #ef4444",
              }}
              animate={{ opacity: [1, 0.4, 1] }}
              transition={{ duration: 1.8, repeat: Infinity }}
            />

            <div className="px-4 py-3.5">
              {/* Header Label */}
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-[8px] font-black tracking-[0.25em] text-white/30 uppercase">
                  CHRONOFEED // GLOBAL
                </span>
              </div>

              {/* Live updating digital clock */}
              <div className="flex items-baseline font-mono text-white tracking-tight">
                <span className="text-2xl font-bold font-display tracking-wide">{formattedTime}</span>
              </div>

              {/* Date string */}
              <p className="text-[9px] font-bold font-mono tracking-widest text-white/55 mt-1">
                {formattedDate}
              </p>

              {/* System Link Stats */}
              <div className="mt-2.5 pt-2 border-t border-white/[0.05] flex items-center justify-between">
                <span className="text-[7.5px] font-black tracking-wider text-white/20 uppercase">
                  SYSTEM CORE:
                </span>
                <span 
                  className="text-[8px] font-bold font-mono tracking-wider"
                  style={{ color: accent }}
                >
                  {aiState}
                </span>
              </div>
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
