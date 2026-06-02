# FRIDAY AI Assistant - Quick Start Guide

## Prerequisites

- Windows 10/11
- Python 3.11+
- Groq API Key (get from https://console.groq.com)

## Setup Instructions

### 1. Clone/Setup Project

```bash
cd c:\FRIDAY
```

### 2. Create Virtual Environment

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. Install Dependencies

```bash
pip install -r backend\requirements.txt
```

### 4. Configure API Key

Edit `backend\.env`:

```
GROQ_API_KEY=your_api_key_here
```

**IMPORTANT**: Get your key from https://console.groq.com/keys

### 5. (Optional) Install Playwright Browsers

```bash
cd backend
..\..venv\Scripts\python.exe -m playwright install
cd ..
```

## Running FRIDAY

### Start the Assistant

```bash
cd backend
..\..venv\Scripts\python.exe main.py
```

### Expected Output

```
[STARTUP] Browser initialized
FRIDAY: FRIDAY online sir
[STARTUP] FRIDAY is ready. Say 'Friday' to wake up.
------------------------------------------------------------
[LISTENING...]
```

### Wake Up FRIDAY

Say one of these wake words:
- "Friday"
- "Hey Friday"
- "Wake up"

### Example Commands

```
"search for python tutorials on youtube"
"open spotify"
"play music"
"take screenshot"
"system status"
"lock pc"
"minimize window"
```

### Go to Sleep

Say one of these exit words:
- "Goodbye"
- "Bye"
- "Go idle"
- "Sleep"
- "Stop listening"

## Testing

Run the test suite:

```bash
cd backend
..\..venv\Scripts\python.exe test_system.py
```

Expected output: `100.0% Success Rate`

## Architecture

```
FRIDAY/
├── backend/
│   ├── voice/          # Speech recognition & TTS
│   ├── brain/          # Intent parsing & context
│   ├── browser/        # Playwright automation
│   ├── execution/      # System control & actions
│   ├── llm/            # Groq integration
│   ├── memory/         # Short/long-term memory
│   ├── config/         # Configuration
│   └── main.py         # Entry point
└── frontend/           # (React UI - future)
```

## Key Features

- ✅ Voice-first interface
- ✅ Browser automation
- ✅ System control
- ✅ Intent parsing
- ✅ Async-safe architecture
- ✅ Error handling
- ✅ Memory system

## Features Roadmap

- [ ] Persistent memory storage
- [ ] Database integration
- [ ] Multi-step workflows
- [ ] Advanced DOM interaction
- [ ] React frontend
- [ ] WebSocket real-time
- [ ] Desktop overlays
- [ ] AI orchestration

## Troubleshooting

### Issue: "No module named 'playwright'"

**Solution**: Make sure you're using the venv Python:

```bash
.venv\Scripts\python.exe -m playwright install
```

### Issue: Microphone not detected

**Solution**: Check audio settings and ensure microphone permission is granted

### Issue: API key errors

**Solution**: Verify API key in `backend\.env`

### Issue: No audio output

**Solution**: Check Windows audio settings and speaker configuration

## Performance Notes

- Speech recognition: ~10-15 second timeout
- Browser startup: ~3-5 seconds
- Intent parsing: <100ms
- LLM response: 1-3 seconds

## Security Notes

- **NEVER** commit `.env` file to git
- Regenerate API keys if exposed
- Keep `.env.example` as template

## Support

For issues:
1. Check `backend\BUG_ANALYSIS_REPORT.md` for known issues
2. Run test suite: `test_system.py`
3. Check logs in `backend\logs\`

## Next Steps

1. Get Groq API key
2. Update `.env` file
3. Install dependencies
4. Run FRIDAY
5. Explore commands

---

**Version**: 1.0  
**Last Updated**: 2026-05-11  
**Status**: Production Ready
