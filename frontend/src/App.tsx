import { Canvas } from "@react-three/fiber";
import { motion, AnimatePresence } from "framer-motion";
import { useAtom, useAtomValue } from "jotai";
import { Suspense, useEffect, useState } from "react";
import { aiStateAtom, commandErrorAtom, wsConnectedAtom, mapModeAtom, mapLocationAtom, mapLatAtom, mapLonAtom, type AiState } from "./atoms";
import { MicButton } from "./components/MicButton";
import { ParticleOrb } from "./components/ParticleOrb";
import { RemindersPanel, ReminderToastOverlay } from "./components/RemindersPanel";
import { useFridaySocket } from "./hooks/useFridaySocket";
import { ClockWidget } from "./components/ClockWidget";
import { WeatherWidget } from "./components/WeatherWidget";
import { StatusCard } from "./components/StatusCard";
import { CommandBar } from "./components/CommandBar";

const GLOW_COLORS: Record<AiState, { primary: string; secondary: string; border: string; labelColor: string }> = {
  IDLE:         { primary: "rgba(79,70,229,0.08)",   secondary: "rgba(99,102,241,0.02)",  border: "rgba(79,70,229,0.18)", labelColor: "text-indigo-400" },
  PERCEIVING:   { primary: "rgba(6,182,212,0.10)",   secondary: "rgba(34,211,238,0.03)",  border: "rgba(6,182,212,0.22)", labelColor: "text-cyan-400" },
  PLANNING:     { primary: "rgba(236,72,153,0.10)",  secondary: "rgba(244,63,94,0.03)",   border: "rgba(236,72,153,0.22)", labelColor: "text-pink-400" },
  DELEGATING:   { primary: "rgba(236,72,153,0.10)",  secondary: "rgba(244,63,94,0.03)",   border: "rgba(236,72,153,0.22)", labelColor: "text-pink-400" },
  WAITING:      { primary: "rgba(99,102,241,0.06)",  secondary: "rgba(79,70,229,0.02)",  border: "rgba(99,102,241,0.15)", labelColor: "text-indigo-300" },
  SYNTHESIZING: { primary: "rgba(168,85,247,0.10)",  secondary: "rgba(192,132,252,0.03)", border: "rgba(168,85,247,0.22)", labelColor: "text-purple-400" },
  RESPONDING:   { primary: "rgba(245,158,11,0.10)",  secondary: "rgba(251,191,36,0.03)",  border: "rgba(245,158,11,0.22)", labelColor: "text-amber-400" },
  REFLECTING:   { primary: "rgba(49,46,129,0.06)",   secondary: "rgba(30,27,75,0.02)",   border: "rgba(49,46,129,0.15)", labelColor: "text-blue-900" },
  INTERRUPTED:  { primary: "rgba(244,63,94,0.12)",   secondary: "rgba(225,29,72,0.04)",   border: "rgba(244,63,94,0.25)", labelColor: "text-rose-400" },
  ERROR:        { primary: "rgba(239,68,68,0.15)",   secondary: "rgba(220,38,38,0.05)",   border: "rgba(239,68,68,0.30)", labelColor: "text-red-500" },
  LISTENING:    { primary: "rgba(6,182,212,0.10)",   secondary: "rgba(34,211,238,0.03)",  border: "rgba(6,182,212,0.22)", labelColor: "text-cyan-400" },
  THINKING:     { primary: "rgba(168,85,247,0.10)",  secondary: "rgba(192,132,252,0.03)", border: "rgba(168,85,247,0.22)", labelColor: "text-purple-400" },
  EXECUTING:    { primary: "rgba(236,72,153,0.10)",  secondary: "rgba(244,63,94,0.03)",   border: "rgba(236,72,153,0.22)", labelColor: "text-pink-400" },
  SPEAKING:     { primary: "rgba(245,158,11,0.10)",  secondary: "rgba(251,191,36,0.03)",  border: "rgba(245,158,11,0.22)", labelColor: "text-amber-400" },
};

