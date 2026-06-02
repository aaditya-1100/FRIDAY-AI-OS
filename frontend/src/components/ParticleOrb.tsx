/**
 * ParticleOrb — premium audio-synced voice companion orb.
 *
 * State visual contract:
 *   IDLE      — gentle slow breathing, low rotation, muted glow
 *   LISTENING — expands in real-time with mic amplitude (backend WS stream)
 *               snaps back cleanly when user stops speaking
 *   THINKING  — elevated, fast focused spin, tight pulse
 *   EXECUTING — larger + faster spin + urgency pulse
 *   SPEAKING  — audio-synced expansion driven by actual TTS amplitude
 *               secondary inner glow ring for "mouth equivalent"
 *   ERROR     — contracted, warning color, slow strobe
 *
 * Audio signal flow:
 *   LISTENING: backend emit_json_sync(mic_level) → WS → micLevelAtom → orb scale
 *   SPEAKING:  Web Audio analyser RMS → ttsLevelAtom → orb scale + inner ring
 */
import { useFrame } from "@react-three/fiber";
import { useAtomValue } from "jotai";
import { useLayoutEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { aiStateAtom, micLevelAtom, ttsLevelAtom, micMutedAtom, type AiState } from "../atoms";



const COUNT = 900;

function fibonacciSphere(count: number, radius: number) {
  const p   = new Float32Array(count * 3);
  const phi = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < count; i++) {
    const y  = 1 - (i / Math.max(1, count - 1)) * 2;
    const rr = Math.sqrt(Math.max(0, 1 - y * y));
    const t  = phi * i;
    p[i * 3]     = Math.cos(t) * rr * radius;
    p[i * 3 + 1] = y * radius;
    p[i * 3 + 2] = Math.sin(t) * rr * radius;
  }
  return p;
}

// ── Per-state color palette ────────────────────────────────────────────────────
const COLORS: Record<AiState, string> = {
  IDLE:      "#4f46e5",   // deep indigo
  LISTENING: "#06b6d4",   // cyber cyan
  THINKING:  "#a855f7",   // bright purple
  EXECUTING: "#ec4899",   // vibrant hot pink
  SPEAKING:  "#f59e0b",   // radiant gold/amber
  ERROR:     "#ef4444",   // warning crimson
};

// ── Per-state rotation speeds (radians/second) ─────────────────────────────────
const ROT_SPEED: Record<AiState, number> = {
  IDLE:      0.055,   // slow, meditative
  LISTENING: 0.095,   // slightly elevated — active attention
  THINKING:  0.35,    // fast focused spin — "working hard"
  EXECUTING: 0.50,    // fastest — urgent task execution
  SPEAKING:  0.13,    // smooth, steady — speech flow
  ERROR:     0.07,    // slow, contracted
};

// ── Per-state base scale ────────────────────────────────────────────────────────
const BASE_SCALE = 0.53;

// ── Damping speeds (lerp lambda per state) ──────────────────────────────────────
// Higher = faster snap. Lower = smoother, more organic transition.
const SCALE_DAMP: Record<AiState, number> = {
  IDLE:      2.5,    // slow breathing
  LISTENING: 10,     // organic growth — responsive but fluid, not jumpy
  THINKING:  4.0,    // smooth ramp
  EXECUTING: 4.5,    // smooth ramp
  SPEAKING:  10,     // organic sync with audio — matched fluidity
  ERROR:     3.0,    // slow contraction
};

// ── Per-state particle size ─────────────────────────────────────────────────────
const BASE_PARTICLE = 0.018;

