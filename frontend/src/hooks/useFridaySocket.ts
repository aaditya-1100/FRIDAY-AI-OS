import { useAtomValue, useSetAtom } from "jotai";
import { useEffect, useRef } from "react";
import {
  type AiState,
  backendStateAtom,
  isTtsPlayingAtom,
  commandErrorAtom,
  micMutedAtom,
  micLevelAtom,
  ttsLevelAtom,
  wsConnectedAtom,
  mapModeAtom,
  mapLocationAtom,
  mapLatAtom,
  mapLonAtom,
  transcriptAtom,
  speakTextAtom,
  remindersAtom,
  reminderToastAtom,
  type ReminderItem,
  type ReminderToast,
} from "../atoms";

// ─── Shared AudioContext ──────────────────────────────────────────────────────
let _audioCtx: AudioContext | null = null;

function getAudioContext(): AudioContext {
  if (!_audioCtx || _audioCtx.state === "closed") {
    _audioCtx = new AudioContext();
  }
  return _audioCtx;
}

export function unlockAudio() {
  const ctx = getAudioContext();
  console.log(`[TRACE] [AUDIO] unlockAudio() called. Current state: ${ctx.state}`);
  if (ctx.state === "suspended") {
    ctx.resume()
      .then(() => console.log(`[TRACE] [AUDIO] unlockAudio() success! State: ${ctx.state}`))
      .catch((e) => console.error("[TRACE] [AUDIO] unlockAudio() failed:", e));
  }
}

// Auto-unlock AudioContext on first user interaction to satisfy Chromium policies
if (typeof window !== "undefined") {
  const unlock = () => {
    const ctx = getAudioContext();
    console.log(`[TRACE] [AUDIO] User gesture detected. Auto-unlocking AudioContext (state: ${ctx.state})...`);
    if (ctx.state === "suspended") {
      ctx.resume().then(() => {
        console.log("[TRACE] [AUDIO] AudioContext successfully auto-unlocked. State:", ctx.state);
        window.removeEventListener("click", unlock);
        window.removeEventListener("keydown", unlock);
        window.removeEventListener("touchstart", unlock);
      }).catch((e) => {
        console.error("[TRACE] [AUDIO_ERROR] Failed to auto-unlock AudioContext:", e);
      });
    } else {
      window.removeEventListener("click", unlock);
      window.removeEventListener("keydown", unlock);
      window.removeEventListener("touchstart", unlock);
    }
  };
  window.addEventListener("click", unlock);
  window.addEventListener("keydown", unlock);
  window.addEventListener("touchstart", unlock);
}

// ─── TTS level callback (set by hook, called by audio engine) ─────────────────
let _setTtsLevel: ((v: number) => void) | null = null;

export function _registerTtsLevelSetter(fn: (v: number) => void) {
  _setTtsLevel = fn;
}

let _setIsTtsPlaying: ((v: boolean) => void) | null = null;

export function _registerIsTtsPlayingSetter(fn: (v: boolean) => void) {
  _setIsTtsPlaying = fn;
}

// ─── Audio queue + playback ───────────────────────────────────────────────────
let _audioPlaying  = false;
let _currentSource: AudioBufferSourceNode | null = null;
let _levelRaf = 0;
interface AudioQueueItem {
  b64: string;
  responseId: string;
}
const _audioQueue: AudioQueueItem[] = [];

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
    _setTtsLevel?.(Math.min(1, rms * 6)); // ×6 amplification for strong orb reaction
    _levelRaf = requestAnimationFrame(tick);
  };
  _levelRaf = requestAnimationFrame(tick);
}

