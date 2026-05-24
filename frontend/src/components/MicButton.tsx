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
    <div className="mt-6 flex items-center justify-center gap-4">

      {/* ── Mic toggle button ──────────────────────────────────────────────── */}
      <div className="relative flex flex-col items-center gap-1.5">
        <motion.button
          type="button"
          id="mic-toggle-btn"
          aria-label={muted ? "Unmute microphone" : "Mute microphone"}
          onClick={handleMicClick}
          whileHover={{ scale: 1.07 }}
          whileTap={{ scale: 0.92 }}
          animate={{
            borderColor: muted ? "rgba(255,80,80,0.5)" : "rgba(255,255,255,0.6)",
            backgroundColor: muted ? "rgba(255,40,40,0.10)" : "rgba(255,255,255,0.08)",
            boxShadow: muted
              ? "0 0 22px rgba(255,60,60,0.18)"
              : "0 0 28px rgba(255,255,255,0.14)",
          }}
          transition={{ duration: 0.2 }}
          className="relative flex h-16 w-16 items-center justify-center rounded-full border backdrop-blur-md"
        >
          {muted ? (
            /* Muted — mic with red slash */
            <svg className="h-7 w-7 text-red-400/90" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 18.75a6 6 0 006-6v-1.5m-6 7.5a6 6 0 01-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 15.75a3 3 0 01-3-3V4.5a3 3 0 116 0v8.25a3 3 0 01-3 3z" />
              <line x1="3" y1="3" x2="21" y2="21" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" />
            </svg>
          ) : (
            /* Active — mic icon full brightness */
            <svg className="h-7 w-7 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
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
                className="absolute -top-1 -right-1 h-3 w-3 rounded-full bg-red-500 shadow-[0_0_8px_rgba(255,60,60,0.8)]"
              />
            )}
          </AnimatePresence>
        </motion.button>

        {/* Label below button */}
        <motion.span
          animate={{ color: muted ? "rgba(255,100,100,0.85)" : "rgba(255,255,255,0.45)" }}
          transition={{ duration: 0.2 }}
          className="text-[10px] font-medium tracking-widest uppercase"
        >
          {muted ? "Muted" : "Mic"}
        </motion.span>
      </div>

      {/* ── Stop speaking button — always visible ──────────────────────────── */}
      <div className="relative flex flex-col items-center gap-1.5">
        <motion.button
          type="button"
          id="stop-speaking-btn"
          aria-label="Stop speaking"
          onClick={() => sendStopSpeaking()}
          whileHover={{ scale: isSpeaking ? 1.07 : 1.0 }}
          whileTap={{ scale: 0.92 }}
          animate={{
            opacity: isSpeaking ? 1 : 0.28,
            scale:   isSpeaking ? 1 : 0.90,
          }}
          transition={{ duration: 0.20, ease: "easeOut" }}
          className="
            relative flex h-16 w-16 items-center justify-center rounded-full
            border border-red-400/40 bg-red-500/[0.08] backdrop-blur-md
            shadow-[0_0_20px_rgba(255,80,80,0.12)]
            hover:border-red-400/70 hover:shadow-[0_0_30px_rgba(255,80,80,0.22)]
            transition-shadow duration-150
          "
          style={{ pointerEvents: isSpeaking ? "auto" : "none", cursor: isSpeaking ? "pointer" : "default" }}
        >
          {/* ■ stop square */}
          <svg className="h-5 w-5 text-red-300/90" fill="currentColor" viewBox="0 0 24 24">
            <rect x="5" y="5" width="14" height="14" rx="2.5" />
          </svg>
        </motion.button>

        <span className="text-[10px] font-medium tracking-widest uppercase text-white/30">
          Stop
        </span>
      </div>

    </div>
  );
}