function statusFor(state: AiState, connected: boolean, err: string | null) {
  if (err) return err;
  if (!connected) return "Connecting server link…";
  switch (state) {
    case "LISTENING":
    case "PERCEIVING":
      return "LISTENING";
    case "THINKING":
    case "SYNTHESIZING":
      return "SYNTHESIZING";
    case "EXECUTING":
    case "PLANNING":
    case "DELEGATING":
      return "EXECUTING WORKLOAD";
    case "SPEAKING":
    case "RESPONDING":
      return "TRANSMITTING RESPONSE";
    case "WAITING":
      return "STANDBY WAITING";
    case "REFLECTING":
      return "REFLECTING COMPLETED CYCLE";
    case "INTERRUPTED":
      return "INTERRUPTED STREAM";
    case "ERROR":
      return "HARDWARE SYSTEM ERROR";
    default:
      return "SYSTEM ONLINE";
  }
}

export default function App() {
  const aiState = useAtomValue(aiStateAtom);
  const connected = useAtomValue(wsConnectedAtom);
  const commandError = useAtomValue(commandErrorAtom);
  const [mapMode, setMapMode] = useAtom(mapModeAtom);
  const [mapLocation, setMapLocation] = useAtom(mapLocationAtom);
  const mapLat = useAtomValue(mapLatAtom);
  const mapLon = useAtomValue(mapLonAtom);
  const [mapPhase, setMapPhase] = useState<"globe" | "map">("globe");
  
  const { sendCommand } = useFridaySocket();

  useEffect(() => {
    if (mapMode) {
      setMapPhase("globe");
      const t = setTimeout(() => setMapPhase("map"), 1400);
      return () => clearTimeout(t);
    } else {
      const t = setTimeout(() => setMapPhase("globe"), 500);
      return () => clearTimeout(t);
    }
  }, [mapMode]);

  const glow = GLOW_COLORS[aiState] || GLOW_COLORS.IDLE;

  return (
    <div className="relative flex h-screen w-screen bg-[#020408] font-display text-white overflow-hidden">
      
      {/* ── Dynamic Ambient glow-mesh circle ────────────────────────────────────── */}
      <div
        className="absolute w-[80vw] h-[80vw] max-w-[800px] max-h-[800px] blur-[140px] pointer-events-none opacity-40 mix-blend-screen animate-ambient-morph"
        style={{
          background: `radial-gradient(circle, ${glow.primary} 0%, ${glow.secondary} 60%, transparent 100%)`,
          left: "calc(50% - min(40vw, 400px))",
          top: "calc(45% - min(40vw, 400px))",
          transition: "background 0.8s ease-in-out",
        }}
      />
      
      {/* Tech grid layout decoration overlay */}
      <div 
        className="pointer-events-none absolute inset-0 opacity-[0.02]"
        style={{
          backgroundImage: `
            linear-gradient(to right, rgba(255, 255, 255, 0.1) 1px, transparent 1px),
            linear-gradient(to bottom, rgba(255, 255, 255, 0.1) 1px, transparent 1px)
          `,
          backgroundSize: "45px 45px",
        }}
      />
      
      {/* HUD vignette & overlay scanlines */}
      <div className="pointer-events-none absolute inset-0 z-20" style={{ boxShadow: "inset 0 0 100px rgba(0,0,0,0.8)" }} />
      <div className="pointer-events-none absolute inset-0 z-20 opacity-[0.03]"
           style={{ backgroundImage: "repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(255,255,255,0.4) 2px, rgba(255,255,255,0.4) 3px)" }} />

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
                  <motion.div
                    className="absolute rounded-full"
                    style={{ width: 280, height: 280, background: "radial-gradient(circle, rgba(6,182,212,0.12) 0%, transparent 70%)" }}
                    animate={{ scale: [1, 1.15, 1] }}
                    transition={{ duration: 1.2, repeat: Infinity, ease: "easeInOut" }}
                  />
                  <motion.svg
                    width="180" height="180" viewBox="0 0 180 180"
                    animate={{ rotate: 360 }}
                    transition={{ duration: 3, repeat: Infinity, ease: "linear" }}
                    style={{ filter: "drop-shadow(0 0 18px rgba(6,182,212,0.5))" }}
                  >
                    <circle cx="90" cy="90" r="78" stroke="rgba(6,182,212,0.35)" strokeWidth="1.5" fill="rgba(6,182,212,0.04)" />
                    {[-60,-30,0,30,60].map((x, i) => (
                      <ellipse key={i} cx="90" cy="90" rx={Math.abs(Math.cos(x * Math.PI / 90) * 78)} ry="78"
                        stroke="rgba(6,182,212,0.2)" strokeWidth="1" fill="none" />
                    ))}
                    {[-50,-25,0,25,50].map((y, i) => {
                      const cy = 90 + y * 78 / 90;
                      const rx = Math.sqrt(Math.max(0, 78*78 - (y * 78/90)**2));
                      return <ellipse key={i} cx="90" cy={cy} rx={rx} ry={rx * 0.18}
                        stroke="rgba(6,182,212,0.18)" strokeWidth="1" fill="none" />;
                    })}
                    <circle cx="90" cy="90" r="4" fill="#06b6d4" opacity="0.9" />
                    <circle cx="90" cy="90" r="8" stroke="#06b6d4" strokeWidth="1" fill="none" opacity="0.5" />
                  </motion.svg>
                  <motion.div
                    className="mt-6 text-center"
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.3 }}
                  >
                    <p className="text-[9px] font-black tracking-[0.5em] text-cyan-400/60 mb-1">NAVIGATING TO</p>
                    <p className="text-lg font-bold tracking-widest text-white uppercase">{mapLocation || "TARGET"}</p>
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
              {mapPhase === "map" && (() => {
                const isRoute = mapLocation.startsWith("origin:");
                let hudTitle = "TACTICAL SATELLITE LINK";
                let hudLocation = mapLocation || "SCANNING REGION";
                let originPart = "";
                let destPart = "";

                if (isRoute) {
                  const parts = mapLocation.split(",");
                  originPart = parts.find(p => p.startsWith("origin:"))?.replace("origin:", "") || "";
                  destPart = parts.find(p => p.startsWith("destination:"))?.replace("destination:", "") || "";
                  hudTitle = "GEOSPATIAL ROUTE DIRECT";
                  hudLocation = `${originPart} ➔ ${destPart}`;
                }

                const mapSrcDoc = `
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <title>FRIDAY Tactical Map Link</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <style>
    html, body, #map {
      height: 100%;
      margin: 0;
      padding: 0;
      background: #020408;
    }
    .leaflet-tile-container {
      filter: invert(1) hue-rotate(180deg) brightness(0.65) contrast(1.3) saturate(1.5);
    }
    .pulse-marker {
      background: rgba(6, 182, 212, 0.4);
      border: 2px solid #06b6d4;
      border-radius: 50%;
      box-shadow: 0 0 12px #06b6d4;
      animation: pulse 1.8s infinite ease-in-out;
    }
    @keyframes pulse {
      0% { transform: scale(0.85); opacity: 0.6; }
      50% { transform: scale(1.15); opacity: 1; }
      100% { transform: scale(0.85); opacity: 0.6; }
    }
  </style>
</head>
<body>
  <div id="map"></div>
  <script>
    const map = L.map('map', {
      zoomControl: false,
      attributionControl: false
    }).setView([20, 0], 2);

    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
      maxZoom: 20
    }).addTo(map);

    const tacticalIcon = L.divIcon({
      className: 'pulse-marker',
      iconSize: [16, 16],
      iconAnchor: [8, 8]
    });

    async function geocode(q) {
      try {
        const res = await fetch(\`https://nominatim.openstreetmap.org/search?q=\${encodeURIComponent(q)}&format=json&limit=1\`, {
          headers: { 'User-Agent': 'FRIDAY-Tactical-Map/1.0' }
        });
        const data = await res.json();
        if (data && data.length > 0) {
          return {
            lat: parseFloat(data[0].lat),
            lon: parseFloat(data[0].lon)
          };
        }
      } catch (e) {
        console.error("Geocode failed", e);
      }
      return null;
    }

    async function initMap() {
      const isRoute = ${isRoute};
      const lat = ${mapLat !== null ? mapLat : "null"};
      const lon = ${mapLon !== null ? mapLon : "null"};
      const locationName = \`${mapLocation}\`;
      const originName = \`${originPart}\`;
      const destName = \`${destPart}\`;

      if (isRoute) {
        const start = await geocode(originName);
        const end = await geocode(destName);
        if (start && end) {
          const startMarker = L.marker([start.lat, start.lon], {icon: tacticalIcon}).addTo(map);
          startMarker.bindPopup("<b>Origin:</b> " + originName).openPopup();
          
          const endMarker = L.marker([end.lat, end.lon], {icon: tacticalIcon}).addTo(map);
          endMarker.bindPopup("<b>Destination:</b> " + destName);

          L.circle([start.lat, start.lon], {radius: 5000, color: '#06b6d4', weight: 1, fillOpacity: 0.05}).addTo(map);
          L.circle([end.lat, end.lon], {radius: 5000, color: '#06b6d4', weight: 1, fillOpacity: 0.05}).addTo(map);

          try {
            const routeRes = await fetch(\`https://router.project-osrm.org/route/v1/driving/\${start.lon},\${start.lat};\${end.lon},\${end.lat}?overview=full&geometries=geojson\`);
            const routeData = await routeRes.json();
            if (routeData.routes && routeData.routes.length > 0) {
              const geojson = routeData.routes[0].geometry;
              const routeLine = L.geoJSON(geojson, {
                style: {
                  color: '#06b6d4',
                  weight: 4,
                  opacity: 0.8,
                  dashArray: '8, 8'
                }
              }).addTo(map);
              map.fitBounds(routeLine.getBounds(), { padding: [50, 50] });
            } else {
              const polyline = L.polyline([[start.lat, start.lon], [end.lat, end.lon]], {
                color: '#06b6d4',
                weight: 3,
                opacity: 0.6,
                dashArray: '5, 10'
              }).addTo(map);
              map.fitBounds(polyline.getBounds(), { padding: [50, 50] });
            }
          } catch (e) {
            const polyline = L.polyline([[start.lat, start.lon], [end.lat, end.lon]], {
              color: '#06b6d4',
              weight: 3,
              opacity: 0.6,
              dashArray: '5, 10'
            }).addTo(map);
            map.fitBounds(polyline.getBounds(), { padding: [50, 50] });
          }
        }
      } else if (lat && lon) {
        map.setView([lat, lon], 12);
        const marker = L.marker([lat, lon], {icon: tacticalIcon}).addTo(map);
        marker.bindPopup("<b>Holographic Pin:</b> " + locationName).openPopup();
        L.circle([lat, lon], {radius: 2000, color: '#06b6d4', weight: 1, fillOpacity: 0.05}).addTo(map);
        L.circle([lat, lon], {radius: 4000, color: '#06b6d4', weight: 0.5, fillOpacity: 0.02}).addTo(map);
      } else if (locationName) {
        const pt = await geocode(locationName);
        if (pt) {
          map.setView([pt.lat, pt.lon], 12);
          const marker = L.marker([pt.lat, pt.lon], {icon: tacticalIcon}).addTo(map);
          marker.bindPopup("<b>Holographic Pin:</b> " + locationName).openPopup();
          L.circle([pt.lat, pt.lon], {radius: 2000, color: '#06b6d4', weight: 1, fillOpacity: 0.05}).addTo(map);
        }
      }
    }

    initMap();
  </script>
</body>
</html>
`;

                return (
                  <motion.div
                    key="map-view"
                    className="absolute inset-0"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
                  >
                    <motion.div
                      className="absolute inset-0"
                      initial={{ scale: 1.15, filter: "blur(6px) brightness(0.2)" }}
                      animate={{ scale: 1,    filter: "blur(0px) brightness(1)"  }}
                      transition={{ duration: 1.0, ease: [0.22, 1, 0.36, 1] }}
                    >
                      <iframe
                        title="Tactical Map"
                        srcDoc={mapSrcDoc}
                        className="h-full w-full border-none"
                        style={{ opacity: 0.92 }}
                      />
                    </motion.div>
                    <div className="pointer-events-none absolute inset-0" style={{ boxShadow: "inset 0 0 120px rgba(0,0,0,0.75)" }} />
                    <div className="pointer-events-none absolute inset-0 opacity-10"
                       style={{ backgroundImage: "repeating-linear-gradient(0deg, transparent, transparent 3px, rgba(0,0,0,0.3) 3px, rgba(0,0,0,0.3) 4px)" }} />
                    {["top-4 left-4 border-t border-l","top-4 right-4 border-t border-r",
                      "bottom-4 left-4 border-b border-l","bottom-4 right-4 border-b border-r"
                    ].map((cls, i) => (
                      <motion.div key={i}
                        className={`pointer-events-none absolute h-8 w-8 border-cyan-400/40 ${cls}`}
                        initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                        transition={{ delay: 0.2 + i * 0.06 }} />
                    ))}
                    <motion.div
                      className="pointer-events-none absolute inset-x-0 top-0 z-50 px-6 pt-8 flex flex-col items-center"
                      initial={{ opacity: 0, y: -12 }} animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: 0.25 }}
                    >
                      <span className="text-[9px] font-black tracking-[0.5em] text-cyan-400/70 mb-1">{hudTitle}</span>
                      <h2 className="text-xl font-bold tracking-[0.2em] text-white uppercase">{hudLocation}</h2>
                      <motion.div className="mt-2 h-px w-40 bg-gradient-to-r from-transparent via-cyan-400 to-transparent"
                        animate={{ scaleX: [0.3, 1, 0.3], opacity: [0.4, 1, 0.4] }}
                        transition={{ duration: 2.5, repeat: Infinity, ease: "easeInOut" }} />
                    </motion.div>
                    <div className="pointer-events-none absolute inset-x-0 bottom-5 flex justify-center">
                      <span className="text-[9px] font-mono tracking-widest text-cyan-400/35">SYS:MAPLINK ● ENCRYPTED ● LIVE FEED</span>
                    </div>
                  </motion.div>
                );
              })()}
            </AnimatePresence>

            {/* Close button */}
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

      {/* Reminder Toast Overlay */}
      <ReminderToastOverlay />

      {/* ── MAIN DASHBOARD LAYOUT ────────────────────────────────────────── */}
      <div className="relative z-10 flex flex-col h-full w-full p-6">
        
        {/* ── TOP HUD HEADER BAR ────────────────────────────────────────── */}
        <header className="flex flex-none items-center justify-between border-b border-white/[0.04] pb-4 mb-6">
          <div className="flex items-center gap-3">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
            </span>
            <div className="text-[9px] font-black tracking-[0.25em] text-white/40 font-mono uppercase">
              FRIDAY // COGNITIVE HOLOGRAPHIC OS // R5.SEAL
            </div>
          </div>
          
          <motion.h1
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, ease: "easeOut" }}
            className="text-2xl font-black tracking-[0.55em] text-white/90 select-none mr-[-0.55em]"
          >
            FRIDAY
          </motion.h1>

          <div className="text-[10px] font-bold font-mono tracking-widest text-white/30">
            {connected ? "SECURE SEC-LINK ACTIVE" : "SERVER HOST OFFLINE"}
          </div>
        </header>

        {/* ── MAIN GRID ── */}
        <main className="flex-1 grid grid-cols-1 lg:grid-cols-12 gap-6 min-h-0 overflow-hidden">
          
          {/* ── LEFT PANEL (DIAGNOSTICS & SYSTEM FEEDS) ──────────────────── */}
          <section className="lg:col-span-3 flex flex-col gap-5 overflow-y-auto pr-1">
            <ClockWidget />
            <WeatherWidget />
            
            {/* Embedded Diagnostics Card */}
            <div className="glass-panel rounded-2xl p-5 select-none text-left relative overflow-hidden">
              <div className="absolute top-0 right-0 h-10 w-10 opacity-[0.03]" style={{ background: `radial-gradient(circle, ${glow.border} 0%, transparent 70%)` }} />
              <div className="text-[9px] font-black tracking-[0.25em] text-white/30 uppercase mb-3.5 font-mono">
                DIAGNOSTICS MONITOR
              </div>
              <div className="space-y-2.5 font-mono text-[10.5px]">
                <div className="flex justify-between border-b border-white/[0.02] pb-1.5">
                  <span className="text-white/40">FIRMWARE OS:</span>
                  <span className="text-cyan-400/80 font-semibold">R5.SEAL.PROD</span>
                </div>
                <div className="flex justify-between border-b border-white/[0.02] pb-1.5">
                  <span className="text-white/40">WS STREAM:</span>
                  <span className={connected ? "text-emerald-400 font-semibold" : "text-rose-400 font-semibold"}>
                    {connected ? "SYNC_OK" : "DISCONN"}
                  </span>
                </div>
                <div className="flex justify-between border-b border-white/[0.02] pb-1.5">
                  <span className="text-white/40">TTS AUDIO:</span>
                  <span className="text-amber-400/80 font-semibold">WEBAUDIO_ANALYSER</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-white/40">INTENT MATRIX:</span>
                  <span className="text-purple-400/80 font-semibold">ONNX_LOCAL_PARSER</span>
                </div>
              </div>
            </div>
          </section>

          {/* ── CENTER GRID (AI ORB & CONTROL CORE) ─────────────────────── */}
          <section className="lg:col-span-6 flex flex-col justify-between items-center relative py-2">
            
            {/* Animated crosshairs & rotating HUD overlays */}
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none overflow-hidden max-h-[460px]">
              
              {/* Rotating outer vector line */}
              <div className="absolute w-[360px] h-[360px] rounded-full border border-dashed border-white/[0.04] animate-hud-spin-cw scale-[1.08] hidden sm:block" />
              
              {/* Counter-rotating inner vector ring */}
              <div className="absolute w-[280px] h-[280px] rounded-full border border-white/[0.02] animate-hud-spin-ccw scale-[0.88]" />
              
              {/* State-colored target locks */}
              <div 
                className="absolute w-[310px] h-[310px] rounded-full border border-white/[0.01]" 
                style={{
                  boxShadow: `0 0 40px ${glow.border}08`,
                  borderColor: `${glow.border}12`
                }}
              />
              
              {/* Corner HUD Ticks */}
              {["top-10 left-10 border-t border-l", "top-10 right-10 border-t border-r", "bottom-24 left-10 border-b border-l", "bottom-24 right-10 border-b border-r"].map((cls, idx) => (
                <div key={idx} className={`absolute w-4 h-4 border-white/10 ${cls} hidden sm:block`} />
              ))}
            </div>

            {/* Core State Display Label */}
            <div className="text-center mt-2 z-10">
              <span className="text-[9px] font-black tracking-[0.35em] text-white/30 font-mono uppercase block mb-1">
                SYSTEM CORE STATE
              </span>
              <span className={`text-[12px] font-black tracking-[0.25em] font-mono uppercase ${glow.labelColor}`} style={{ textShadow: `0 0 10px ${glow.border}44` }}>
                {statusFor(aiState, connected, commandError)}
              </span>
            </div>

            {/* Canvas Core stage */}
            <div className="relative z-10 w-full flex-1 flex items-center justify-center max-h-[380px] sm:max-h-[420px]">
              <div className="w-[260px] sm:w-[320px] md:w-[360px]" style={{ width: "min(100%, 100vh - 360px)", aspectRatio: "1 / 1" }}>
                <Canvas camera={{ position: [0, 0, 2.5], fov: 45 }} gl={{ alpha: true, antialias: true }}>
                  <ambientLight intensity={0.35} />
                  <Suspense fallback={null}>
                    <ParticleOrb />
                  </Suspense>
                </Canvas>
              </div>
            </div>

            {/* Bottom voice / input capsule stack */}
            <div className="w-full flex flex-col items-center gap-4 z-10 mb-2">
              <MicButton />
              <CommandBar onSend={sendCommand} />
            </div>
          </section>

          {/* ── RIGHT PANEL (TRANSCRIPT & TIMERS) ────────────────────────── */}
          <section className="lg:col-span-3 flex flex-col gap-5 overflow-y-auto pl-1">
            <StatusCard />
            <RemindersPanel />

            {/* Fallback sys logs layout to maintain visual weight if idle */}
            {aiState === "IDLE" && !commandError && (
              <div className="glass-panel rounded-2xl p-5 select-none text-left relative overflow-hidden flex flex-col min-h-[170px]">
                <div className="text-[9px] font-black tracking-[0.25em] text-white/30 uppercase mb-3.5 font-mono">
                  HUD SYSTEM FEEDLOGS
                </div>
                <div className="flex-1 overflow-y-auto space-y-2 font-mono text-[10px] text-white/35 leading-normal">
                  <div className="text-emerald-500/80 font-semibold">● [OK] AUDIOCONTEXT_SYNC</div>
                  <div className="text-cyan-400/80 font-semibold">● [OK] WS_HANDSHAKE_101</div>
                  <div>○ [INFO] State listeners connected</div>
                  <div>○ [INFO] Matrix dynamic UI mapping complete</div>
                  <div className="text-white/15 animate-pulse-hud">_ Awaiting client voice / text input...</div>
                </div>
              </div>
            )}
          </section>

        </main>
        
        {/* Footer info line */}
        <footer className="flex flex-none justify-between border-t border-white/[0.04] pt-3.5 mt-4 text-[8.5px] font-mono text-white/20 uppercase tracking-widest select-none">
          <span>COGNITIVE INTERFACE MODULE</span>
          <span>SYS_FEED: SECURE_LINK</span>
          <span>© DEEPMIND ADVANCED AGENTIC CODING</span>
        </footer>

      </div>
    </div>
  );
}
