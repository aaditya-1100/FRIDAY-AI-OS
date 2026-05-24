import { atom } from "jotai";
import { atomWithStorage } from "jotai/utils";

export type AiState =
  | "IDLE"
  | "LISTENING"
  | "THINKING"
  | "EXECUTING"
  | "SPEAKING"
  | "ERROR";

export const aiStateAtom      = atom<AiState>("IDLE");
export const micMutedAtom     = atomWithStorage<boolean>("micMuted", false);  // mic active by default; user clicks to mute
export const micLevelAtom     = atom(0);     // 0-1 mic input amplitude
export const ttsLevelAtom     = atom(0);     // 0-1 TTS playback amplitude (for orb)
export const wsConnectedAtom  = atom(false);

/** Last server `result` error (cleared on new command send). */
export const commandErrorAtom = atom<string | null>(null);

// Cinematic layers & Integrations atoms
export const mapModeAtom      = atom<boolean>(false);
export const mapLocationAtom  = atom<string>("");
export const transcriptAtom   = atom<string>("");
export const speakTextAtom    = atom<string>("");

