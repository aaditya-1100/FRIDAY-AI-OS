import { Canvas } from "@react-three/fiber";
import { motion } from "framer-motion";
import { useAtomValue } from "jotai";
import { Suspense } from "react";
import { aiStateAtom, commandErrorAtom, wsConnectedAtom, type AiState } from "./atoms";
import { MicButton } from "./components/MicButton";
import { ParticleOrb } from "./components/ParticleOrb";
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
  useFridaySocket();

  return (
    <div className="relative flex h-full w-full flex-col bg-[#030508] font-display text-white">
      <div
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_80%_50%_at_50%_40%,rgba(120,140,200,0.12),transparent_55%),radial-gradient(ellipse_60%_40%_at_50%_100%,rgba(80,100,160,0.08),transparent_50%)]"
        aria-hidden
      />

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
