import { atom } from "jotai";

export type AiState =
  | "IDLE"
  | "LISTENING"
  | "THINKING"
  | "EXECUTING"
  | "SPEAKING"
  | "ERROR";

export const aiStateAtom      = atom<AiState>("IDLE");
export const micMutedAtom     = atom(false);  // mic active by default; user clicks to mute
export const micLevelAtom     = atom(0);     // 0-1 mic input amplitude
export const ttsLevelAtom     = atom(0);     // 0-1 TTS playback amplitude (for orb)
export const wsConnectedAtom  = atom(false);

/** Last server `result` error (cleared on new command send). */
export const commandErrorAtom = atom<string | null>(null);
