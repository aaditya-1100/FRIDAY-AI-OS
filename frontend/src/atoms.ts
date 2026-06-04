import { atom } from "jotai";
import { atomWithStorage } from "jotai/utils";

export type AiState =
  | "IDLE"
  | "LISTENING"
  | "THINKING"
  | "EXECUTING"
  | "SPEAKING"
  | "ERROR";

export interface ReminderItem {
  id: string;
  type: "timer" | "alarm" | "reminder" | "recurring";
  text: string;
  target_time: string;
  recurrence: string | null;
  duration_seconds: number | null;
  remaining_seconds: number;
}

export interface ReminderToast {
  id: string;
  item_type: string;
  title: string;
  body: string;
}

export const backendStateAtom  = atom<AiState>("IDLE");
export const isTtsPlayingAtom  = atom<boolean>(false);

export const aiStateAtom = atom<AiState>((get) => {
  const backendState = get(backendStateAtom);
  const isTtsPlaying = get(isTtsPlayingAtom);
  if (backendState === "SPEAKING" && !isTtsPlaying) {
    return "THINKING"; // Keep thinking spinner active during TTS synthesis lag
  }
  if (isTtsPlaying && (backendState === "LISTENING" || backendState === "IDLE")) {
    return "SPEAKING";
  }
  return backendState;
});

export const micMutedAtom     = atomWithStorage<boolean>("micMuted", false);
export const micLevelAtom     = atom(0);
export const ttsLevelAtom     = atom(0);
export const wsConnectedAtom  = atom(false);

export const commandErrorAtom = atom<string | null>(null);

// Map / Navigation
export const mapModeAtom      = atom<boolean>(false);
export const mapLocationAtom  = atom<string>("");
export const mapLatAtom       = atom<number | null>(null);
export const mapLonAtom       = atom<number | null>(null);

// Transcript / speak text
export const transcriptAtom   = atom<string>("");
export const speakTextAtom    = atom<string>("");

// ── Temporal / Reminders ─────────────────────────────────────────────────────
/** Live list of active reminders/timers/alarms streamed from backend */
export const remindersAtom     = atom<ReminderItem[]>([]);
/** Fires when a reminder/timer/alarm triggers — cleared after 6s */
export const reminderToastAtom = atom<ReminderToast | null>(null);
