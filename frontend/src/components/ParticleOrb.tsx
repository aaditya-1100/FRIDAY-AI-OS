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
    const t  = phi * i;
    p[i * 3]     = Math.cos(t) * rr * radius;
    p[i * 3 + 1] = y * radius;
    p[i * 3 + 2] = Math.sin(t) * rr * radius;
  }
  return p;
}

function rotSpeed(state: AiState): number {
  if (state === "ERROR")                              return 0.05;
  if (state === "THINKING" || state === "EXECUTING") return 0.50;
  if (state === "SPEAKING")                           return 0.38;
  if (state === "LISTENING")                          return 0.20;
  return 0.08;
}

export function ParticleOrb() {
  const group       = useRef<THREE.Group>(null);
  const points      = useRef<THREE.Points>(null);
  const smoothScale = useRef(0.48);
  const smoothWobble = useRef(0.003);

  const aiState  = useAtomValue(aiStateAtom);
  const micLevel = useAtomValue(micLevelAtom);  // 0..1 live mic RMS
  const ttsLevel = useAtomValue(ttsLevelAtom);  // 0..1 live TTS RMS
  const base     = useMemo(() => fibonacciSphere(COUNT, 1), []);

  useLayoutEffect(() => {
    const geom = points.current?.geometry;
    if (!geom) return;
    geom.setAttribute("position", new THREE.BufferAttribute(new Float32Array(base), 3));
  }, [base]);

  useFrame((st, delta) => {
    const t   = st.clock.elapsedTime;
    const g   = group.current;
    const pts = points.current;
    if (!g || !pts) return;

    // ── Compute target scale based on state + live audio ─────────────────────
    // BASE = 0.42. Active states push it up. Audio levels push further.
    const BASE = 0.42;
    let targetScale = BASE;
    let targetWobble = 0.003;

    switch (aiState) {
      case "IDLE":
        // Subtle breathing — very gentle
        targetScale  = BASE + Math.sin(t * 1.1) * 0.020 + Math.sin(t * 0.4) * 0.008;
        targetWobble = 0;
        break;

      case "LISTENING": {
        const micBoost = micLevel * 0.45;
        targetScale  = BASE + 0.02 + micBoost;
        targetWobble = 0;
        break;
      }

      case "SPEAKING": {
        const ttsBoost = ttsLevel * 0.43;
        const synth = ttsLevel < 0.01
          ? Math.abs(Math.sin(t * 7.5)) * 0.04 + Math.abs(Math.sin(t * 3.3)) * 0.025
          : 0;
        targetScale  = BASE + 0.04 + ttsBoost + synth;
        targetWobble = 0;
        break;
      }

      case "THINKING":
      case "EXECUTING": {
        const pulse = Math.sin(t * 4.5) * 0.038 + Math.sin(t * 2.1) * 0.022;
        targetScale  = BASE + 0.08 + pulse;
        targetWobble = 0;
        break;
      }

      case "ERROR":
        targetScale  = BASE - 0.06 + Math.sin(t * 3.0) * 0.018;
        targetWobble = 0;
        break;
    }

    // ── Smooth scale toward target ────────────────────────────────────────────
    // Fast track when audio is driving (LISTENING / SPEAKING) so it feels live.
    // Slow track for idle breathing.
    const isAudioDriven = aiState === "LISTENING" || aiState === "SPEAKING";
    const scaleLerp = isAudioDriven ? 0.28 : (aiState === "IDLE" ? 0.05 : 0.14);
    smoothScale.current  += (targetScale  - smoothScale.current)  * scaleLerp;
    smoothWobble.current += (targetWobble - smoothWobble.current) * 0.12;

    g.scale.setScalar(smoothScale.current);

    // ── Rotation ─────────────────────────────────────────────────────────────
    const rs = rotSpeed(aiState);
    g.rotation.y += delta * rs;
    g.rotation.x += delta * rs * 0.33;
    g.rotation.z += delta * rs * 0.11;

    // ── Per-particle surface distortion (disabled — keep perfect sphere) ─────
    // No wobble applied; particles stay on their base fibonacci sphere positions.
    // pos.needsUpdate only needed if we modify positions.

    // ── Material: opacity + size + color ─────────────────────────────────────
    const mat = pts.material as THREE.PointsMaterial;

    const opTarget =
      aiState === "ERROR"      ? 0.68 + Math.sin(t * 4) * 0.10 :
      aiState === "THINKING" || aiState === "EXECUTING"
                               ? 0.90 + Math.sin(t * 7) * 0.08 :
      aiState === "SPEAKING"   ? 0.82 + ttsLevel * 0.18 :
      aiState === "LISTENING"  ? 0.78 + micLevel * 0.22 :
                                 0.70;
    mat.opacity = Math.min(1, opTarget);

    mat.size =
      aiState === "THINKING" || aiState === "EXECUTING" ? 0.026 :
      aiState === "ERROR"                                ? 0.024 :
      aiState === "SPEAKING"   ? 0.021 + ttsLevel * 0.010 :
      aiState === "LISTENING"  ? 0.021 + micLevel * 0.010 :
                                 0.019;

    mat.color.set(aiState === "ERROR" ? "#ffb4a2" : "#eef2ff");
    mat.needsUpdate = true;
  });

  return (
    <group ref={group}>
      <points ref={points}>
        <bufferGeometry />
        <pointsMaterial
          color="#eef2ff"
          size={0.020}
          transparent
          opacity={0.75}
          depthWrite={false}
          sizeAttenuation
          blending={THREE.AdditiveBlending}
        />
      </points>
    </group>
  );
}
