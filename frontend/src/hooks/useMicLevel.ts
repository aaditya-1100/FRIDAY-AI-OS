import { useAtom, useAtomValue } from "jotai";
import { useEffect, useRef, useCallback } from "react";
import { aiStateAtom, micLevelAtom, micMutedAtom } from "../atoms";
import { getWsSocket, sendStopSpeaking } from "./useFridaySocket";

function sendMicMsg(type: "mic_on" | "mic_off") {
  const ws = getWsSocket();
  if (ws?.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type }));
    console.log(`[MIC] Sent ${type} to backend`);
  } else {
    console.warn(`[MIC] WebSocket not open, cannot send ${type}`);
  }
}

export function useMicLevel() {
  const [muted, setMutedRaw] = useAtom(micMutedAtom);
  const [, setLevel]         = useAtom(micLevelAtom);
  const aiState              = useAtomValue(aiStateAtom);
  const ctxRef               = useRef<AudioContext | null>(null);
  const streamRef            = useRef<MediaStream | null>(null);
  const rafRef               = useRef<number>(0);
  const mutedRef             = useRef(muted);
  const aiStateRef           = useRef(aiState);
  // Interruption debounce: count consecutive frames above threshold
  const interruptCountRef    = useRef(0);
  // Prevent re-triggering within the same SPEAKING cycle
  const interruptFiredRef    = useRef(false);

  // Keep ref in sync so event handlers always see latest value
  mutedRef.current = muted;
  aiStateRef.current = aiState;
  // Reset interruption state when we leave SPEAKING
  if (aiState !== "SPEAKING") {
    interruptCountRef.current = 0;
    interruptFiredRef.current = false;
  }

  // Stable setter that also notifies backend
  const setMuted = useCallback((value: boolean) => {
    setMutedRaw(value);
    sendMicMsg(value ? "mic_off" : "mic_on");
  }, [setMutedRaw]);

  useEffect(() => {
    if (muted) {
      // ── Muted: tear down mic stream immediately ───────────────────────────
      cancelAnimationFrame(rafRef.current);
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
      ctxRef.current?.close().catch(() => {});
      ctxRef.current = null;
      setLevel(0);
      return;
    }

    // ── Unmuted: start mic stream ──────────────────────────────────────────
    let cancelled = false;
    const data = new Uint8Array(256);

    (async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        if (!stream) {
          setLevel(0);
          return;
        }
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;

        const ctx = new AudioContext();
        ctxRef.current = ctx;

        const src      = ctx.createMediaStreamSource(stream);
        const analyser = ctx.createAnalyser();
        analyser.fftSize = 512;
        analyser.smoothingTimeConstant = 0.55;
        src.connect(analyser);

        const tick = () => {
          if (cancelled) return;
          analyser.getByteFrequencyData(data);
          let sum = 0;
          for (let i = 0; i < data.length; i++) sum += data[i];
          const avg = (sum / data.length / 255) * 2.2;
          const currentLevel = Math.min(1, avg);
          setLevel(currentLevel);

          // Voice interruption: user must speak loudly and consistently for
          // 8 consecutive frames (~133ms at 60fps) to avoid spurious triggers.
          if (aiStateRef.current === "SPEAKING" && !interruptFiredRef.current) {
            if (currentLevel > 0.45) {
              interruptCountRef.current += 1;
              if (interruptCountRef.current >= 8) {
                console.log(`[MIC] Interruption confirmed: ${interruptCountRef.current} frames above threshold (level=${currentLevel.toFixed(2)})`);
                interruptFiredRef.current = true;
                interruptCountRef.current = 0;
                sendStopSpeaking();
              }
            } else {
              // Reset counter if voice drops below threshold
              interruptCountRef.current = 0;
            }
          }

          rafRef.current = requestAnimationFrame(tick);
        };
        rafRef.current = requestAnimationFrame(tick);
      } catch (err) {
        console.error("[MIC] getUserMedia failed:", err);
        setLevel(0);
      }
    })();

    return () => {
      cancelled = true;
      cancelAnimationFrame(rafRef.current);
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
      ctxRef.current?.close().catch(() => {});
      ctxRef.current = null;
      setLevel(0);
    };
  }, [muted, setLevel]);

  return { muted, setMuted };
}
