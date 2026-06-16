import { motion, AnimatePresence } from "framer-motion";
import { useAtomValue } from "jotai";
import { aiStateAtom } from "../atoms";
import { sendStopSpeaking, unlockAudio } from "../hooks/useFridaySocket";
import { useMicLevel } from "../hooks/useMicLevel";

export function MicButton() {
  const { muted, setMuted } = useMicLevel();
  const aiState    = useAtomValue(aiStateAtom);
  const isSpeaking = aiState === "SPEAKING";

  const handleMicClick = () => {
    unlockAudio();
    setMuted(!muted);
    if (isSpeaking) {
      sendStopSpeaking();
    }
  };

  return (
    <div className="flex items-center justify-center gap-6 px-6 py-3 rounded-full border border-white/[0.05] bg-gradient-to-r from-slate-950/60 to-slate-900/60 backdrop-blur-xl shadow-[0_12px_40px_rgba(0,0,0,0.6)] relative z-10">

      {/* ── Mic toggle button ──────────────────────────────────────────────── */}
      <div className="relative flex flex-col items-center gap-1">
        <motion.button
          type="button"
          id="mic-toggle-btn"
          aria-label={muted ? "Unmute microphone" : "Mute microphone"}
          onClick={handleMicClick}
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.94 }}
          animate={{
            borderColor: muted ? "rgba(239,68,68,0.4)" : "rgba(6,182,212,0.4)",
            backgroundColor: muted ? "rgba(239,68,68,0.06)" : "rgba(6,182,212,0.06)",
            boxShadow: muted
              ? "0 0 20px rgba(239,68,68,0.12)"
              : "0 0 20px rgba(6,182,212,0.15)",
          }}
          transition={{ duration: 0.2 }}
          className="relative flex h-14 w-14 items-center justify-center rounded-full border backdrop-blur-md"
        >
          {muted ? (
            /* Muted — mic with red slash */
            <svg className="h-6 w-6 text-rose-500/90" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 18.75a6 6 0 006-6v-1.5m-6 7.5a6 6 0 01-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 15.75a3 3 0 01-3-3V4.5a3 3 0 116 0v8.25a3 3 0 01-3 3z" />
              <line x1="3" y1="3" x2="21" y2="21" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" />
            </svg>
          ) : (
            /* Active — mic icon full brightness */
            <svg className="h-6 w-6 text-cyan-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 18.75a6 6 0 006-6v-1.5m-6 7.5a6 6 0 01-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 15.75a3 3 0 01-3-3V4.5a3 3 0 116 0v8.25a3 3 0 01-3 3z" />
            </svg>
          )}

          {/* Red dot badge when muted */}
          <AnimatePresence>
            {muted && (
              <motion.span
                key="muted-badge"
                initial={{ scale: 0, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                exit={{ scale: 0, opacity: 0 }}
                transition={{ duration: 0.15 }}
                className="absolute -top-0.5 -right-0.5 h-2.5 w-2.5 rounded-full bg-rose-500 shadow-[0_0_8px_rgba(239,68,68,0.8)]"
              />
            )}
          </AnimatePresence>
        </motion.button>

        {/* Label below button */}
        <motion.span
          animate={{ color: muted ? "rgba(239,68,68,0.85)" : "rgba(6,182,212,0.85)" }}
          transition={{ duration: 0.2 }}
          className="text-[8px] font-bold tracking-widest uppercase font-mono"
        >
          {muted ? "MUTED" : "VOICE"}
        </motion.span>
      </div>

      {/* ── Stop speaking button — always visible ──────────────────────────── */}
      <div className="relative flex flex-col items-center gap-1">
        <motion.button
          type="button"
          id="stop-speaking-btn"
          aria-label="Stop speaking"
          onClick={() => sendStopSpeaking()}
          whileHover={{ scale: isSpeaking ? 1.05 : 1.0 }}
          whileTap={{ scale: 0.94 }}
          animate={{
            opacity: isSpeaking ? 1 : 0.22,
            scale:   isSpeaking ? 1 : 0.92,
            borderColor: isSpeaking ? "rgba(244,63,94,0.5)" : "rgba(255,255,255,0.1)",
          }}
          transition={{ duration: 0.20, ease: "easeOut" }}
          className="
            relative flex h-14 w-14 items-center justify-center rounded-full
            border bg-rose-500/[0.04] backdrop-blur-md
            shadow-[0_0_15px_rgba(239,68,68,0.06)]
            hover:shadow-[0_0_25px_rgba(239,68,68,0.18)]
            transition-shadow duration-150
          "
          style={{ pointerEvents: isSpeaking ? "auto" : "none", cursor: isSpeaking ? "pointer" : "default" }}
        >
          {/* ■ stop square */}
          <svg className="h-4.5 w-4.5 text-rose-400" fill="currentColor" viewBox="0 0 24 24">
            <rect x="5" y="5" width="14" height="14" rx="2" />
          </svg>
        </motion.button>

        <span className="text-[8px] font-bold tracking-widest uppercase text-white/20 font-mono">
          STOP
        </span>
      </div>

    </div>
  );
}