async function _playNext() {
  if (_audioPlaying || _audioQueue.length === 0) return;
  
  _audioPlaying = true;
  _setIsTtsPlaying?.(true);
  const item = _audioQueue.shift()!;
  const b64 = item.b64;
  const rid = item.responseId;
  let playTimeout: ReturnType<typeof setTimeout> | null = null;
  
  console.log(`[TRACE] [AUDIO_PLAYBACK] [${rid}] STARTING PLAYBACK | queue_remaining=${_audioQueue.length} | b64_length=${b64.length}`);
  console.log(`[E2E_TRACE] [STAGE 12: Frontend Playback Started] Decoding base64 audio payload for response ID: ${rid}`);
  
  try {
    const ctx = getAudioContext();
    console.log(`[TRACE] [AUDIO_PLAYBACK] [${rid}] AudioContext state=${ctx.state}`);
    if (ctx.state === "suspended") {
      console.log(`[TRACE] [AUDIO_PLAYBACK] [${rid}] Resuming suspended AudioContext`);
      await ctx.resume();
      console.log(`[TRACE] [AUDIO_PLAYBACK] [${rid}] AudioContext resumed successfully`);
    }
    
    console.log(`[TRACE] [AUDIO_PLAYBACK] [${rid}] Decoding base64 audio data | b64_length=${b64.length}`);
    const binary = atob(b64);
    const bytes  = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    console.log(`[TRACE] [AUDIO_PLAYBACK] [${rid}] Base64 decode complete | bytes_length=${bytes.length}`);
    
    try {
      console.log(`[TRACE] [AUDIO_PLAYBACK] [${rid}] Decoding AudioData | bytes=${bytes.length}`);
      const audioBuf = await ctx.decodeAudioData(bytes.buffer);
      console.log(`[TRACE] [AUDIO_PLAYBACK] [${rid}] AudioData decode success | duration=${audioBuf.duration}s | channels=${audioBuf.numberOfChannels} | sampleRate=${audioBuf.sampleRate}`);
      
      const src     = ctx.createBufferSource();
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      
      src.buffer = audioBuf;
      src.connect(analyser);
      
      // ── Anti-crackling audio graph ───────────────────────────────────────
      // DynamicsCompressorNode prevents inter-app audio clipping when Chrome
      // (YouTube) and FRIDAY's TTS both route through the same audio device.
      const compressor = ctx.createDynamicsCompressor();
      compressor.threshold.setValueAtTime(-18, ctx.currentTime);
      compressor.knee.setValueAtTime(8, ctx.currentTime);
      compressor.ratio.setValueAtTime(4, ctx.currentTime);
      compressor.attack.setValueAtTime(0.003, ctx.currentTime);
      compressor.release.setValueAtTime(0.18, ctx.currentTime);
      
      const gainNode = ctx.createGain();
      gainNode.gain.setValueAtTime(0.92, ctx.currentTime); // Slightly under unity to prevent clipping
      
      analyser.connect(compressor);
      compressor.connect(gainNode);
      gainNode.connect(ctx.destination);
      console.log(`[TRACE] [AUDIO_PLAYBACK] [${rid}] Audio graph: source -> analyser -> compressor -> gain -> destination`);
      
      _currentSource = src;
      _startLevelRaf(analyser);
      
      let ended = false;
      
      const cleanUpPlayback = () => {
        if (ended) return;
        ended = true;
        console.log(`[TRACE] [AUDIO_PLAYBACK] [${rid}] CLEANUP STARTED`);
        
        if (playTimeout) { clearTimeout(playTimeout); playTimeout = null; }
        
        try {
          if (_currentSource) {
            _currentSource.disconnect();
            console.log(`[TRACE] [AUDIO_PLAYBACK] [${rid}] Source node disconnected`);
          }
        } catch (e) {
          console.warn(`[TRACE] [AUDIO_PLAYBACK] [${rid}] disconnect error:`, e);
        }
        
        _audioPlaying  = false;
        _currentSource = null;
        _stopLevelRaf();
        _setIsTtsPlaying?.(false);
        console.log(`[TRACE] [AUDIO_PLAYBACK] [${rid}] State reset: _audioPlaying=false, _currentSource=null`);
        
        const ws = getWsSocket();
        if (ws && ws.readyState === WebSocket.OPEN) {
          console.log(`[TRACE] [AUDIO_PLAYBACK] [${rid}] Sending playback_completed to backend`);
          console.log(`[E2E_TRACE] [STAGE 12: Frontend Playback Started] PASS. Playback finished. Sending playback_completed back to backend. Response ID: ${rid}`);
          ws.send(JSON.stringify({ type: "playback_completed", responseId: rid }));
        } else {
          console.warn(`[TRACE] [AUDIO_PLAYBACK] [${rid}] WebSocket not open, cannot send playback_completed | ws_state=${ws?.readyState}`);
          console.log(`[E2E_TRACE] [STAGE 12: Frontend Playback Started] WARNING. Playback finished but WebSocket is closed. Response ID: ${rid}`);
        }
        
        console.log(`[TRACE] [AUDIO_PLAYBACK] [${rid}] CLEANUP COMPLETE | queue_remaining=${_audioQueue.length}`);
        _playNext();
      };
      
      src.onended = () => {
        console.log(`[TRACE] [AUDIO_PLAYBACK] [${rid}] onended event fired`);
        cleanUpPlayback();
      };
      
      // Schedule playback 40ms in the future to give the audio graph time to
      // pre-buffer, preventing the initial crackle/pop artifact on start.
      const startOffset = 0.04;
      console.log(`[TRACE] [AUDIO_PLAYBACK] [${rid}] Starting source node playback (scheduled +${startOffset}s)`);
      src.start(ctx.currentTime + startOffset);
      console.log(`[TRACE] [AUDIO_PLAYBACK] [${rid}] Source node start() called successfully`);
      console.log(`[E2E_TRACE] [STAGE 12: Frontend Playback Started] PASS. Web Audio API source node started playing response ID: ${rid}`);
      
      // Safety Timeout: if it doesn't end in duration + 5 seconds, force recovery
      const safetyMs = (audioBuf.duration * 1000) + 5000;
      console.log(`[TRACE] [AUDIO_PLAYBACK] [${rid}] Safety timeout set | duration=${audioBuf.duration}s | timeout=${safetyMs}ms`);
      playTimeout = setTimeout(() => {
        console.warn(`[TRACE] [AUDIO_PLAYBACK] [${rid}] SAFETY TIMEOUT TRIGGERED | forcing cleanup`);
        console.log(`[E2E_TRACE] [STAGE 12: Frontend Playback Started] WARNING. Safety timeout triggered (playback hung/delayed). Response ID: ${rid}`);
        cleanUpPlayback();
      }, safetyMs);
      
    } catch (decodeError) {
      console.error(`[TRACE] [AUDIO_PLAYBACK] [${rid}] DECODE ERROR:`, decodeError);
      console.log(`[E2E_TRACE] [STAGE 12: Frontend Playback Started] FAIL. Web Audio API decodeAudioData failed for response ID: ${rid}`);
      throw decodeError;
    }
  } catch (e) {
    console.error(`[TRACE] [AUDIO_PLAYBACK] [${rid}] PLAYBACK ERROR:`, e);
    console.log(`[E2E_TRACE] [STAGE 12: Frontend Playback Started] FAIL. Playback error: ${e} for response ID: ${rid}`);
    if (playTimeout) { clearTimeout(playTimeout); playTimeout = null; }
    _audioPlaying  = false;
    _currentSource = null;
    _stopLevelRaf();
    _setIsTtsPlaying?.(false);
    
    // Safety check: notify backend on error so it unblocks
    const ws = getWsSocket();
    if (ws && ws.readyState === WebSocket.OPEN) {
      console.log(`[TRACE] [AUDIO_PLAYBACK] [${rid}] Sending playback_completed on error to unblock backend`);
      ws.send(JSON.stringify({ type: "playback_completed", responseId: rid }));
    }
  }
}

