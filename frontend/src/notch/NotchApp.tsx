import { useEffect, useRef, useState } from "react";
import { useAtom, useAtomValue } from "jotai";
import { aiStateAtom, wsConnectedAtom, proactiveTriggerAtom, activeAgentAtom } from "../atoms";
import { useFridaySocket, getWsSocket } from "../hooks/useFridaySocket";

export default function NotchApp() {
  const aiState = useAtomValue(aiStateAtom);
  const connected = useAtomValue(wsConnectedAtom);
  const [proactiveTrigger, setProactiveTrigger] = useAtom(proactiveTriggerAtom);
  const activeAgent = useAtomValue(activeAgentAtom);

  const [backendReady, setBackendReady] = useState(false);

  // Initialize socket hook so it connects to backend in this window's process
  useFridaySocket();

  const isIdleLike = aiState === "IDLE" || aiState === "WAITING" || aiState === "REFLECTING";

  // Query backend readiness on mount and subscribe to ready events
  useEffect(() => {
    const api = (window as any).electronAPI;
    if (api) {
      if (api.isBackendReady) {
        api.isBackendReady().then((ready: boolean) => {
          if (ready) {
            setBackendReady(true);
          }
        });
      }
      if (api.onBackendReady) {
        const cleanReady = api.onBackendReady(() => {
          console.log("[NOTCH] Received IPC backend-ready event");
          setBackendReady(true);
        });
        return () => {
          if (typeof cleanReady === "function") cleanReady();
        };
      }
    }
  }, []);

  // Auto-dismiss proactive notification after 7 seconds
  useEffect(() => {
    if (proactiveTrigger) {
      const timer = setTimeout(() => {
        setProactiveTrigger(null);
      }, 7000);
      return () => clearTimeout(timer);
    }
  }, [proactiveTrigger, setProactiveTrigger]);

  // Clear proactive trigger when FSM transitions to any active state
  const prevAiStateRef = useRef(aiState);
  useEffect(() => {
    if (prevAiStateRef.current !== aiState) {
      if (aiState !== "IDLE" && aiState !== "WAITING" && aiState !== "REFLECTING") {
        setProactiveTrigger(null);
      }
      prevAiStateRef.current = aiState;
    }
  }, [aiState, setProactiveTrigger]);

  // Expose listeners for hotkey triggers from main process with cleanup support
  useEffect(() => {
    const api = (window as any).electronAPI;
    if (api) {
      const handleMicOn = () => {
        console.log("[NOTCH] Received IPC hotkey-mic-on command");
        if (!backendReady) {
          console.warn("[NOTCH] Ignoring hotkey-mic-on because backend is not ready");
          return;
        }
        const ws = getWsSocket();
        if (ws && ws.readyState === WebSocket.OPEN) {
          console.log("[NOTCH] Sending mic_on WS command to backend with hold_to_talk mode");
          ws.send(JSON.stringify({ type: "mic_on", mode: "hold_to_talk" }));
        } else {
          console.warn("[NOTCH] WebSocket not open, cannot send mic_on");
        }
      };

      const handleMicOff = () => {
        console.log("[NOTCH] Received IPC hotkey-mic-off command");
        if (!backendReady) {
          console.warn("[NOTCH] Ignoring hotkey-mic-off because backend is not ready");
          return;
        }
        const ws = getWsSocket();
        if (ws && ws.readyState === WebSocket.OPEN) {
          console.log("[NOTCH] Sending mic_off WS command to backend");
          ws.send(JSON.stringify({ type: "mic_off" }));
        } else {
          console.warn("[NOTCH] WebSocket not open, cannot send mic_off");
        }
      };

      const cleanMicOn = api.onHotkeyMicOn(handleMicOn);
      const cleanMicOff = api.onHotkeyMicOff(handleMicOff);

      return () => {
        if (typeof cleanMicOn === "function") cleanMicOn();
        if (typeof cleanMicOff === "function") cleanMicOff();
      };
    }
  }, [connected, backendReady]);

  // Synchronize state changes with Electron main process for resizing/mouse-ignore toggling
  useEffect(() => {
    const api = (window as any).electronAPI;
    if (api) {
      const stateToSync = (proactiveTrigger && isIdleLike) ? "PROACTIVE" : aiState;
      api.setNotchState({ state: stateToSync, connected });
    }
  }, [aiState, connected, proactiveTrigger, isIdleLike]);

  const handleMouseEnter = () => {
    const api = (window as any).electronAPI;
    if (api) {
      api.setIgnoreMouseEvents(false);
    }
  };

  const handleMouseLeave = () => {
    const api = (window as any).electronAPI;
    if (api) {
      api.setIgnoreMouseEvents(true, true);
    }
  };

  const handleContextMenu = (e: React.MouseEvent) => {
    e.preventDefault();
    const api = (window as any).electronAPI;
    if (api && api.showNotchContextMenu) {
      api.showNotchContextMenu();
    }
  };

  const handleDoubleClick = () => {
    console.log("[NOTCH] Double click detected, sending force_idle WS command");
    const ws = getWsSocket();
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "force_idle" }));
    }
  };

  // ── Determine state key and label ─────────────────────────────────────────
  let stateKey = "idle";
  let label    = "FRIDAY";
  let showDot  = false;

  if (!backendReady) {
    stateKey = "disconnected";
    label    = "Starting...";
    showDot  = false;
  } else if (!connected) {
    stateKey = "disconnected";
    label    = "Offline";
    showDot  = false;
  } else if (proactiveTrigger && isIdleLike) {
    stateKey = "suggestion";
    label    = "Suggestion";
    showDot  = true;
  } else if (aiState === "LISTENING") {
    stateKey = "listening";
    label    = "Listening";
    showDot  = true;
  } else if (
    aiState === "PERCEIVING" ||
    aiState === "PLANNING"   ||
    aiState === "SYNTHESIZING" ||
    aiState === "THINKING"
  ) {
    stateKey = "thinking";
    label    = "Thinking";
    showDot  = true;
  } else if (aiState === "DELEGATING" || aiState === "WAITING" || aiState === "EXECUTING") {
    const agent = activeAgent ? activeAgent.toUpperCase() : "";
    if (agent.includes("WEB") || agent.includes("BROWSER") || agent.includes("SEARCH")) {
      stateKey = "searching"; label = "Searching";
    } else if (agent.includes("VISION")) {
      stateKey = "looking";   label = "Looking";
    } else if (agent.includes("MEMORY") || agent.includes("KNOWLEDGE")) {
      stateKey = "recalling"; label = "Recalling";
    } else {
      stateKey = "executing"; label = "Executing";
    }
    showDot = true;
  } else if (aiState === "SPEAKING" || aiState === "RESPONDING") {
    stateKey = "speaking";
    label    = "Speaking";
    showDot  = true;
  } else if (aiState === "ERROR") {
    stateKey = "error";
    label    = "Error";
    showDot  = false;
  }

  return (
    <div
      data-state={stateKey}
      className="notch-container"
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      onContextMenu={handleContextMenu}
      onDoubleClick={handleDoubleClick}
    >
      {showDot && <span className="notch-dot" />}
      <span className="notch-label">{label}</span>
    </div>
  );
}

