# FRIDAY AI OS

> ## An Agentic AI Operating Layer for Real-World Computer Interaction
>
> FRIDAY is an experimental AI agent platform that connects language models to a real Windows environment through **perception, stateful reasoning, tool orchestration, computer control, and persistent memory**.

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![React](https://img.shields.io/badge/React-TypeScript-61DAFB?logo=react&logoColor=111)](https://react.dev/)
[![Electron](https://img.shields.io/badge/Electron-Desktop-47848F?logo=electron&logoColor=white)](https://www.electronjs.org/)
[![Status](https://img.shields.io/badge/status-active%20development-orange)](#project-status)

## The idea

Most AI interfaces stop at generating an answer.

FRIDAY explores the next layer: **how an AI system can move from understanding an instruction to operating inside a real environment.**

The system is built around a continuous control loop:

**Perceive → Interpret → Plan → Delegate → Execute → Synthesize → Reflect**

A language model provides reasoning capability, but FRIDAY is the surrounding system that gives that reasoning access to a computer.

## Interaction model

FRIDAY is designed to stay **out of the way of the user's work**.

It does not open a full assistant window, live in the taskbar, or use a wake word. Instead, it appears as a narrow, pill-shaped **floating island at the top-center of the screen**, directly beneath the camera/notch area on a modern laptop. It acts as a compact status and interaction surface rather than demanding focus.

### Push-to-talk, by design

FRIDAY uses a deliberate **walkie-talkie interaction model**:

**Hold `Ctrl + Alt + Z` → speak → release → FRIDAY processes the turn.**

The microphone is only active while the hotkey is held. There is no passive background listening in the normal interaction flow.

This design gives the user explicit control over microphone activation and avoids treating connectivity or application startup as permission to listen.

### What happens during a turn

When the hotkey is held, the floating island indicates that FRIDAY is actively listening. When the key is released, the system moves through its processing stages and returns to idle after responding.

The interaction pipeline is:

1. **Listen** — capture the user's voice while push-to-talk is held.
2. **Transcribe** — process speech locally with Faster-Whisper.
3. **Interpret** — determine whether the request is a question, command, memory lookup, or system action.
4. **Plan / route** — use deterministic routing where appropriate and LLM-assisted reasoning where ambiguity requires it.
5. **Execute** — delegate work to the relevant agent and tools.
6. **Respond** — synthesize the result and speak it back with Edge-TTS.
7. **Reflect / remember** — update relevant interaction state and memory.

The UI is intentionally minimal: no modal workflow, no full-screen takeover, and no requirement to leave the application currently in use.

## What FRIDAY can do from that interface

From a single deliberate push-to-talk interaction, FRIDAY can:

- answer questions using live web retrieval or stored context
- control supported media workflows such as Spotify
- capture and analyze screenshots
- read and locate text on the current screen
- open applications and interact with Windows resources
- work with files and system information through guarded tool paths
- retrieve relevant information from semantic and episodic memory
- surface passive/proactive information through the floating island without turning every event into a spoken interruption

FRIDAY is designed around the idea that **the computer itself is part of the environment the agent observes and acts within**.

## What FRIDAY actually is

FRIDAY is not designed as a single monolithic chatbot. It is a small **agent runtime** with explicit state, asynchronous event routing, specialized agents, tool permissions, and memory services.

At the center is a cognitive state machine with explicit transitions such as:

```text
IDLE
  ↓
PERCEIVING
  ↓
PLANNING
  ↓
DELEGATING
  ↓
WAITING
  ↓
SYNTHESIZING
  ↓
RESPONDING
  ↓
REFLECTING
  ↓
IDLE
```

Interruptions and failures are modeled explicitly rather than treated as ordinary responses.

## System architecture

```text
                     ┌──────────────────────────────┐
                     │ Push-to-Talk / Text Input     │
                     │      Ctrl + Alt + Z          │
                     └──────────────┬───────────────┘
                                    ↓
                     ┌──────────────────────────────┐
                     │         Perception           │
                     │  STT + Screen/OCR Context   │
                     └──────────────┬───────────────┘
                                    ↓
                     ┌──────────────────────────────┐
                     │        Cognitive Core        │
                     │  State + Planning + Context  │
                     └──────────────┬───────────────┘
                                    ↓
                     ┌──────────────────────────────┐
                     │  Event Bus / Task Dispatch   │
                     │   Priority + Correlation     │
                     └──────────────┬───────────────┘
                                    ↓
       ┌───────────┬───────────┬────┴────┬───────────┬──────────┬───────────┐
       ↓           ↓           ↓         ↓           ↓          ↓           ↓
      PC          Web        Media     Vision      Memory   Knowledge     Voice
     Agent       Agent       Agent      Agent       Agent      Agent      Agent
       └───────────┴───────────┴────┬────┴───────────┴──────────┴───────────┘
                                    ↓
                          ┌──────────────────────┐
                          │ Permissions + Safety │
                          └──────────┬───────────┘
                                     ↓
                          ┌──────────────────────┐
                          │  Windows / Web / UI  │
                          └──────────┬───────────┘
                                     ↓
                             Result + New Context
                                     ↓
                            Memory / UI Feedback
```

## The important engineering pieces

### 1. Cognitive state and control flow

FRIDAY uses an explicit state machine instead of a single request/response function. Each transition is validated, logged, associated with a correlation ID, and published through the event system.

This gives the system a concrete representation of **where an interaction is, what it is doing, and how it can recover or be interrupted**.

### 2. Event-driven orchestration

Agents communicate through a priority-aware asynchronous event bus. Events carry session IDs, correlation IDs, sources, priorities, and structured payloads.

The bus supports wildcard subscriptions and concurrent delivery, allowing the cognitive layer and specialized agents to remain decoupled.

### 3. Specialized agents

FRIDAY currently separates responsibilities into seven agents:

- **PC** — Windows, applications, files, system operations
- **Web** — browser interaction and web workflows
- **Media** — media and playback control
- **Vision** — screenshot reading, OCR, screen description, screen targeting
- **Memory** — storing and retrieving contextual information
- **Knowledge** — knowledge-oriented tasks and retrieval
- **Voice** — speech input/output lifecycle

Each agent follows a common lifecycle, declares capabilities, processes dispatched tasks, reports structured results, and emits health/heartbeat events.

### 4. Perception and computer vision

FRIDAY can capture the current screen and turn it into machine-usable context.

Its vision layer supports operations such as:

- structured screen reading
- OCR-based text extraction
- finding text on screen
- screen description
- screenshot capture
- visual understanding
- locating UI targets for computer interaction

This makes the computer an environment FRIDAY can **observe**, not merely a set of APIs it can call.

### 5. Persistent memory

FRIDAY's memory is more than conversation history.

The architecture combines working/session context with semantic and episodic retrieval. Semantic memory uses embeddings with local Qdrant storage, while the cognitive layer can retrieve relevant memory under a latency budget before planning a response or action.

The practical goal is simple: **do not force every interaction to start from zero.**

### 6. Safety and authorization

Giving an AI access to a computer requires more than tool availability.

FRIDAY includes agent trust levels and a permission engine that maps tools to permission requirements. Sensitive operations can trigger a human-confirmation flow, while denied operations are audit-logged rather than silently executed.

The intended model is:

**Capability ≠ unrestricted authority.**

### 7. Stateful context

The cognitive layer assembles context from multiple sources when needed:

- current system state
- active application/window
- screen context
- tool results
- semantic memory
- recent episodic context
- recent conversation turns

This context is then supplied to the reasoning layer with explicit budget management and truncation rules.

## What the system can currently do

| Layer | Current capability |
|---|---|
| **Perception** | Push-to-talk voice input, text input, screenshots, OCR, screen understanding |
| **Reasoning** | Intent parsing, LLM-assisted planning, stateful response synthesis |
| **Orchestration** | Event routing, task dispatch, priorities, correlation tracking |
| **Computer use** | Application control, files, screenshots, system information, browser interaction |
| **Vision** | Screen reading, text finding, screen description, visual target detection |
| **Memory** | Session context, semantic retrieval, episodic retrieval |
| **Safety** | Trust levels, permission policies, human confirmation, audit logging |
| **Interface** | Electron + React desktop UI with a top-center floating interaction surface |

## Technology

### Runtime

- Python 3.11+
- `asyncio`
- FastAPI / Uvicorn
- WebSockets
- Event-driven internal architecture

### Intelligence

- Groq-hosted LLaMA 3.3 for LLM inference
- Faster-Whisper for speech recognition
- Edge-TTS for speech synthesis
- fastembed with `BAAI/bge-small-en-v1.5`
- embedded Qdrant for vector retrieval
- optional Ollama vision models

### Computer interaction

- `pyautogui`
- `psutil`
- `pygetwindow`
- browser automation tooling
- Tesseract OCR

### Interface

- React
- TypeScript
- TailwindCSS
- Framer Motion
- Electron

## Why the interface is deliberately minimal

FRIDAY is designed to sit **alongside work, not on top of it**.

The floating island occupies a small strip of otherwise unused screen space. Push-to-talk makes activation explicit. Voice input and voice output keep the user's hands available for whatever they are already doing.

The design goal is not to make the assistant the center of attention. It is to make AI capability **immediately available without demanding focus**.

## Reliability engineering

FRIDAY has gone through multiple iterations focused less on adding features and more on making the runtime behave predictably.

Recent work includes:

- fixing ambient self-listening and microphone-state synchronization
- hardening hold-to-talk speech recognition
- removing startup-time microphone activation
- reducing startup latency
- stabilizing asynchronous task cancellation
- moving semantic embeddings to the lighter fastembed / ONNX stack
- removing local databases and release artifacts from the public repository
- maintaining regression, health, routing, and determinism checks

## Performance snapshot

The repository's documented R9.0 lean-build measurements report:

| Metric | Measurement |
|---|---:|
| Boot import time | ~2.0 s |
| RAM at idle boot | ~140 MB |
| RAM after first query | ~325 MB |
| Regression suite | 75 tests / 0 failing |

These are development measurements from the project, not independent benchmarks or production guarantees.

## Project status

**Active development / experimental public release.**

FRIDAY is intentionally a systems experiment rather than a finished commercial product. The repository is used to explore the engineering problems around agentic computer interaction: control flow, tool orchestration, perception, memory, permissions, latency, reliability, and recovery.

## What I am exploring

The central question behind the project is:

> **What software architecture is needed for an AI system to reliably act in a real computer environment rather than only generate text?**

That question naturally connects FRIDAY to broader areas of AI engineering:

- agentic systems
- human-computer interaction
- multimodal perception
- computer use
- memory architectures
- tool-using language models
- autonomous robotics and embodied AI

## Repository structure

```text
FRIDAY-AI-OS/
├── backend/
│   ├── friday/
│   │   ├── agents/          # Specialized execution agents
│   │   ├── core/            # Cognitive state + event system
│   │   ├── memory/          # Context and semantic retrieval
│   │   ├── security/        # Capability + permission controls
│   │   ├── vision/          # Screen perception
│   │   └── system/          # Environment and OS integration
│   ├── tests/               # Regression and behavior tests
│   └── requirements.txt
├── frontend/                # React + Electron interface
├── health_check.py          # Runtime health checks
├── determinism_audit.py
├── production_regression_suite_spec.md
├── ROUTING_MATRIX.md
├── CHANGELOG.md
└── README.md
```

## Run locally

### Requirements

- Windows 10/11
- Python 3.11+
- Node.js 18+
- Tesseract OCR
- API keys for the optional cloud services you enable

### Backend

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r backend/requirements.txt
```

Create `backend/.env` using the provided example configuration.

Start the backend:

```bash
cd backend
..\venv\Scripts\python.exe -m uvicorn api.server:app --host 127.0.0.1 --port 8001
```

Start the interface separately:

```bash
cd frontend
npm install
npm run dev
```

## Roadmap

The next phase is focused on **reliability, evaluation, and deeper environmental understanding** rather than simply adding more commands.

- stronger action verification and recovery
- more robust screen/vision interaction
- better uncertainty handling around tool results and memory
- improved observability and evaluation harnesses
- cleaner desktop packaging and deployment

## Author

**Aaditya Pratap Chauhan**

FRIDAY is a long-running personal engineering project exploring the boundary between language models and real-world computer interaction.

## License

See [LICENSE](LICENSE).
