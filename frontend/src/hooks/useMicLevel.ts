import { useAtom } from "jotai";
import { useEffect, useRef, useCallback } from "react";
import { micLevelAtom, micMutedAtom } from "../atoms";
import { getWsSocket } from "./useFridaySocket";

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
  const ctxRef               = useRef<AudioContext | null>(null);
  const streamRef            = useRef<MediaStream | null>(null);
  const rafRef               = useRef<number>(0);
  const mutedRef             = useRef(muted);

  // Keep ref in sync so event handlers always see latest value
  mutedRef.current = muted;

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
          setLevel(Math.min(1, avg));
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
