/**
 * WeatherWidget — Kashipur, Uttarakhand, India
 * Data: backend /api/weather → Open-Meteo (production-grade, no CORS risk).
 * Refreshes every 5 minutes. Hidden in map mode.
 */
import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useAtomValue } from "jotai";
import { mapModeAtom } from "../atoms";

// ── Weather icon SVGs keyed by "kind" ──────────────────────────────────────────
const WeatherIcon = ({ kind, size = 28 }: { kind: string; size?: number }) => {
  const s = size;
  const props = { width: s, height: s, viewBox: "0 0 24 24", fill: "none", strokeWidth: 1.4 };

  if (kind === "clear")
    return (
      <svg {...props}>
        <circle cx="12" cy="12" r="4" stroke="#fbbf24" fill="#fbbf2422" />
        {[0,45,90,135,180,225,270,315].map(a => (
          <line key={a} x1="12" y1="2.5" x2="12" y2="4.5"
            stroke="#fbbf24" strokeWidth="1.5" strokeLinecap="round"
            transform={`rotate(${a} 12 12)`} />
        ))}
      </svg>
    );

  if (kind === "cloudy")
    return (
      <svg {...props}>
        <path d="M6 15a3 3 0 110-6 3 3 0 116 0" stroke="#94a3b8" fill="none"/>
        <path d="M8 15h8a3 3 0 000-6c-.14 0-.27 0-.4.02A4 4 0 008 15z"
          stroke="#94a3b8" fill="#94a3b822"/>
        <circle cx="8" cy="10" r="2.5" stroke="#fbbf24" fill="#fbbf2411"/>
      </svg>
    );

  if (kind === "rain")
    return (
      <svg {...props}>
        <path d="M6 13a4 4 0 014-4h4a3 3 0 010 6H8a3 3 0 01-2-5z"
          stroke="#60a5fa" fill="#60a5fa11"/>
        <line x1="9"  y1="17" x2="8"  y2="20" stroke="#60a5fa" strokeWidth="1.5" strokeLinecap="round"/>
        <line x1="12" y1="17" x2="11" y2="20" stroke="#60a5fa" strokeWidth="1.5" strokeLinecap="round"/>
        <line x1="15" y1="17" x2="14" y2="20" stroke="#60a5fa" strokeWidth="1.5" strokeLinecap="round"/>
      </svg>
    );

  if (kind === "drizzle")
    return (
      <svg {...props}>
        <path d="M6 12a4 4 0 014-4h4a3 3 0 010 6H8a3 3 0 01-2-4z"
          stroke="#7dd3fc" fill="#7dd3fc11"/>
        <line x1="10" y1="17" x2="9"  y2="19" stroke="#7dd3fc" strokeWidth="1.2" strokeLinecap="round"/>
        <line x1="14" y1="17" x2="13" y2="19" stroke="#7dd3fc" strokeWidth="1.2" strokeLinecap="round"/>
      </svg>
    );

  if (kind === "snow")
    return (
      <svg {...props}>
        <path d="M6 12a4 4 0 014-4h4a3 3 0 010 6H8a3 3 0 01-2-4z"
          stroke="#bfdbfe" fill="#bfdbfe11"/>
        <line x1="9"  y1="17" x2="9"  y2="20" stroke="#bfdbfe" strokeWidth="1.5" strokeLinecap="round"/>
        <line x1="12" y1="17" x2="12" y2="20" stroke="#bfdbfe" strokeWidth="1.5" strokeLinecap="round"/>
        <line x1="15" y1="17" x2="15" y2="20" stroke="#bfdbfe" strokeWidth="1.5" strokeLinecap="round"/>
        <line x1="7.5" y1="18.5" x2="10.5" y2="18.5" stroke="#bfdbfe" strokeWidth="1.2" strokeLinecap="round"/>
        <line x1="10.5" y1="18.5" x2="13.5" y2="18.5" stroke="#bfdbfe" strokeWidth="1.2" strokeLinecap="round"/>
      </svg>
    );

  if (kind === "thunder")
    return (
      <svg {...props}>
        <path d="M6 11a4 4 0 014-4h4a3 3 0 010 6H8a3 3 0 01-2-4z"
          stroke="#94a3b8" fill="#94a3b811"/>
        <path d="M13 14l-2 4h3l-2 4" stroke="#fbbf24" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
      </svg>
    );

  if (kind === "fog")
    return (
      <svg {...props}>
        <line x1="5" y1="10" x2="19" y2="10" stroke="#94a3b8" strokeLinecap="round"/>
        <line x1="5" y1="13" x2="17" y2="13" stroke="#94a3b8" strokeLinecap="round"/>
        <line x1="5" y1="16" x2="15" y2="16" stroke="#94a3b8" strokeLinecap="round"/>
      </svg>
    );

  // fallback
  return <span className="text-xl">🌡️</span>;
};



