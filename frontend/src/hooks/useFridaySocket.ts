import { useSetAtom } from "jotai";
import { useEffect, useRef } from "react";
import { type AiState, aiStateAtom, commandErrorAtom, ttsLevelAtom, wsConnectedAtom } from "../atoms";

// ─── Shared AudioContext ──────────────────────────────────────────────────────
let _audioCtx: AudioContext | null = null;

function getAudioContext(): AudioContext {
  if (!_audioCtx || _audioCtx.state === "closed") {
    _audioCtx = new AudioContext({ sampleRate: 22050 });
  }
  return _audioCtx;
}

export function unlockAudio() {
  const ctx = getAudioContext();
  if (ctx.state === "suspended") ctx.resume().catch(() => {});
}

// ─── TTS level callback (set by hook, called by audio engine) ─────────────────
let _setTtsLevel: ((v: number) => void) | null = null;

export function _registerTtsLevelSetter(fn: (v: number) => void) {
  _setTtsLevel = fn;
}

// ─── Audio queue + playback ───────────────────────────────────────────────────
let _audioPlaying  = false;
let _currentSource: AudioBufferSourceNode | null = null;
let _levelRaf = 0;
const _audioQueue: string[] = [];

function _stopLevelRaf() {
  if (_levelRaf) { cancelAnimationFrame(_levelRaf); _levelRaf = 0; }
  _setTtsLevel?.(0);
}

function _startLevelRaf(analyser: AnalyserNode) {
  const data = new Uint8Array(analyser.fftSize);
  const tick = () => {
    analyser.getByteTimeDomainData(data);
    let sum = 0;
    for (let i = 0; i < data.length; i++) {
      const s = (data[i] - 128) / 128;
      sum += s * s;
    }
    const rms = Math.sqrt(sum / data.length);
    _setTtsLevel?.(Math.min(1, rms * 4)); // amplify RMS for orb visibility
    _levelRaf = requestAnimationFrame(tick);
  };
  _levelRaf = requestAnimationFrame(tick);
}

async function _playNext() {
  if (_audioPlaying || _audioQueue.length === 0) return;
  _audioPlaying = true;
  const b64 = _audioQueue.shift()!;
  try {
    const ctx = getAudioContext();
    if (ctx.state === "suspended") await ctx.resume();

    const binary = atob(b64);
    const bytes  = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    const audioBuf = await ctx.decodeAudioData(bytes.buffer);

    const src     = ctx.createBufferSource();
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 256;

    src.buffer = audioBuf;
    src.connect(analyser);
    analyser.connect(ctx.destination);

    _currentSource = src;
    _startLevelRaf(analyser);

    src.onended = () => {
      _audioPlaying  = false;
      _currentSource = null;
      _stopLevelRaf();
      _playNext();
    };
    src.start(0);
  } catch (e) {
    console.error("[Audio] Playback error:", e);
    _audioPlaying  = false;
    _currentSource = null;
    _stopLevelRaf();
    _playNext();
  }
}

export function enqueueAudio(base64: string) {
  _audioQueue.push(base64);
  _playNext();
}

export function stopAudio() {
  _audioQueue.length = 0;
  try { _currentSource?.stop(); } catch (_) {}
  _currentSource = null;
  _audioPlaying  = false;
  _stopLevelRaf();
}

// Exposed ref so MicButton + useMicLevel can send WS messages without circular imports
let _wsRef: { current: WebSocket | null } | null = null;
export function _registerWsRef(ref: { current: WebSocket | null }) { _wsRef = ref; }

/** Returns the live WebSocket (or null). Used by useMicLevel to send mic_on/off. */
export function getWsSocket(): WebSocket | null {
  return _wsRef?.current ?? null;
}

export function sendStopSpeaking() {
  stopAudio();
  const ws = _wsRef?.current;
  if (ws?.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "stop_speaking" }));
  }
}
// ─────────────────────────────────────────────────────────────────────────────

