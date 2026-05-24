/**
 * ParticleOrb — voice-driven scale only.
 * Idle: slow breathing. Listening: grows with mic. Speaking: grows with TTS.
 * No per-particle distortion. Clean, smooth, lightweight.
 */
import { useFrame } from "@react-three/fiber";
import { useAtomValue } from "jotai";
import { useLayoutEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { aiStateAtom, micLevelAtom, ttsLevelAtom, type AiState } from "../atoms";

const COUNT = 900;

function fibonacciSphere(count: number, radius: number) {
  const p   = new Float32Array(count * 3);
  const phi = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < count; i++) {
    const y  = 1 - (i / Math.max(1, count - 1)) * 2;
    const rr = Math.sqrt(Math.max(0, 1 - y * y));
    const th = phi * i;
    p[i * 3]     = Math.cos(th) * rr * radius;
    p[i * 3 + 1] = y * radius;
    p[i * 3 + 2] = Math.sin(th) * rr * radius;
  }
  return p;
}

const COLORS: Record<AiState, string> = {
  IDLE:      "#6366f1",
  LISTENING: "#06b6d4",
  THINKING:  "#a855f7",
  EXECUTING: "#a855f7",
  SPEAKING:  "#eab308",
  ERROR:     "#ef4444",
};

export function ParticleOrb() {
  const group  = useRef<THREE.Group>(null);
  const points = useRef<THREE.Points>(null);
  const base   = useMemo(() => fibonacciSphere(COUNT, 1), []);

  const aiState  = useAtomValue(aiStateAtom);
  const micLevel = useAtomValue(micLevelAtom);
  const ttsLevel = useAtomValue(ttsLevelAtom);

  // Smoothed scale — lerped each frame, no jitter
  const scale  = useRef(0.42);
  // Smoothed audio — prevents jitter from raw mic/tts values
  const mic    = useRef(0);
  const tts    = useRef(0);
  // GC-safe color target
  const color  = useRef(new THREE.Color(COLORS.IDLE));

  useLayoutEffect(() => {
    const geom = points.current?.geometry;
    if (!geom) return;
    geom.setAttribute("position", new THREE.BufferAttribute(new Float32Array(base), 3));
  }, [base]);

  useFrame((st, dt) => {
    const g   = group.current;
    const pts = points.current;
    if (!g || !pts) return;

    const t  = st.clock.elapsedTime;
    const dt2 = Math.min(dt, 0.05);

    // ── Smooth raw audio levels (Framerate Independent Damping) ─────────────
    mic.current = THREE.MathUtils.damp(mic.current, micLevel, 15, dt);
    tts.current = THREE.MathUtils.damp(tts.current, ttsLevel, 15, dt);

    // ── Target scale per state ────────────────────────────────────────────────
    const BASE = 0.42;
    let target = BASE;

    if (aiState === "IDLE") {
      // Gentle breathing — slow sin wave
      target = BASE + Math.sin(t * 0.8) * 0.018 + Math.sin(t * 0.33) * 0.008;
    } else if (aiState === "LISTENING") {
      // Expands directly with mic volume
      target = BASE + 0.02 + mic.current * 0.40;
    } else if (aiState === "SPEAKING") {
      // Expands with TTS output; fallback pulse when TTS level is 0
      const pulse = tts.current < 0.02 ? Math.abs(Math.sin(t * 5.0)) * 0.03 : 0;
      target = BASE + 0.03 + tts.current * 0.38 + pulse;
    } else if (aiState === "THINKING" || aiState === "EXECUTING") {
      // Steady elevated + gentle pulse — "processing" feel
      target = BASE + 0.08 + Math.sin(t * 4.0) * 0.022;
    } else if (aiState === "ERROR") {
      target = BASE - 0.04 + Math.sin(t * 3.5) * 0.015;
    }

    // ── Lerp scale — fast for audio states, slow for IDLE breathing ──────────
    const lambda = (aiState === "LISTENING" || aiState === "SPEAKING") ? 12 : 3;
    scale.current = THREE.MathUtils.damp(scale.current, target, lambda, dt);
    g.scale.setScalar(scale.current);

    // ── Rotation — smooth transition between speeds ───────────────────────────
    const targetRotSpeed = aiState === "IDLE" ? 0.06 : aiState === "THINKING" || aiState === "EXECUTING" ? 0.30 : 0.14;
    // We attach rotSpeed to g.userData to persist it across frames without needing another ref
    if (g.userData.rotSpeed === undefined) g.userData.rotSpeed = 0.06;
    g.userData.rotSpeed = THREE.MathUtils.damp(g.userData.rotSpeed, targetRotSpeed, 4, dt);
    
    g.rotation.y += dt2 * g.userData.rotSpeed;
    g.rotation.x += dt2 * g.userData.rotSpeed * 0.25;

    // ── Material ──────────────────────────────────────────────────────────────
    const mat = pts.material as THREE.PointsMaterial;

    // Color lerp (framerate independent)
    color.current.set(COLORS[aiState]);
    mat.color.lerp(color.current, 1 - Math.exp(-4 * dt));

    // Opacity and size track audio
    const audioLevel = aiState === "SPEAKING" ? tts.current : aiState === "LISTENING" ? mic.current : 0;
    mat.opacity = Math.min(1, 0.72 + audioLevel * 0.25);
    mat.size    = 0.019 + audioLevel * 0.010;
    mat.needsUpdate = true;
  });

  return (
    <group ref={group}>
      <points ref={points}>
        <bufferGeometry />
        <pointsMaterial
          color={COLORS.IDLE}
          size={0.019}
          transparent
          opacity={0.72}
          depthWrite={false}
          sizeAttenuation
          blending={THREE.AdditiveBlending}
        />
      </points>
    </group>
  );
}
