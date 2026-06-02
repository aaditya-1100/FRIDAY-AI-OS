import { useAtom, useAtomValue } from "jotai";
import { useEffect, useRef, useCallback } from "react";
import { aiStateAtom, micLevelAtom, micMutedAtom } from "../atoms";
import { getWsSocket, sendStopSpeaking } from "./useFridaySocket";

function sendMicMsg(type: "mic_on" | "mic_off") {
  const ws = getWsSocket();
  console.log(`[TRACE] [MIC_MSG] sendMicMsg("${type}") called. WebSocket open state: ${ws?.readyState === WebSocket.OPEN}`);
  if (ws?.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type }));
    console.log(`[TRACE] [MIC_MSG] Sent "${type}" to backend successfully`);
  } else {
    console.warn(`[TRACE] [MIC_MSG_ERROR] WebSocket is NOT open (state: ${ws?.readyState}). Cannot send "${type}".`);
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
    console.log(`[TRACE] [MIC_HOOK] setMuted(${value}) called`);
    setMutedRaw(value);
    sendMicMsg(value ? "mic_off" : "mic_on");
  }, [setMutedRaw]);

  useEffect(() => {
    // CRITICAL RECOVERY: Disable unstable browser mic capture during SPEAKING state.
    // Capturing the browser mic during speaking causes extreme acoustic feedback loops from the speakers
    // and initial hardware click pops, which trigger false interruptions within 130ms and clear
    // the audio queue before any sound is heard. Manual click-to-interrupt handles speech cancellation safely.
    const shouldCapture = false;

    console.log(`[TRACE] [MIC_EFFECT] Effect triggered. muted=${muted} | aiState=${aiState} | shouldCapture=${shouldCapture}`);
    if (!shouldCapture) {
      console.log("[TRACE] [MIC_EFFECT] Microphone capture not required or muted. Tearing down local stream...");
      cancelAnimationFrame(rafRef.current);
      streamRef.current?.getTracks().forEach((t) => {
        console.log(`[TRACE] [MIC_EFFECT] Stopping track: ${t.label}`);
        t.stop();
      });
      streamRef.current = null;
      ctxRef.current?.close().catch(() => {});
      ctxRef.current = null;
      setLevel(0);
      return;
    }

    // ── Active: start mic stream ──────────────────────────────────────────
    let cancelled = false;
    const data = new Uint8Array(256);

    (async () => {
      try {
        console.log("[TRACE] [MIC_EFFECT] Unmuted is true. Requesting microphone access (navigator.mediaDevices.getUserMedia)...");
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        if (!stream) {
          console.warn("[TRACE] [MIC_EFFECT_ERROR] getUserMedia returned null/empty stream");
          setLevel(0);
          return;
        }
        if (cancelled) {
          console.log("[TRACE] [MIC_EFFECT] getUserMedia completed but effect was cancelled. Tearing down track immediately.");
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;
        console.log(`[TRACE] [MIC_EFFECT] getUserMedia success! Tracks count: ${stream.getTracks().length}`);

        const ctx = new AudioContext();
        ctxRef.current = ctx;
        console.log(`[TRACE] [MIC_EFFECT] Local mic AudioContext created. State: ${ctx.state}`);

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
                console.log(`[TRACE] [MIC_INTERRUPT] Interruption confirmed: ${interruptCountRef.current} frames above threshold (level=${currentLevel.toFixed(2)})`);
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
        console.error("[TRACE] [MIC_EFFECT_ERROR] getUserMedia failed:", err);
        setLevel(0);
      }
    })();

    return () => {
      console.log("[TRACE] [MIC_EFFECT] Cleanup running. Tearing down stream...");
      cancelled = true;
      cancelAnimationFrame(rafRef.current);
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
      ctxRef.current?.close().catch(() => {});
      ctxRef.current = null;
      setLevel(0);
    };
  }, [muted, setLevel, aiState]);

  return { muted, setMuted };
}