function wsUrl(): string {
  const env = import.meta.env.VITE_WS_URL;
  if (env) return env;
  if (import.meta.env.DEV) return "ws://127.0.0.1:8001/api/ws";
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/api/ws`;
}

function formatResultError(data: { reason?: string; detail?: string }): string {
  const r = data.reason ?? "error";
  if (r === "no_intent")      return "No matching command";
  if (r === "execute_failed") return "Action failed";
  if (r === "pipeline_error") return data.detail ? `Error: ${data.detail}` : "Internal error";
  return r;
}

export function useFridaySocket() {
  const setState        = useSetAtom(aiStateAtom);
  const setConnected    = useSetAtom(wsConnectedAtom);
  const setCommandError = useSetAtom(commandErrorAtom);
  const setTtsLevel     = useSetAtom(ttsLevelAtom);
  const wsRef           = useRef<WebSocket | null>(null);
  const reconnectAttempt = useRef(0);

  // Register the tts level setter so the audio engine can update Jotai
  useEffect(() => {
    _registerTtsLevelSetter(setTtsLevel);
    return () => { _registerTtsLevelSetter(() => {}); };
  }, [setTtsLevel]);

  // Register wsRef so sendStopSpeaking() can reach the socket
  useEffect(() => {
    _registerWsRef(wsRef);
  }, []);

  useEffect(() => {
    let cancelled = false;
    let ws: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | undefined;
    const maxDelayMs = 12_000;

    const attachHandlers = (socket: WebSocket) => {
      socket.onopen = () => {
        console.log("[WS] Connected to", wsUrl());
        setConnected(true);
        reconnectAttempt.current = 0;
      };
      socket.onclose = (event) => {
        console.log("[WS] Closed", event.code, event.reason);
        setConnected(false);
        wsRef.current = null;
        if (cancelled) return;
        const n     = reconnectAttempt.current++;
        const delay = Math.min(maxDelayMs, 400 * 2 ** Math.min(n, 5));
        reconnectTimer = window.setTimeout(connect, delay) as any;
      };
      socket.onerror = () => { socket.close(); };
      socket.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data as string);
          if (data.type === "state" && typeof data.state === "string") {
            setState(data.state as AiState);
          }
          if (data.type === "audio" && typeof data.audioBase64 === "string") {
            enqueueAudio(data.audioBase64);
          }
          if (data.type === "result" && data.ok === false) {
            setCommandError(formatResultError(data));
          }
          if (data.type === "result" && data.ok === true) {
            setCommandError(null);
          }
        } catch (err) {
          console.log("[WS] Message parse error", err);
        }
      };
    };

    const connect = () => {
      if (cancelled) return;
      ws = new WebSocket(wsUrl());
      wsRef.current = ws;
      attachHandlers(ws);
    };

    connect();

    // Keep-alive ping every 20s (reduced from 25s for better connection health)
    const pingTimer = window.setInterval(() => {
      const s = wsRef.current;
      if (s?.readyState === WebSocket.OPEN) {
        s.send(JSON.stringify({ type: "ping" }));
      }
    }, 20_000);

    // ── beforeunload: tell backend to stop everything before the tab dies ────
    const onUnload = () => {
      const s = wsRef.current;
      if (s?.readyState === WebSocket.OPEN) {
        s.send(JSON.stringify({ type: "mic_off" }));
        s.send(JSON.stringify({ type: "stop_speaking" }));
        // Note: 'shutdown' would kill the server process — only send if desired
      }
      stopAudio();
    };
    window.addEventListener("beforeunload", onUnload);

    return () => {
      cancelled = true;
      window.removeEventListener("beforeunload", onUnload);
      window.clearInterval(pingTimer);
      window.clearTimeout(reconnectTimer);
      // Tell backend mic is off before closing socket
      const s = wsRef.current;
      if (s?.readyState === WebSocket.OPEN) {
        s.send(JSON.stringify({ type: "mic_off" }));
        s.send(JSON.stringify({ type: "stop_speaking" }));
      }
      stopAudio();
      ws?.close();
      wsRef.current = null;
      setConnected(false);
    };
  }, [setCommandError, setConnected, setState]);

  const sendCommand = (text: string) => {
    const socket = wsRef.current;
    if (socket?.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: "command", text }));
    }
  };

  return { sendCommand, wsRef };
}
