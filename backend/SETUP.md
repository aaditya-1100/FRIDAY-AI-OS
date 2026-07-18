# FRIDAY — Setup Guide

Quick-start for a new contributor on Windows 11.

---

## Prerequisites

- **Windows 10 / 11** (required — uses WMI, PyGetWindow, and Windows-only audio APIs)
- **Python 3.11 or 3.12** — [python.org/downloads](https://www.python.org/downloads/)
- **Node.js 18+** — [nodejs.org](https://nodejs.org/) (only needed for the Electron UI)
- **Git**

Optional (needed only for specific features):

- **Tesseract OCR** — for screen-text reading (SCREEN_READ intent)
  Install: https://github.com/UB-Mannheim/tesseract/wiki
  After install, set `TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe` in your `.env`
- **Ollama + qwen2.5-vl:7b** — for VLM screen understanding (SCREEN_DESCRIBE intent)
  ```
  winget install Ollama.Ollama
  ollama pull qwen2.5-vl:7b
  ```
- **Redis** — for session memory. If absent, FRIDAY silently falls back to SQLite.
  Install: https://github.com/microsoftarchive/redis/releases

---

## 1 — Clone

```bash
git clone https://github.com/your-username/FRIDAY.git
cd FRIDAY
```

---

## 2 — Create Python Virtual Environment

```bash
python -m venv .venv
.venv\Scripts\activate
```

---

## 3 — Install Backend Dependencies

```bash
pip install -r backend/requirements.txt
```

> The first install downloads the fastembed ONNX model (~45 MB) on first run of
> the backend, not during pip install. Subsequent starts use the cached model.

---

## 4 — Configure API Keys

Copy the example env file and fill in your keys:

```bash
copy backend\.env.example backend\.env
```

Open `backend/.env` and set:

```env
# Required
GROQ_API_KEY=gsk_...          # https://console.groq.com
TAVILY_API_KEY=tvly-...       # https://app.tavily.com

# Optional: Spotify
SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=
SPOTIFY_REDIRECT_URI=

# Optional: per-user data isolation (default is backend/data/)
FRIDAY_DATA_DIR=
```

> **Never commit `.env`** — it is in `.gitignore`.

---

## 5 — (Optional) Ollama Vision Setup

If you want "what's on my screen" to use the VLM instead of OCR:

```bash
ollama pull qwen2.5-vl:7b
```

FRIDAY auto-detects Ollama at `http://localhost:11434`. Override with `OLLAMA_HOST=` in `.env`.

---

## 6 — (Optional) Redis

If Redis is not running, session memory silently falls back to SQLite — no config needed.
To use Redis: install and start it, then set `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB` in `.env`.

---

## 7 — Run the Backend

```bash
cd backend
..\venv\Scripts\python.exe -m uvicorn api.server:app --host 127.0.0.1 --port 8001
```

Or via the helper entry point:

```bash
cd backend
..\venv\Scripts\python.exe main.py
```

The backend will log `[STARTUP] Data directory confirmed at ...` on first run.

---

## 8 — Run the Frontend

```bash
cd frontend
npm install
npm run dev
```

This starts the Electron window. The UI connects to the backend at `ws://127.0.0.1:8001`.

---

## 9 — Talk to FRIDAY

Press **Ctrl+Alt+Z** to activate voice input. Speak your command. Release to submit.

Or type in the text input box in the UI.

---

## Running Tests

```bash
cd backend
..\venv\Scripts\python.exe -m pytest -v --tb=short
```

Expected: **75 passed**.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `GROQ_API_KEY not set` | Set it in `backend/.env` |
| `Qdrant already accessed` | A previous backend instance is still running. Kill it or restart. |
| `PyAudio install fails` | Install Visual C++ Build Tools or use a pre-built wheel |
| `pytesseract not found` | Install Tesseract OCR and set `TESSERACT_CMD` in `.env` |
| `ollama connection refused` | Either start Ollama or leave it — FRIDAY falls back to OCR |
| Backend port 8001 in use | The `enforce_single_backend_instance()` auto-kills stale processes on startup |
