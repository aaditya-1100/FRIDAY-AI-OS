import { Canvas } from "@react-three/fiber";
import { motion, AnimatePresence } from "framer-motion";
import { useAtom, useAtomValue } from "jotai";
import { Suspense, useEffect, useState } from "react";
import { aiStateAtom, commandErrorAtom, wsConnectedAtom, mapModeAtom, mapLocationAtom, type AiState } from "./atoms";
import { MicButton } from "./components/MicButton";
import { ParticleOrb } from "./components/ParticleOrb";
import { StatusCard } from "./components/StatusCard";
import { WeatherWidget } from "./components/WeatherWidget";
import { ClockWidget } from "./components/ClockWidget";
import { useFridaySocket } from "./hooks/useFridaySocket";

function statusFor(state: AiState, connected: boolean, err: string | null) {
  if (err) return err;
  if (!connected) return "Waiting for server…";
  switch (state) {
    case "LISTENING":
      return "Listening";
    case "THINKING":
      return "Thinking";
    case "EXECUTING":
      return "Working";
    case "SPEAKING":
      return "Speaking";
    case "ERROR":
      return "Error";
    default:
      return "Ready";
  }
}

export default function App() {
  const aiState = useAtomValue(aiStateAtom);
  const connected = useAtomValue(wsConnectedAtom);
  const commandError = useAtomValue(commandErrorAtom);
  const [mapMode, setMapMode] = useAtom(mapModeAtom);
  const [mapLocation, setMapLocation] = useAtom(mapLocationAtom);
  // Globe intro: "globe" phase plays first, then transitions to "map"
  const [mapPhase, setMapPhase] = useState<"globe" | "map">("globe");
  useFridaySocket();

  useEffect(() => {
    if (mapMode) {
      // Map just opened — start globe phase, then transition to map
      setMapPhase("globe");
      const t = setTimeout(() => setMapPhase("map"), 1400);
      return () => clearTimeout(t);
    } else {
      // Map closed — reset phase after exit animation so next open starts fresh
      const t = setTimeout(() => setMapPhase("globe"), 500);
      return () => clearTimeout(t);
    }
  }, [mapMode]);

  return (
    <div className="relative flex h-full w-full flex-col bg-[#030508] font-display text-white overflow-hidden">
      <div
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_80%_50%_at_50%_40%,rgba(120,140,200,0.12),transparent_55%),radial-gradient(ellipse_60%_40%_at_50%_100%,rgba(80,100,160,0.08),transparent_50%)]"
        aria-hidden
      />

      {/* Cinematic Fullscreen Map Layer */}
      <AnimatePresence>
        {mapMode && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.45 }}
            className="absolute inset-0 z-40 bg-[#020408] overflow-hidden"
          >

            {/* ── GLOBE INTRO PHASE ────────────────────────────────────────── */}
            <AnimatePresence>
              {mapPhase === "globe" && (
                <motion.div
                  key="globe-intro"
                  initial={{ opacity: 0, scale: 0.6 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 1.5 }}
                  transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
                  className="absolute inset-0 flex flex-col items-center justify-center"
                >
                  {/* Outer glow ring */}
                  <motion.div
                    className="absolute rounded-full"
                    style={{ width: 280, height: 280, background: "radial-gradient(circle, rgba(6,182,212,0.12) 0%, transparent 70%)" }}
                    animate={{ scale: [1, 1.15, 1] }}
                    transition={{ duration: 1.2, repeat: Infinity, ease: "easeInOut" }}
                  />

                  {/* Spinning globe SVG */}
                  <motion.svg
                    width="180" height="180" viewBox="0 0 180 180"
                    animate={{ rotate: 360 }}
                    transition={{ duration: 3, repeat: Infinity, ease: "linear" }}
                    style={{ filter: "drop-shadow(0 0 18px rgba(6,182,212,0.5))" }}
                  >
                    {/* Globe circle */}
                    <circle cx="90" cy="90" r="78" stroke="rgba(6,182,212,0.35)" strokeWidth="1.5" fill="rgba(6,182,212,0.04)" />
                    {/* Meridians */}
                    {[-60,-30,0,30,60].map((x, i) => (
                      <ellipse key={i} cx="90" cy="90" rx={Math.abs(Math.cos(x * Math.PI / 90) * 78)} ry="78"
                        stroke="rgba(6,182,212,0.2)" strokeWidth="1" fill="none" />
                    ))}
                    {/* Parallels */}
                    {[-50,-25,0,25,50].map((y, i) => {
                      const cy = 90 + y * 78 / 90;
                      const rx = Math.sqrt(Math.max(0, 78*78 - (y * 78/90)**2));
                      return <ellipse key={i} cx="90" cy={cy} rx={rx} ry={rx * 0.18}
                        stroke="rgba(6,182,212,0.18)" strokeWidth="1" fill="none" />;
                    })}
                    {/* Bright dot — location pin */}
                    <circle cx="90" cy="90" r="4" fill="#06b6d4" opacity="0.9" />
                    <circle cx="90" cy="90" r="8" stroke="#06b6d4" strokeWidth="1" fill="none" opacity="0.5" />
                  </motion.svg>

                  {/* Location label */}
                  <motion.div
                    className="mt-6 text-center"
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.3 }}
                  >
                    <p className="text-[9px] font-black tracking-[0.5em] text-cyan-400/60 mb-1">NAVIGATING TO</p>
                    <p className="text-lg font-bold tracking-widest text-white uppercase">{mapLocation || "TARGET"}</p>
                    {/* Animated scan line */}
                    <motion.div
                      className="mt-2 h-px mx-auto bg-gradient-to-r from-transparent via-cyan-400 to-transparent"
                      style={{ width: 120 }}
                      animate={{ scaleX: [0.2, 1, 0.2], opacity: [0.3, 1, 0.3] }}
                      transition={{ duration: 1.2, repeat: Infinity, ease: "easeInOut" }}
                    />
                  </motion.div>
                </motion.div>
              )}
            </AnimatePresence>

            {/* ── MAP PHASE ────────────────────────────────────────────────── */}
            <AnimatePresence>
              {mapPhase === "map" && (
                <motion.div
                  key="map-view"
                  className="absolute inset-0"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
                >
                  {/* Map iframe zooms in from 1.15 */}
                  <motion.div
                    className="absolute inset-0"
                    initial={{ scale: 1.15, filter: "blur(6px) brightness(0.2)" }}
                    animate={{ scale: 1,    filter: "blur(0px) brightness(1)"  }}
                    transition={{ duration: 1.0, ease: [0.22, 1, 0.36, 1] }}
                  >
                    <iframe
                      title="Tactical Map"
                      src={`https://maps.google.com/maps?q=${encodeURIComponent(mapLocation || "Earth")}&t=k&z=12&ie=UTF8&iwloc=&output=embed`}
                      className="h-full w-full border-none"
                      style={{ filter: "invert(88%) hue-rotate(180deg) brightness(80%) contrast(120%) saturate(70%)" }}
                    />
                  </motion.div>

                  {/* Vignette */}
                  <div className="pointer-events-none absolute inset-0" style={{ boxShadow: "inset 0 0 120px rgba(0,0,0,0.75)" }} />

                  {/* Scanlines */}
                  <div className="pointer-events-none absolute inset-0 opacity-10"
                    style={{ backgroundImage: "repeating-linear-gradient(0deg, transparent, transparent 3px, rgba(0,0,0,0.3) 3px, rgba(0,0,0,0.3) 4px)" }} />

                  {/* HUD corners */}
                  {["top-4 left-4 border-t border-l","top-4 right-4 border-t border-r",
                    "bottom-4 left-4 border-b border-l","bottom-4 right-4 border-b border-r"
                  ].map((cls, i) => (
                    <motion.div key={i}
                      className={`pointer-events-none absolute h-8 w-8 border-cyan-400/40 ${cls}`}
                      initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                      transition={{ delay: 0.2 + i * 0.06 }} />
                  ))}

                  {/* Top HUD */}
                  <motion.div
                    className="pointer-events-none absolute inset-x-0 top-0 z-50 px-6 pt-8 flex flex-col items-center"
                    initial={{ opacity: 0, y: -12 }} animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.25 }}
                  >
                    <span className="text-[9px] font-black tracking-[0.5em] text-cyan-400/70 mb-1">TACTICAL SATELLITE LINK</span>
                    <h2 className="text-xl font-bold tracking-[0.2em] text-white uppercase">{mapLocation || "SCANNING REGION"}</h2>
                    <motion.div className="mt-2 h-px w-40 bg-gradient-to-r from-transparent via-cyan-400 to-transparent"
                      animate={{ scaleX: [0.3, 1, 0.3], opacity: [0.4, 1, 0.4] }}
                      transition={{ duration: 2.5, repeat: Infinity, ease: "easeInOut" }} />
                  </motion.div>

                  {/* Bottom HUD */}
                  <div className="pointer-events-none absolute inset-x-0 bottom-5 flex justify-center">
                    <span className="text-[9px] font-mono tracking-widest text-cyan-400/35">SYS:MAPLINK ● ENCRYPTED ● LIVE FEED</span>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            {/* Close button — always visible */}
            <motion.button
              onClick={() => { setMapMode(false); setMapLocation(""); }}
              className="absolute right-5 top-5 z-50 flex h-10 w-10 items-center justify-center rounded-full border border-white/10 bg-black/60 text-white/60 backdrop-blur-md transition-all hover:bg-white/10 hover:text-white hover:border-cyan-400/30"
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.4 }}
              whileHover={{ scale: 1.08 }} whileTap={{ scale: 0.93 }}
            >
              <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-4 h-4">
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </motion.button>
          </motion.div>
        )}
      </AnimatePresence>




      <header className="relative z-10 flex flex-none justify-center pt-10 md:pt-14">
        <motion.h1
          initial={{ opacity: 0, y: -12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
          className="text-center text-4xl font-extrabold tracking-[0.42em] text-white md:text-5xl"
          style={{ textIndent: "0.42em" }}
        >
          FRIDAY
        </motion.h1>
      </header>

      <div className="relative z-0 min-h-0 flex-1 flex items-center justify-center">
        <div style={{ width: "min(100%, 100vh - 220px)", aspectRatio: "1 / 1" }}>
          <Canvas camera={{ position: [0, 0, 2.5], fov: 45 }} gl={{ alpha: true, antialias: true }}>
            <ambientLight intensity={0.35} />
            <Suspense fallback={null}>
              <ParticleOrb />
            </Suspense>
          </Canvas>
        </div>
      </div>

      {/* Floating status panel */}
      <StatusCard />

      {/* Realtime weather widget — Kashipur, India */}
      <WeatherWidget />

      {/* Holographic live clock widget */}
      <ClockWidget />

      <footer className="relative z-10 flex flex-none flex-col items-center pb-12 md:pb-16">
        <motion.p
          key={aiState + (connected ? "1" : "0") + (commandError ?? "")}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35 }}
          className={`max-w-md px-4 text-center text-sm font-medium tracking-wide md:text-base ${
            commandError ? "text-amber-200/90" : "text-white/75"
          }`}
        >
          {statusFor(aiState, connected, commandError)}
        </motion.p>
        <MicButton />
      </footer>
    </div>
  );
}
