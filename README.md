# FRIDAY AI OS

> **A personal AI operating layer for Windows — built from scratch.**
>
> FRIDAY lets me interact with my computer through voice or text, understand what I want, decide which capability to use, execute the action, and remember useful context across sessions.

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![React](https://img.shields.io/badge/React-TypeScript-61DAFB?logo=react&logoColor=111)](https://react.dev/)
[![Electron](https://img.shields.io/badge/Electron-Desktop-47848F?logo=electron&logoColor=white)](https://www.electronjs.org/)
[![Status](https://img.shields.io/badge/status-active%20development-orange)](#project-status)

## What is FRIDAY?

FRIDAY started as a simple voice-assistant experiment and evolved into a **personal AI system that can operate a Windows desktop**.

The basic loop is:

**Hear → Understand → Plan → Execute → Respond → Remember**

Instead of building another chatbot, I focused on the orchestration layer between an AI model and a real computer: tool selection, state management, memory, safety checks, and desktop execution.

## See it in action

> **Real demos are intentionally kept here rather than simulated in the documentation.**
> Add your latest screenshots and screen-recordings to `docs/media/` and link them below.

### Demo video

`docs/media/friday-demo.mp4`  
*A short end-to-end recording showing voice input, reasoning/routing, desktop control, and the FRIDAY UI.*

### Interface

`docs/media/friday-ui.png`  
*Main FRIDAY desktop interface / orb UI.*

### Memory + tools

`docs/media/friday-memory.png`  
*Example of FRIDAY using memory or a tool-driven workflow.*

## What can it do?

| Capability | Example |
|---|---|
| **Voice interaction** | Speak to FRIDAY and receive spoken responses |
| **Desktop control** | Open apps, inspect system state, take screenshots, interact with windows |
| **Web + media** | Search the web, control browser/YouTube workflows, interact with Spotify |
| **Vision** | Analyze the current screen and extract useful visual/text context |
| **Memory** | Keep working, session, episodic, and user-profile context |
| **Real-time UI** | Stream state between Python and the Electron interface over WebSockets |

## Why I built it

I wanted to understand what it takes to turn a general-purpose language model into something that can **reliably act inside a real environment**.

The interesting part is not just the model. It is the system around it:

- **Routing:** decide what capability a request needs.
- **Orchestration:** coordinate multiple tools and agents.
- **State:** track where FRIDAY is in the interaction lifecycle.
- **Memory:** retain useful context without treating every interaction as isolated.
- **Safety:** guard destructive or sensitive actions before execution.
- **Latency:** keep the system responsive enough to feel interactive.

## Architecture at a glance

```text
User
  ↓
Voice / Text Input
  ↓
Intent + Cognitive State
  ↓
Planning / Routing
  ↓
┌────────┬────────┬────────┬────────┬────────┬────────┐
│  PC    │  Web   │ Media  │ Vision │ Memory │Knowledge│
└────────┴────────┴────────┴────────┴────────┴────────┘
  ↓
Tool Execution
  ↓
Response + UI State
  ↓
Memory Update
```

FRIDAY currently uses an **11-state cognitive flow** and separates capabilities into dedicated agent classes for PC, Web, Media, Vision, Memory, Knowledge, and Voice tasks.

## Core engineering

### Frontend

- React + TypeScript
- TailwindCSS + Framer Motion
- Electron desktop shell
- WebSockets for live state synchronization

### Backend

- Python 3.11+
- FastAPI + WebSockets
- Groq LLaMA 3.3 for intent/planning support
- Faster-Whisper for local speech-to-text
- Edge-TTS for speech output
- fastembed + embedded Qdrant for semantic memory
- pyautogui / psutil / pygetwindow for Windows interaction
- Tavily for web retrieval

### Memory

FRIDAY uses four practical memory layers:

**Working → Session → Episodic → User Profile**

Semantic retrieval is handled with embeddings and local Qdrant storage.

### Reliability and safety

The system includes capability registration, a deletion guard, explicit state transitions, deterministic routing checks, and regression/health tooling.

## Project status

**Current status: active development / public experimental release.**

The public repository represents the current implementation rather than a polished commercial product. The project has gone through several iterations focused on startup reliability, voice interaction, agent execution, memory, and reducing runtime overhead.

Recent engineering work includes:

- resolving ambient self-listening and microphone-state issues
- hardening hold-to-talk speech recognition
- reducing startup delays
- stabilizing event-bus task cancellation
- moving the embedding stack to fastembed / ONNX
- removing local databases and build artifacts from the public repository

## Performance snapshot

| Metric | R9.0 lean build |
|---|---:|
| Boot import time | ~2.0 s |
| RAM at idle boot | ~140 MB |
| RAM after first query | ~325 MB |
| Regression suite | 75 tests / 0 failing |

These figures are from the project's documented lean-build benchmark and should be treated as development measurements, not formal performance guarantees.

## Run locally

### Requirements

- Windows 10/11
- Python 3.11+
- Node.js 18+
- Tesseract OCR for screen text extraction
- API keys for the external services you choose to enable

### Backend

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r backend/requirements.txt
```

Create `backend/.env` using the provided example configuration.

### Start

```bash
cd backend
.\..\venv\Scripts\python.exe -m uvicorn api.server:app --host 127.0.0.1 --port 8001
```

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

## Repository map

```text
FRIDAY-AI-OS/
├── backend/            # AI, orchestration, memory, tools
├── frontend/           # Electron + React interface
├── docs/media/         # Screenshots and demo recordings
├── health_check.py     # Runtime health checks
├── determinism_audit.py
├── production_regression_suite_spec.md
├── ROUTING_MATRIX.md
├── CHANGELOG.md
└── README.md
```

## Roadmap

The next stage is about making FRIDAY **more reliable, more inspectable, and easier to extend** rather than simply adding more features.

- stronger tool verification and failure recovery
- better screen/vision workflows
- more robust long-term memory decisions
- cleaner desktop packaging
- improved observability and evaluation

## About the project

FRIDAY is a personal engineering project by **Aaditya Pratap Chauhan**.

It is an ongoing exploration of AI agents, computer interaction, memory systems, and the practical engineering required to make AI systems act rather than just answer.

## License

See [LICENSE](LICENSE).
