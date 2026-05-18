# JARVIS — Voice-First AI Assistant for macOS

> *"At your service, sir."*

Built from CLAUDE.md by RJ - https://itsbrook.com

## Overview

JARVIS is a voice-first AI assistant with a British butler personality, running locally on macOS. It features a real-time Three.js particle orb that responds to audio and sentiment, powered by local LLM inference via Ollama.

## Architecture

| Layer | Tech |
|-------|------|
| Backend | FastAPI + Python (server.py) |
| Frontend | Vite + TypeScript + Three.js |
| Communication | WebSocket (JSON messages + base64 binary audio) |
| AI (primary) | Ollama glm-5.1:cloud (local, offline-capable) |
| TTS | Voicebox (kokoro, am_onyx) at localhost:17493 |
| TTS fallback | macOS `say` |
| Wake word | "Hey Jarvis" / "Jarvis" via openWakeWord |
| System | AppleScript for macOS integrations |
| Storage | Pocketbase v0.38.1 (port 8090) |
| Orb | Three.js particle system with sentiment colors |

## Quick Start

### Prerequisites

- Python 3.13+
- Node.js 20+
- [Ollama](https://ollama.ai) running locally
- [Voicebox](https://github.com/anthropics/voicebox) (optional, for TTS)
- Pocketbase v0.38.1 (optional, for persistent memory)

### Backend

```bash
cd jarvis
pip install -r requirements.txt
python server.py
```

Server runs on port **8444**.

### Frontend

```bash
cd jarvis/frontend
npm install
npm run dev
```

Frontend runs on port **3002**.

### Docker

```bash
docker compose up
```

## Features

- 🎤 **Voice-first interaction** — Push to talk or wake word
- 🧠 **Local LLM** — Ollama glm-5.1:cloud, no external API calls
- 🔊 **TTS pipeline** — Voicebox primary, macOS say fallback
- 🌐 **Three.js orb** — Audio-reactive particles with sentiment colors
- 💾 **Persistent memory** — Pocketbase-backed conversation history
- 📅 **macOS integrations** — Calendar, Mail, Notes via AppleScript
- 🌍 **Web browsing** — Playwright-based, all local
- 🔧 **System control** — Volume, brightness, apps via AppleScript
- 🛡️ **Privacy-first** — Everything runs locally, no data leaves your machine

## Orb Sentiment Colors

| Sentiment | Color |
|-----------|-------|
| Positive | 🟢 Green |
| Neutral | 🔵 Blue |
| Negative | 🔴 Red |
| Thinking | 🟡 Yellow |
| Listening | 🟢 Green |

## API Endpoints

- `GET /health` — Health check
- `GET /status` — Service status (Ollama, Voicebox, sessions)
- `GET /history/{session_id}` — Conversation history
- `WS /ws` — WebSocket for bidirectional audio + JSON

## WebSocket Messages

### Client → Server

```json
{"type": "transcript", "text": "Hello Jarvis"}
{"type": "interrupt"}
{"type": "ping"}
{"type": "get_history"}
```

Binary audio data (for STT) is also accepted.

### Server → Client

```json
{"type": "state", "state": "thinking", "sentiment": "neutral"}
{"type": "text_chunk", "text": "Good "}
{"type": "text_chunk", "text": "evening, sir."}
{"type": "audio_start", "sentiment": "positive"}
{"type": "audio_end"}
{"type": "interrupted"}
{"type": "error", "message": "..."}
```

## License

MIT

---

*Built from CLAUDE.md by RJ - https://itsbrook.com*