export function enqueueAudio(base64: string, responseId?: string) {
  const rid = responseId || "unknown";
  console.log(`[TRACE] [AUDIO_PLAYBACK] [${rid}] ENQUEUE AUDIO | queue_size_before=${_audioQueue.length} | b64_length=${base64.length}`);
  console.log(`[E2E_TRACE] [STAGE 12: Frontend Playback Started] Audio base64 received from WebSocket. Enqueueing response ID: ${rid}`);
  _audioQueue.push({ b64: base64, responseId: rid });
  _playNext();
}

export function stopAudio() {
  console.log(`[TRACE] [AUDIO] stopAudio() called. Clearing queue.`);
  _audioQueue.length = 0;
  try {
    if (_currentSource) {
      console.log("[TRACE] [AUDIO] Stopping active source node");
      _currentSource.stop();
    }
  } catch (e) {
    console.warn("[TRACE] [AUDIO] Error stopping source node:", e);
  }
  _currentSource = null;
  _audioPlaying  = false;
  _stopLevelRaf();
  _setIsTtsPlaying?.(false);
}

// Exposed ref so MicButton + useMicLevel can send WS messages without circular imports
let _wsRef: { current: WebSocket | null } | null = null;
export function _registerWsRef(ref: { current: WebSocket | null }) { _wsRef = ref; }