export function ParticleOrb() {
  const group      = useRef<THREE.Group>(null);
  const points     = useRef<THREE.Points>(null);
  const base       = useMemo(() => fibonacciSphere(COUNT, 1), []);

  const aiState  = useAtomValue(aiStateAtom);
  const micLevel = useAtomValue(micLevelAtom);
  const ttsLevel = useAtomValue(ttsLevelAtom);
  const micMuted = useAtomValue(micMutedAtom);

  // Smoothed values — prevent jitter from raw WS data
  const mic    = useRef(0);
  const tts    = useRef(0);
  const scale  = useRef(BASE_SCALE);
  const color  = useRef(new THREE.Color(COLORS.IDLE));

  useLayoutEffect(() => {
    const geom = points.current?.geometry;
    if (!geom) return;
    geom.setAttribute("position", new THREE.BufferAttribute(new Float32Array(base), 3));
  }, [base]);

  useFrame((st, dt) => {
    const g    = group.current;
    const pts  = points.current;
    if (!g || !pts) return;

    const t   = st.clock.elapsedTime;
    const dt2 = Math.min(dt, 0.05);

    // ── Smooth raw audio levels ────────────────────────────────────────────────
    // Organic damping: 10 for active states gives fluid, premium motion
    // without sacrificing responsiveness to speech onset/offset.
    const micDamp = aiState === "LISTENING" ? 10 : 8;
    const ttsDamp = aiState === "SPEAKING"  ? 10 : 8;
    mic.current = THREE.MathUtils.damp(mic.current, micLevel, micDamp, dt);
    tts.current = THREE.MathUtils.damp(tts.current, ttsLevel, ttsDamp, dt);

    // Noise floor: mic levels below 0.03 are ambient room noise — treat as silence
    // to prevent micro-jitter when nobody is speaking.
    const cleanMic = mic.current < 0.03 ? 0 : mic.current;

    // ── Target scale per state ─────────────────────────────────────────────────
    let target = BASE_SCALE;

    if (aiState === "IDLE") {
      // Gentle two-frequency breathing — calm, alive, not mechanical
      target = BASE_SCALE
        + Math.sin(t * 0.75) * 0.015
        + Math.sin(t * 0.31) * 0.006;

    } else if (aiState === "LISTENING") {
      // Expand organically with voice amplitude — louder speech = slightly larger orb, silence = baseline
      // Cubic easing (pow 0.7) is less aggressive than sqrt, reducing sensitivity to small
      // fluctuations while preserving dramatic response to loud speech.
      const voiceExpansion = Math.pow(cleanMic, 0.7) * 0.10;
      target = BASE_SCALE + voiceExpansion;

    } else if (aiState === "SPEAKING") {
      // Expand with TTS audio amplitude — authentic speech rhythm.
      // Fallback gentle pulse when tts is zero (TTS warming up or between chunks).
      const warmupPulse = tts.current < 0.025
        ? Math.abs(Math.sin(t * 5.5)) * 0.010
        : 0;
      target = BASE_SCALE + 0.01 + tts.current * 0.16 + warmupPulse;

    } else if (aiState === "THINKING") {
      // Elevated steady state + tight high-frequency pulse = "processing" feel
      // Distinct from EXECUTING: smaller base, different pulse frequency
      target = BASE_SCALE + 0.04 + Math.sin(t * 5.5) * 0.010;

    } else if (aiState === "EXECUTING") {
      // Larger than THINKING + faster pulse + slight breathless urgency
      target = BASE_SCALE + 0.06 + Math.sin(t * 9.0) * 0.008;

    } else if (aiState === "ERROR") {
      // Contracted, slow warning strobe
      target = BASE_SCALE - 0.04 + Math.sin(t * 3.0) * 0.010;
    }

    // ── Lerp scale (framerate independent) ────────────────────────────────────
    const lambda = SCALE_DAMP[aiState] ?? 4.0;
    scale.current = THREE.MathUtils.damp(scale.current, target, lambda, dt);
    g.scale.setScalar(scale.current);

    // ── Rotation (state-specific speed, smooth transition) ────────────────────
    const targetRotSpeed = ROT_SPEED[aiState] ?? 0.10;
    if (g.userData.rotSpeed === undefined) g.userData.rotSpeed = ROT_SPEED.IDLE;
    // Rotation speed transitions with lambda=5 — takes ~0.6s to fully change
    g.userData.rotSpeed = THREE.MathUtils.damp(g.userData.rotSpeed, targetRotSpeed, 5, dt);
    g.rotation.y += dt2 * g.userData.rotSpeed;
    g.rotation.x += dt2 * g.userData.rotSpeed * 0.22;

    // ── Material: color + opacity + size ──────────────────────────────────────
    const mat = pts.material as THREE.PointsMaterial;

    // Color lerp — instant enough to feel crisp, smooth enough to avoid flash
    const targetColorStr = (aiState === "IDLE" && micMuted) ? "#334155" : COLORS[aiState];
    color.current.set(targetColorStr);
    mat.color.lerp(color.current, 1 - Math.exp(-5 * dt));

    // Audio level drives opacity + particle size boost
    const audioLevel = aiState === "SPEAKING"
      ? tts.current
      : aiState === "LISTENING"
        ? mic.current
        : 0;

    mat.opacity    = Math.min(1, 0.78 + audioLevel * 0.22);
    mat.size       = BASE_PARTICLE + audioLevel * 0.008;
    mat.needsUpdate = true;
  });

  return (
    <group ref={group}>
      {/* Outer particle sphere */}
      <points ref={points}>
        <bufferGeometry />
        <pointsMaterial
          color={COLORS.IDLE}
          size={BASE_PARTICLE}
          transparent
          opacity={0.86}
          depthWrite={false}
          sizeAttenuation
          blending={THREE.AdditiveBlending}
        />
      </points>
    </group>
  );
}
