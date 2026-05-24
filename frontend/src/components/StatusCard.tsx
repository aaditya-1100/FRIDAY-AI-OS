import { useAtomValue } from "jotai";
import { motion, AnimatePresence } from "framer-motion";
import { aiStateAtom, transcriptAtom, speakTextAtom, commandErrorAtom, wsConnectedAtom, mapModeAtom } from "../atoms";

const STATE_META = {
  IDLE:      { label: "STANDBY",   dot: "#6366f1", glow: "rgba(99,102,241,0.4)"  },
  LISTENING: { label: "LISTENING", dot: "#06b6d4", glow: "rgba(6,182,212,0.4)"   },
  THINKING:  { label: "THINKING",  dot: "#a855f7", glow: "rgba(168,85,247,0.4)"  },
  EXECUTING: { label: "EXECUTING", dot: "#f59e0b", glow: "rgba(245,158,11,0.4)"  },
  SPEAKING:  { label: "SPEAKING",  dot: "#22c55e", glow: "rgba(34,197,94,0.4)"   },
  ERROR:     { label: "ERROR",     dot: "#ef4444", glow: "rgba(239,68,68,0.4)"   },
};

export function StatusCard() {
  const aiState   = useAtomValue(aiStateAtom);
  const transcript = useAtomValue(transcriptAtom);
  const speakText  = useAtomValue(speakTextAtom);
  const error      = useAtomValue(commandErrorAtom);
  const connected  = useAtomValue(wsConnectedAtom);
  const mapMode    = useAtomValue(mapModeAtom);

  const meta = STATE_META[aiState] ?? STATE_META.IDLE;
  const hasContent = !!transcript || !!speakText || !!error;
  // Show panel whenever there's content or when active, but automatically hide during map/globe mode to prevent blocking the map view
  const isVisible  = !mapMode && (hasContent || (connected && aiState !== "IDLE"));

  return (
    <AnimatePresence>
      {isVisible && (
        <motion.div
          key="status-panel"
          initial={{ opacity: 0, x: 32, scale: 0.97 }}
          animate={{ opacity: 1, x: 0,  scale: 1    }}
          exit={{    opacity: 0, x: 32, scale: 0.97 }}
          transition={{ type: "spring", stiffness: 280, damping: 28 }}
          // Right-side floating panel — doesn't overlap orb or mic
          className="absolute right-4 top-1/2 z-50 w-64 -translate-y-1/2 md:right-6 md:w-72"
        >
          <div
            className="relative overflow-hidden rounded-2xl border border-white/[0.08] shadow-2xl"
            style={{
              background: "linear-gradient(135deg, rgba(5,8,20,0.85) 0%, rgba(10,14,30,0.92) 100%)",
              backdropFilter: "blur(24px)",
              WebkitBackdropFilter: "blur(24px)",
              boxShadow: `0 0 0 1px rgba(255,255,255,0.05), 0 24px 48px rgba(0,0,0,0.5), 0 0 20px ${meta.glow}22`,
            }}
          >
            {/* Top accent glow bar */}
            <div
              className="absolute inset-x-0 top-0 h-px"
              style={{ background: `linear-gradient(90deg, transparent, ${meta.dot}99, transparent)` }}
            />

            {/* State header */}
            <div className="flex items-center gap-2.5 px-4 pt-4 pb-3">
              {/* Animated status dot */}
              <span className="relative flex h-2 w-2 shrink-0">
                <span
                  className="absolute inline-flex h-full w-full rounded-full animate-ping opacity-60"
                  style={{ backgroundColor: meta.dot }}
                />
                <span
                  className="relative inline-flex h-2 w-2 rounded-full"
                  style={{ backgroundColor: meta.dot, boxShadow: `0 0 6px ${meta.dot}` }}
                />
              </span>
              <span
                className="text-[10px] font-black tracking-[0.3em] uppercase"
                style={{ color: meta.dot }}
              >
                {meta.label}
              </span>
              {/* Subtle connection indicator */}
              <span className="ml-auto text-[9px] text-white/20 font-mono tracking-wider">
                {connected ? "● LINK" : "○ ---"}
              </span>
            </div>

            {/* Divider */}
            <div className="mx-4 h-px bg-white/[0.05]" />

            {/* Content area */}
            <div className="px-4 py-3 space-y-3">

              {/* User transcript */}
              <AnimatePresence mode="wait">
                {transcript && (
                  <motion.div
                    key={transcript}
                    initial={{ opacity: 0, y: 4 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{    opacity: 0, y: -4 }}
                    transition={{ duration: 0.2 }}
                  >
                    <p className="text-[9px] font-bold tracking-[0.25em] text-white/30 mb-1.5 uppercase">
                      You said
                    </p>
                    <p className="text-[13px] font-medium text-white/85 leading-relaxed">
                      "{transcript}"
                    </p>
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Divider between transcript and response */}
              {transcript && speakText && (
                <div className="h-px bg-white/[0.04]" />
              )}

              {/* AI response */}
              <AnimatePresence mode="wait">
                {speakText && (
                  <motion.div
                    key={speakText.slice(0, 20)}
                    initial={{ opacity: 0, y: 4 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{    opacity: 0, y: -4 }}
                    transition={{ duration: 0.25, delay: 0.05 }}
                  >
                    <p
                      className="text-[9px] font-bold tracking-[0.25em] mb-1.5 uppercase"
                      style={{ color: `${meta.dot}99` }}
                    >
                      FRIDAY
                    </p>
                    <p className="text-[13px] font-medium leading-relaxed max-h-36 overflow-y-auto"
                      style={{ color: `${meta.dot}dd` }}
                    >
                      {speakText}
                    </p>
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Error */}
              <AnimatePresence>
                {error && (
                  <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{    opacity: 0 }}
                    className="rounded-lg border border-red-500/20 bg-red-950/20 px-3 py-2"
                  >
                    <p className="text-[9px] font-bold tracking-[0.2em] text-red-400 mb-1">ERROR</p>
                    <p className="text-[12px] text-red-300/80 font-mono">{error}</p>
                  </motion.div>
                )}
              </AnimatePresence>

            </div>

            {/* Bottom accent */}
            <div className="h-px mx-4 mb-4 bg-white/[0.03]" />

            {/* FRIDAY signature */}
            <p className="pb-3 text-center text-[8px] font-bold tracking-[0.4em] text-white/10 uppercase">
              F · R · I · D · A · Y
            </p>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