/** Returns the live WebSocket (or null). Used by useMicLevel to send mic_on/off. */
export function getWsSocket(): WebSocket | null {
  return _wsRef?.current ?? null;
}

export function sendStopSpeaking() {
  console.log("[TRACE] [AUDIO] sendStopSpeaking() triggered");
  stopAudio();
  const ws = _wsRef?.current;
  if (ws?.readyState === WebSocket.OPEN) {
    console.log("[TRACE] [AUDIO] Sending stop_speaking message to backend");
    ws.send(JSON.stringify({ type: "stop_speaking" }));
  } else {
    console.warn("[TRACE] [AUDIO] WebSocket not open, cannot send stop_speaking");
  }
}
// ─────────────────────────────────────────────────────────────────────────────

function wsUrl(): string {
  const env = import.meta.env.VITE_WS_URL;
  if (env) return env;
  // Always connect to local backend — works in both dev and packaged Electron app
  return "ws://127.0.0.1:8001/api/ws";
}

function formatResultError(data: { reason?: string; detail?: string }): string {
  const r = data.reason ?? "error";
  if (r === "no_intent")      return "No matching command";
  if (r === "execute_failed") return "Action failed";
  if (r === "pipeline_error") return data.detail ? `Error: ${data.detail}` : "Internal error";
  return r;
}

