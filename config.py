"""
JARVIS — Configuration
All environment variables, constants, and paths in one place.

Built from CLAUDE.md by RJ - https://itsbrook.com
"""

import os

# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------
OLLAMA_BASE: str = os.getenv("OLLAMA_BASE", "http://localhost:11434")
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "glm-5.1:cloud")

# Cloud fallback (OpenRouter)
OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL: str = os.getenv("OPENROUTER_MODEL", "google/gemini-2.0-flash-001")

# ---------------------------------------------------------------------------
# TTS
# ---------------------------------------------------------------------------
VOICEBOX_URL: str = os.getenv("VOICEBOX_URL", "http://localhost:17493")
VOICEBOX_PROFILE: str = os.getenv("VOICEBOX_PROFILE", "35ec6078-2f64-463c-aa02-77e4e4ade095")

# ---------------------------------------------------------------------------
# Memory / Storage
# ---------------------------------------------------------------------------
PB_BASE: str = os.getenv("PB_BASE", "http://localhost:8090")
PB_USER: str = os.getenv("PB_USER", "jarvis")
PB_PASS: str = os.getenv("PB_PASS", "jarvis123")

# Obsidian vault
VAULT_DIR: str = os.getenv("VAULT_DIR", os.path.expanduser("~/.openclaw/workspace/vault"))

# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------
BACKEND_PORT: int = int(os.getenv("BACKEND_PORT", "8444"))
FRONTEND_PORT: int = int(os.getenv("FRONTEND_PORT", "3002"))
MAX_CONTEXT: int = int(os.getenv("MAX_CONTEXT", "10"))

# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------
SERPER_API_KEY: str = os.getenv("SERPER_API_KEY", "")
OPENCLAW_URL: str = os.getenv("OPENCLAW_URL", "http://localhost:4152")
DUCKDUCKGO_URL: str = "https://api.duckduckgo.com/"

# ---------------------------------------------------------------------------
# Chat / Telegram
# ---------------------------------------------------------------------------
TELEGRAM_CHAT_ID: str = "-1003471219808"
TOPIC_BLACKWIDOW: int = 26
TOPIC_RUFLO: int = 23
TOPIC_JARVIS: int = 19

# Telegram relay via OpenClaw
OPENCLAW_TELEGRAM_TOPIC: int = 19  # 🤖 Jarvis topic

# ---------------------------------------------------------------------------
# Attribution
# ---------------------------------------------------------------------------
ATTRIBUTION: str = "Built from CLAUDE.md by RJ - https://itsbrook.com"