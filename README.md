# FRIDAY AI

FRIDAY is a fast, lean local AI voice assistant built with Python, React, Electron, and WebSockets.
Responds to voice or text commands with real-time intent routing, screen awareness, and persistent memory.
Inspired by JARVIS — minimal latency, no cloud dependency for core execution.

---

# Features

* Real-time voice interaction (Faster-Whisper STT + Edge-TTS)
* Smart intent understanding (11-state FSM + Groq LLaMA 3.3)
* System & app control (open apps, screenshots, system status)
* Browser + YouTube control
* Spotify OAuth2/PKCE integration
* WebSocket-based real-time state sync
* Orb-based immersive UI (React + Electron)
* Working / session / episodic / user-profile memory (4-layer)
* Semantic memory via fastembed + Qdrant embedded
* Live web search (Tavily + Serper)
* Screen-awareness via vision pipeline

---

# Tech Stack

## Frontend

* React + TypeScript
* TailwindCSS + Framer Motion
* Electron
* WebSockets

## Backend

* Python 3.11+
* FastAPI / WebSockets (uvicorn)
* Groq API — llama-3.3-70b-versatile
* Faster-Whisper base.en (local STT)
* Edge-TTS (en-IN-NeerjaNeural)
* fastembed (BAAI/bge-small-en-v1.5) + Qdrant embedded
* Tavily web search
* pyautogui / psutil / pygetwindow

---

# Architecture

* 11-state CognitiveFSM (IDLE → LISTENING → PLANNING → EXECUTING → RESPONDING…)
* 7 agent classes: PC, Web, Media, Vision, Memory, Knowledge, Voice
* Event-bus async architecture (publish/subscribe)
* 4-layer memory: working → session → episodic → user profile
* Deletion guard + capability registry (security layer)

---

# Setup & Installation

## Prerequisites

* **OS**: Windows 10/11 (required for window management, PyGetWindow, and WMI controls)
* **Python**: 3.11+
* **Node.js**: 18+ (for frontend)
* **Tesseract OCR**: Required for vision/screenshot text extraction
  Install from: https://github.com/tesseract-ocr/tesseract
* **Optional**: [Ollama](https://ollama.com/) for enhanced local vision (`qwen2.5-vl:7b`)
* **Optional**: Redis (auto-falls back to local SQLite if not running)

## Installation Guide

1. **Clone the project**:
   ```bash
   cd c:\FRIDAY
   ```

2. **Create and activate a Python virtual environment**:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   ```

3. **Install backend dependencies**:
   ```bash
   pip install -r backend/requirements.txt
   ```

4. **Configure API keys** — create `backend/.env` (see `backend/.env.example`):
   ```env
   GROQ_API_KEY=your_groq_api_key_here
   TAVILY_API_KEY=your_tavily_search_key_here
   SPOTIFY_CLIENT_ID=your_spotify_client_id
   SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
   ```

5. **Qdrant (Embedded Mode)** — no install needed:
   FRIDAY uses Qdrant in local embedded mode (`QdrantClient(path=...)`).
   Collections are stored under `backend/data/qdrant/`. No Docker or port 6333 required.

## Running FRIDAY

### Start Backend
```bash
cd backend
.\..\venv\Scripts\python.exe -m uvicorn api.server:app --host 127.0.0.1 --port 8001
```

### Start Frontend UI
```bash
cd frontend
npm install
npm run dev
```

## Testing

Run the full test suite (75 tests):
```bash
cd backend
..\venv\Scripts\python.exe -m pytest -v --tb=short
```

---

# Performance (R9.0 Lean Build)

| Metric | R8.x | R9.0 |
|--------|------|------|
| Boot import time | ~12s | **2.0s** |
| RAM (full stack) | ~800 MB | **140 MB (Idle at boot)**<br>**325 MB (Active after first query)** |
| Embedding stack | PyTorch + sentence-transformers | **fastembed** (ONNX, no GPU required) |
| Test suite | 78 tests (15 failing) | **75 tests, 0 failing** |

---

# Known Limitations

> [!NOTE]
> **Per-User Data Isolation**:
> FRIDAY supports multi-tenant or multi-developer data isolation. Set the `FRIDAY_DATA_DIR` environment variable in `backend/.env` to isolate user profiles, databases, screenshots, and active project files to a specific subdirectory.

> [!NOTE]
> **Groq Daily Quota**: The free tier of Groq API has a 100k token/day limit.
> FRIDAY handles quota exhaustion gracefully with a keyword-fallback intent parser.
> All system-control intents (open apps, screenshots, media control) continue working without Groq.

---

# Disclaimer

This project is an experimental personal AI assistant under active development.
Designed and built for personal use on a single Windows machine.

---

# Author

Aaditya Pratap Chauhan