export function useFridaySocket() {
  const setBackendState = useSetAtom(backendStateAtom);
  const setIsTtsPlaying = useSetAtom(isTtsPlayingAtom);
  const setConnected    = useSetAtom(wsConnectedAtom);
  const setCommandError = useSetAtom(commandErrorAtom);
  const setTtsLevel     = useSetAtom(ttsLevelAtom);
  const setMicLevel     = useSetAtom(micLevelAtom);
  const setTranscript   = useSetAtom(transcriptAtom);
  const setSpeakText    = useSetAtom(speakTextAtom);
  const setMapMode      = useSetAtom(mapModeAtom);
  const setMapLocation  = useSetAtom(mapLocationAtom);
  const setMapLat       = useSetAtom(mapLatAtom);
  const setMapLon       = useSetAtom(mapLonAtom);
  const setReminders    = useSetAtom(remindersAtom);
  const setReminderToast = useSetAtom(reminderToastAtom);
  const micMuted        = useAtomValue(micMutedAtom);
  const micMutedRef     = useRef(micMuted);
  const wsRef           = useRef<WebSocket | null>(null);
  const reconnectAttempt = useRef(0);
  const toastTimerRef   = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Keep a ref so onopen closure always reads the latest mute state
  micMutedRef.current = micMuted;

  // Register the tts level setter so the audio engine can update Jotai
  useEffect(() => {
    console.log("[TRACE] [SOCKET_HOOK] Registering TTS level setter");
    _registerTtsLevelSetter(setTtsLevel);
    return () => {
      console.log("[TRACE] [SOCKET_HOOK] Unregistering TTS level setter");
      _registerTtsLevelSetter(() => {});
    };
  }, [setTtsLevel]);

  // Register the isTtsPlaying setter so the audio engine can update Jotai
  useEffect(() => {
    console.log("[TRACE] [SOCKET_HOOK] Registering isTtsPlaying setter");
    _registerIsTtsPlayingSetter(setIsTtsPlaying);
    return () => {
      console.log("[TRACE] [SOCKET_HOOK] Unregistering isTtsPlaying setter");
      _registerIsTtsPlayingSetter(() => {});
    };
  }, [setIsTtsPlaying]);

  // Register wsRef so sendStopSpeaking() can reach the socket
  useEffect(() => {
    console.log("[TRACE] [SOCKET_HOOK] Registering global wsRef reference");
    _registerWsRef(wsRef);
  }, []);

  useEffect(() => {
    let cancelled = false;
    let ws: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | undefined;
    const maxDelayMs = 12_000;

    const attachHandlers = (socket: WebSocket) => {
      socket.onopen = () => {
        console.log("[TRACE] [WS] Connected to", wsUrl());
        setConnected(true);
        reconnectAttempt.current = 0;
        
        // ── CRITICAL: Sync mic state to backend on every (re)connect. ──────────
        const syncMsg = micMutedRef.current ? "mic_off" : "mic_on";
        console.log(`[TRACE] [WS] Syncing mic state on connect: "${syncMsg}"`);
        socket.send(JSON.stringify({ type: syncMsg }));
      };
      
      socket.onclose = (event) => {
        console.log(`[TRACE] [WS] Connection closed. code=${event.code}, reason="${event.reason}"`);
        setConnected(false);
        wsRef.current = null;
        if (cancelled) {
          console.log("[TRACE] [WS] Component unmounted, skipping reconnection");
          return;
        }
        const n     = reconnectAttempt.current++;
        const delay = Math.min(maxDelayMs, 400 * 2 ** Math.min(n, 5));
        console.log(`[TRACE] [WS] Scheduling reconnect attempt #${n + 1} in ${delay}ms...`);
        reconnectTimer = window.setTimeout(connect, delay) as any;
      };
      
      socket.onerror = (error) => {
        console.error("[TRACE] [WS_ERROR] WebSocket encountered error:", error);
        socket.close();
      };
      
      socket.onmessage = (ev) => {
        console.log("[TRACE] [WS_MSG_RAW] Raw message received:", ev.data);
        try {
          const data = JSON.parse(ev.data as string);
          console.log(`[TRACE] [WS_MSG] Parsed message type: "${data.type}"`, data);
          
          if (data.type === "state" && typeof data.state === "string") {
            const newState = data.state as AiState;
            console.log(`[TRACE] [WS_MSG] State change: "${newState}"`);
            setBackendState(newState);
            if (newState === "LISTENING") {
              setTranscript("");
              setSpeakText("");
            } else if (newState === "THINKING") {
              setSpeakText("");
            }
            if (newState === "LISTENING" || newState === "IDLE") {
              stopAudio();
            }
          }
          if (data.type === "transcript" && typeof data.text === "string") {
            console.log(`[TRACE] [WS_MSG] Transcript text: "${data.text}"`);
            setTranscript(data.text);
          }
          if (data.type === "speak" && typeof data.text === "string") {
            console.log(`[TRACE] [WS_MSG] Speak text: "${data.text}"`);
            setSpeakText(data.text);
          }
          if (data.type === "show_map") {
            console.log(`[TRACE] [WS_MSG] Sat map display requested. Location: "${data.location}" lat=${data.lat} lon=${data.lon}`);
            setMapMode(true);
            if (typeof data.location === "string") {
              setMapLocation(data.location);
            }
            if (typeof data.lat === "number") setMapLat(data.lat);
            if (typeof data.lon === "number") setMapLon(data.lon);
          }
          if (data.type === "hide_map") {
            console.log("[TRACE] [WS_MSG] Sat map hide requested.");
            setMapMode(false);
            setMapLocation("");
            setMapLat(null);
            setMapLon(null);
          }
          if (data.type === "cancel_audio") {
            console.log("[TRACE] [WS_MSG] cancel_audio event received");
            stopAudio();
          }
          if (data.type === "audio" && typeof data.audioBase64 === "string") {
            const rid = data.responseId || "unknown";
            console.log(`[TRACE] [WS_MSG] [${rid}] Audio received | b64_length=${data.audioBase64.length}`);
            enqueueAudio(data.audioBase64, rid);
          }
          if (data.type === "result" && data.ok === false) {
            const errText = formatResultError(data);
            console.log(`[TRACE] [WS_MSG] Result error: "${errText}"`);
            setCommandError(errText);
          }
          if (data.type === "result" && data.ok === true) {
            console.log("[TRACE] [WS_MSG] Result success.");
            setCommandError(null);
          }
          if (data.type === "hint" && typeof data.text === "string") {
            console.log(`[TRACE] [WS_MSG] UI hint: "${data.text}"`);
            setCommandError(data.text);
            setTimeout(() => setCommandError(null), 3000);
          }
          // Backend mic-level stream — drives the orb during LISTENING state.
          // The backend owns PyAudio during LISTENING so the browser can't open
          // getUserMedia; instead the backend streams amplitude via WebSocket.
          if (data.type === "mic_level" && typeof data.level === "number") {
            setMicLevel(Math.min(1, Math.max(0, data.level)));
          }
          // ── Temporal: reminder list update ──────────────────────────────
          if (data.type === "reminder_list" && Array.isArray(data.items)) {
            console.log(`[TRACE] [WS_MSG] reminder_list received: ${data.items.length} items`);
            setReminders(data.items as ReminderItem[]);
          }
          // ── Temporal: reminder/timer/alarm fired toast ───────────────────
          if (data.type === "reminder_fired") {
            console.log(`[TRACE] [WS_MSG] reminder_fired: ${data.title} — ${data.body}`);
            const toast: ReminderToast = {
              id: data.id || "",
              item_type: data.item_type || "reminder",
              title: data.title || "Reminder",
              body: data.body || "",
            };
            setReminderToast(toast);
            // Auto-dismiss toast after 6 seconds
            if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
            toastTimerRef.current = setTimeout(() => setReminderToast(null), 6000);
          }
        } catch (err) {
          console.error("[TRACE] [WS_MSG_PARSE_ERROR] Failed to parse raw event data:", err);
        }
      };
    };

    const connect = () => {
      if (cancelled) return;
      console.log("[TRACE] [WS] Opening new WebSocket connection to:", wsUrl());
      ws = new WebSocket(wsUrl());
      wsRef.current = ws;
      attachHandlers(ws);
    };

    connect();

    // Keep-alive ping every 20s
    console.log("[TRACE] [SOCKET_HOOK] Initializing 20s keep-alive ping interval");
    const pingTimer = window.setInterval(() => {
      const s = wsRef.current;
      if (s?.readyState === WebSocket.OPEN) {
        console.log("[TRACE] [WS] Emitting heartbeat ping");
        s.send(JSON.stringify({ type: "ping" }));
      }
    }, 20_000);

    // ── beforeunload: tell backend to stop everything before the tab dies ────
    const onUnload = () => {
      console.log("[TRACE] [WS] beforeunload event. Synced cleanup mic_off and stop_speaking.");
      const s = wsRef.current;
      if (s?.readyState === WebSocket.OPEN) {
        s.send(JSON.stringify({ type: "mic_off" }));
        s.send(JSON.stringify({ type: "stop_speaking" }));
      }
      stopAudio();
    };
    window.addEventListener("beforeunload", onUnload);

    return () => {
      console.log("[TRACE] [SOCKET_HOOK] Cleanups running for socket hook");
      cancelled = true;
      window.removeEventListener("beforeunload", onUnload);
      window.clearInterval(pingTimer);
      window.clearTimeout(reconnectTimer);
      stopAudio();
      if (ws) {
        console.log("[TRACE] [WS] Closing WebSocket connection...");
        ws.close();
      }
      wsRef.current = null;
      setConnected(false);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const sendCommand = (text: string) => {
    const socket = wsRef.current;
    console.log(`[TRACE] [SOCKET_HOOK] sendCommand("${text}") called. Socket state: ${socket?.readyState}`);
    if (socket?.readyState === WebSocket.OPEN) {
      setTranscript(text);
      setSpeakText("");
      console.log("[TRACE] [SOCKET_HOOK] Sending command over WebSocket");
      socket.send(JSON.stringify({ type: "command", text }));
    } else {
      console.error("[TRACE] [SOCKET_HOOK_ERROR] Cannot send command, WebSocket is not open");
    }
  };

  return { sendCommand, wsRef };
}