const ACCENT: Record<string, string> = {
  clear:   "#fbbf24", cloudy: "#94a3b8", rain: "#60a5fa",
  drizzle: "#7dd3fc", snow: "#bfdbfe", thunder: "#a78bfa", fog: "#6b7280",
};

interface WeatherData {
  ok: boolean;
  location: string;
  temp: number;
  feels: number;
  humidity: number;
  wind: number;
  wind_dir: number;
  uv: number;
  precip: number;
  code: number;
  label: string;
  kind: string;
  sunrise: string;
  sunset: string;
  forecast: { date: string; max: number; min: number; label: string; kind: string }[];
  updated_at: string;
}

function dayName(dateStr: string, i: number) {
  if (i === 0) return "Today";
  const d = new Date(dateStr);
  return d.toLocaleDateString("en-IN", { weekday: "short" });
}

function windDirLabel(deg: number) {
  const dirs = ["N","NE","E","SE","S","SW","W","NW"];
  return dirs[Math.round(deg / 45) % 8];
}

export function WeatherWidget() {
  const mapMode = useAtomValue(mapModeAtom);
  const [data, setData]   = useState<WeatherData | null>(null);
  const [error, setError] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadRef = useRef<() => void>(() => {});

  useEffect(() => {
    const load = () =>
      fetch("http://127.0.0.1:8001/api/weather")
        .then(r => r.json())
        .then((d: WeatherData) => {
          if (d.ok) { setData(d); setError(false); }
          else setError(true);
        })
        .catch(() => setError(true));

    loadRef.current = load;
    load();
    timerRef.current = setInterval(load, 5 * 60 * 1000);
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, []);

  const show = !mapMode;
  const kind    = data?.kind ?? "clear";
  const accent  = ACCENT[kind] ?? ACCENT.clear;

  return (
    <AnimatePresence>
      {show && (
        <motion.div
          key="weather-widget"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 12 }}
          transition={{ duration: 0.35 }}
          className="w-full relative"
        >
          {/* Card */}
          <motion.div
            className="glass-panel overflow-hidden rounded-2xl cursor-pointer select-none"
            style={{
              boxShadow: `0 0 24px ${accent}12`,
            }}
            onClick={() => setExpanded(e => !e)}
            whileTap={{ scale: 0.98 }}
          >
            {/* Top accent line */}
            <motion.div
              className="absolute inset-x-0 top-0 h-px"
              style={{ background: `linear-gradient(90deg, transparent, ${accent}66, transparent)` }}
              animate={{ opacity: [0.5, 1, 0.5] }}
              transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
            />

            {/* Loading state */}
            {!data && !error && (
              <div className="flex items-center justify-center py-8">
                <motion.div
                  className="h-5 w-5 rounded-full border-2 border-white/10 border-t-white/50"
                  animate={{ rotate: 360 }}
                  transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
                />
              </div>
            )}

            {/* Error state */}
            {error && (
              <div className="px-4 py-5 text-center cursor-pointer" onClick={() => { setError(false); loadRef.current(); }}>
                <p className="text-[10px] text-white/30">Weather unavailable</p>
                <p className="text-[9px] text-white/15 mt-1">Tap to retry</p>
              </div>
            )}

            {/* Data */}
            {data && !error && (
              <div className="px-3.5 pt-3 pb-3">
                {/* Location */}
                <div className="flex items-center justify-between mb-2">
                  <p className="text-[8px] font-black tracking-[0.28em] uppercase"
                    style={{ color: `${accent}88` }}>
                    {data.location.split(",")[0]}
                  </p>
                  <p className="text-[8px] text-white/20 font-mono">{data.updated_at}</p>
                </div>

                {/* Main row: temp + icon */}
                <div className="flex items-end justify-between mb-1">
                  <div>
                    <span className="text-[34px] font-bold text-white leading-none tracking-tight">
                      {data.temp}
                    </span>
                    <span className="text-sm text-white/40 ml-0.5">°C</span>
                  </div>
                  <motion.div
                    animate={{ y: [0, -2, 0] }}
                    transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
                    className="mb-1"
                  >
                    <WeatherIcon kind={kind} size={30} />
                  </motion.div>
                </div>

                {/* Condition */}
                <p className="text-[11px] font-medium mb-3" style={{ color: `${accent}cc` }}>
                  {data.label}
                </p>

                {/* Stats grid */}
                <div className="grid grid-cols-2 gap-x-2 gap-y-1.5 mb-3">
                  <MiniStat label="Feels like" value={`${data.feels}°C`} accent={accent} />
                  <MiniStat label="Humidity"   value={`${data.humidity}%`} accent={accent} />
                  <MiniStat label="Wind"       value={`${data.wind} ${windDirLabel(data.wind_dir)}`} accent={accent} />
                  <MiniStat label="UV Index"   value={`${data.uv}`} accent={accent} />
                </div>

                {/* Sunrise / Sunset */}
                <div className="flex justify-between mb-2.5">
                  <div className="flex items-center gap-1">
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#fbbf24" strokeWidth="2" strokeLinecap="round">
                      <path d="M12 2v4M4.93 7.93l2.83 2.83M2 15h4M20 15h4M16.24 10.76l2.83-2.83M17 15a5 5 0 10-10 0"/>
                      <line x1="3" y1="19" x2="21" y2="19"/>
                    </svg>
                    <span className="text-[9px] text-white/40 font-mono">{data.sunrise}</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#f97316" strokeWidth="2" strokeLinecap="round">
                      <path d="M12 10v4M4.93 16.07l2.83-2.83M2 9h4M20 9h4M16.24 13.24l2.83 2.83M17 9a5 5 0 10-10 0"/>
                      <line x1="3" y1="5" x2="21" y2="5"/>
                    </svg>
                    <span className="text-[9px] text-white/40 font-mono">{data.sunset}</span>
                  </div>
                </div>

                {/* Divider */}
                <div className="h-px mb-2" style={{ background: `${accent}22` }} />

                {/* 3-day forecast */}
                <AnimatePresence>
                  {expanded && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: "auto", opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.25 }}
                      className="overflow-hidden"
                    >
                      <div className="flex flex-col gap-1.5 mb-2">
                        {data.forecast.map((f, i) => (
                          <div key={f.date} className="flex items-center justify-between">
                            <span className="text-[9px] text-white/40 w-8">{dayName(f.date, i)}</span>
                            <WeatherIcon kind={f.kind} size={13} />
                            <span className="text-[9px] text-white/60 ml-auto">{f.min}°</span>
                            <div className="mx-1.5 h-1 w-10 rounded-full overflow-hidden bg-white/10">
                              <div className="h-full rounded-full"
                                style={{ width: "60%", background: accent, opacity: 0.6 }} />
                            </div>
                            <span className="text-[9px] text-white/80">{f.max}°</span>
                          </div>
                        ))}
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>

                {/* Expand hint */}
                <div className="flex justify-center">
                  <motion.div
                    animate={{ y: expanded ? -1 : 1 }}
                    transition={{ duration: 0.2 }}
                  >
                    <svg width="10" height="6" viewBox="0 0 10 6" fill="none">
                      <path d={expanded ? "M1 5l4-4 4 4" : "M1 1l4 4 4-4"}
                        stroke={`${accent}66`} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                  </motion.div>
                </div>
              </div>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function MiniStat({ label, value, accent }: { label: string; value: string; accent: string }) {
  return (
    <div>
      <p className="text-[8px] uppercase tracking-wider" style={{ color: `${accent}55` }}>{label}</p>
      <p className="text-[11px] font-semibold text-white/75">{value}</p>
    </div>
  );
}
