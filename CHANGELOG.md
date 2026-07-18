# Changelog

All notable changes to FRIDAY are documented here.
Format: [Version] — [Date] — [Summary]

---

## [R9.0] — 2026-07-12 — Lean Build: Simplification & Bug Fix

### Overview
Major simplification pass. Removed all experimental subsystems that were not
delivering user-facing value. Result: **2s boot, 140 MB RAM (idle) / 325 MB (active)** (down from ~12s and ~800 MB).

---

### Stripped (moved to `backend/experimental/`)

These subsystems were built for a research/experimental track and are no longer
imported by any live code path. They remain in `experimental/` for reference.

| Subsystem | File(s) | Reason |
|-----------|---------|--------|
| MEP Confidence Engine | `brain/confidence_engine.py` | Over-engineered scoring — not used |
| MEP Trigger Intelligence | `brain/trigger_intelligence.py` | `trigger_reliability.json` — not live |
| MEP Conflict Engine | `brain/conflict_engine.py` | Never wired to request path |
| MEP Behavior Contract | `brain/behavior_contract.py` | Complexity without value |
| MEP Routing Telemetry | `brain/routing_telemetry.py` | `routing_telemetry.db` — not live |
| Personalization Engine | `brain/personalization_engine.py` | Not user-facing |
| Behavioral Signal Registry | `brain/behavioral_signal_registry.py` | Depends on above |
| Semantic Taxonomy | `brain/semantic_taxonomy.py` | Dead code in entity tracker |
| ONNX Biencoder | `brain/onnx_biencoder.py` | Replaced by fastembed |
| spaCy Loader | `brain/spacy_loader.py` | spaCy fully removed |
| Schedulers | `core/schedulers/` | No live consumer |
| Legacy memory package | `memory/` (bare) | All imports use `friday.memory.*` |
| Legacy pipeline | `core/pipeline.py` | Replaced by FSM event bus |
| Knowledge Graph | `friday/memory/knowledge_graph.py` | No live import |
| Consolidation | `friday/memory/consolidation.py` | No live import |
| Spotify Client (duplicate) | `system/spotify_client.py` | Duplicate of `friday/agents/media_agent.py` |

### Embedding Stack Replaced

| Before | After |
|--------|-------|
| `sentence-transformers` + PyTorch (~500 MB) | `fastembed` 0.5.1 (ONNX, ~45 MB) |
| Loaded at import time | Lazy-loaded on first query |

Packages removed from `requirements.txt`: `sentence-transformers`, `torch`, `onnxruntime`, `tokenizers`, `playwright`, `spacy`.

---

### Bugs Fixed (6 confirmed live failures)

| ID | Description | File |
|----|-------------|------|
| C1 | `CognitiveFSM.current_state` AttributeError on cold start causing notch to show wrong state | `friday/core/fsm.py` |
| C2 | Qdrant client not explicitly closed on shutdown → file lock held across restarts | `friday/memory/semantic.py` |
| C3 | Zombie port 8001: duplicate backend processes not killed on startup | `api/server.py` — `enforce_single_backend_instance()` |
| C4 | Hotkey race: `GetAsyncKeyState` busy-poll caused Ctrl+Alt+Z to double-fire | `voice/listen.py` — hold-to-talk architecture |
| C5 | SAPI5 (pyttsx3) initialised at module import instead of first use, blocking boot | `voice/speak.py` — lazy init |
| C6 | ProactiveEngine fired during boot grace period, changing FSM state before first interaction | `friday/core/proactive_engine.py` — 60s `_startup_time` guard |

---

### Performance

| Metric | R8.x | R9.0 |
|--------|------|------|
| Boot import time | ~12s | **2.0s** |
| RAM (full stack) | ~800 MB | **140 MB (Idle)**<br>**325 MB (Active)** |
| Embedding model size | ~500 MB (PyTorch) | **~45 MB (ONNX)** |
| Test suite | 78 tests, 15 failing | **75 tests, 0 failing** |

---

### Breaking Changes

**None for fresh installs.**

For existing installs upgrading from R8.x:
- `FRIDAY_QDRANT_PATH` env var still works (backward compatible)
- The `data/knowledge_graph.db` file may remain on disk but is never written to
- 3 tests were deleted (covered stripped subsystems): `test_knowledge_graph_population`, `test_scheduler_tick`, `test_llm_synthesizing`

---

## [R9.1] — 2026-07-18 — GitHub Deploy Readiness + Vision Quality

### Per-User Data Isolation (G1)

Added `backend/config/paths.py` — a central data directory resolver.
All 6 live data stores now route through `get_data_path()`:

- `friday/memory/session.py` — `session_fallback.db`
- `friday/memory/semantic.py` — `qdrant/`
- `friday/memory/episodic.py` — `episodic.db`
- `friday/memory/user_profile.py` — `user_profile.db`
- `brain/project_manager.py` — `projects/project_registry.json`
- `friday/agents/vision_agent.py` — `screenshots/`

Set `FRIDAY_DATA_DIR` in `.env` to point each user's install at its own subdirectory.
Default is `backend/data/` — no migration required for existing installs.

### .gitignore Hardening (G2)

- Root `.gitignore`: added `backend/data/`, `backend/logs/`, `logs/`, `frontend/node_modules/`
- `backend/.gitignore`: added `data/`, `friday_backend.pid`, `friday_runtime.log`

### First-Run Bootstrap (G3)

`api/server.py` lifespan now calls `ensure_data_dirs()` on startup.
Creates `qdrant/`, `screenshots/`, `projects/` subdirs automatically.
No manual `mkdir` required after a fresh clone.

### Documentation

- `backend/SETUP.md` — new contributor quickstart (prerequisites through first run)
- `CHANGELOG.md` — this file

### Vision Quality (V2 + V3)

Improved `screen_reader.describe_screen()` in `friday/vision/screen_reader.py`:
- Separated system prompt from user query
- User's actual question is now passed to the VLM for context
- Explicit voice-readability instructions (no markdown, max 3 sentences)
- Added `vision_response_formatter()` in `friday/agents/vision_agent.py`
  — strips markdown, removes "I can see" openers, normalises `%`/`&`, truncates to 3 sentences

### Breaking Changes

None.
