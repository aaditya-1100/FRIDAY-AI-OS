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
          initial={{ opacity: 0, y: -12 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -12 }}
          transition={{ duration: 0.35 }}
          className="w-full relative"
        >
          <div
            className="glass-panel overflow-hidden rounded-2xl select-none"
            style={{
              boxShadow: `0 0 24px ${getGlowColor()}`,
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
              className="absolute right-4 top-4 h-2 w-2 rounded-full animate-pulse-hud"
              style={{
                background: connected ? "#22c55e" : "#ef4444",
                boxShadow: connected ? "0 0 8px #22c55e" : "0 0 8px #ef4444",
              }}
            />
 
            <div className="px-5 py-4">
              {/* Header Label */}
              <div className="flex items-center justify-between mb-2">
                <span className="text-[9px] font-black tracking-[0.25em] text-white/35 font-mono uppercase">
                  CHRONOFEED // GLOBAL
                </span>
              </div>
 
              {/* Live updating digital clock */}
              <div className="flex items-baseline font-mono text-white tracking-tight">
                <span className="text-3xl font-extrabold tracking-wide font-space text-white/90">{formattedTime}</span>
              </div>
 
              {/* Date string */}
              <p className="text-[10px] font-semibold font-mono tracking-widest text-white/50 mt-1.5 uppercase">
                {formattedDate}
              </p>
 
              {/* System Link Stats */}
              <div className="mt-3.5 pt-2.5 border-t border-white/[0.04] flex items-center justify-between">
                <span className="text-[8px] font-bold tracking-wider text-white/25 font-mono uppercase">
                  STATE CORE:
                </span>
                <span 
                  className="text-[9px] font-black font-mono tracking-widest uppercase"
                  style={{ color: accent, textShadow: `0 0 8px ${accent}44` }}
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
