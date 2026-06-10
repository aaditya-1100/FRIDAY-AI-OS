import { Canvas } from "@react-three/fiber";
import { motion, AnimatePresence } from "framer-motion";
import { useAtom, useAtomValue } from "jotai";
import { Suspense, useEffect, useState } from "react";
import { aiStateAtom, commandErrorAtom, wsConnectedAtom, mapModeAtom, mapLocationAtom, mapLatAtom, mapLonAtom, type AiState } from "./atoms";
import { MicButton } from "./components/MicButton";
import { ParticleOrb } from "./components/ParticleOrb";
import { RemindersPanel, ReminderToastOverlay } from "./components/RemindersPanel";
import { useFridaySocket } from "./hooks/useFridaySocket";

function statusFor(state: AiState, connected: boolean, err: string | null) {
  if (err) return err;
  if (!connected) return "Waiting for server…";
  switch (state) {
    case "LISTENING":
    case "PERCEIVING":
      return "Listening";
    case "THINKING":
    case "SYNTHESIZING":
      return "Thinking";
    case "EXECUTING":
    case "PLANNING":
    case "DELEGATING":
      return "Working";
    case "SPEAKING":
    case "RESPONDING":
      return "Speaking";
    case "WAITING":
      return "Waiting";
    case "REFLECTING":
      return "Reflecting";
    case "INTERRUPTED":
      return "Interrupted";
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
  const mapLat = useAtomValue(mapLatAtom);
  const mapLon = useAtomValue(mapLonAtom);
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

                // Premium dark-themed Leaflet.js tactical map template (completely bypasses iframe restrictions)
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
    /* Holographic dark cyan theme filter on basemap tiles */
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
                    {/* Map iframe zooms in from 1.15 */}
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

                    {/* HUD Header */}
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

                    {/* Bottom HUD */}
                    <div className="pointer-events-none absolute inset-x-0 bottom-5 flex justify-center">
                      <span className="text-[9px] font-mono tracking-widest text-cyan-400/35">SYS:MAPLINK ● ENCRYPTED ● LIVE FEED</span>
                    </div>
                  </motion.div>
                );
              })()}
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




      {/* Reminder Toast — top center notification */}
      <ReminderToastOverlay />

      {/* Reminder/Timer/Alarm live panel — bottom right */}
      <RemindersPanel />

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
        <div className="w-[300px] sm:w-[380px] md:w-[500px]" style={{ width: "min(100%, 100vh - 220px)", aspectRatio: "1 / 1" }}>
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
