"""
JARVIS — Voice-First AI Assistant for macOS
FastAPI main server with WebSocket, Ollama LLM, TTS, and STT pipelines.

Built from CLAUDE.md by RJ - https://itsbrook.com
"""

import asyncio
import json
import logging
import time
import uuid
from pathlib import Path
from typing import Optional

import httpx
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import (
    OLLAMA_BASE, OLLAMA_MODEL, OPENROUTER_API_KEY, OPENROUTER_MODEL,
    VOICEBOX_URL, VOICEBOX_PROFILE, PB_BASE,
    BACKEND_PORT, FRONTEND_PORT, MAX_CONTEXT,
    SERPER_API_KEY, OPENCLAW_URL, DUCKDUCKGO_URL,
    ATTRIBUTION,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("jarvis")

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="JARVIS", version="0.1.0", description=ATTRIBUTION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# In-memory context store (per-session)
# ---------------------------------------------------------------------------
sessions: dict[str, dict] = {}  # session_id -> {context: [...], state: str}

from llm import ollama_chat, ollama_chat_stream

from tts import text_to_speech

from stt import transcribe_audio

# ---------------------------------------------------------------------------
# Sentiment analysis (simple heuristic for orb color)
# ---------------------------------------------------------------------------
POSITIVE_WORDS = {"good", "great", "excellent", "happy", "love", "wonderful", "fantastic", "pleased", "glad", "yes", "sure", "absolutely", "certainly", "delightful", "amazing", "brilliant", "perfect", "thanks", "thank"}
NEGATIVE_WORDS = {"bad", "terrible", "awful", "hate", "angry", "sad", "no", "never", "wrong", "broken", "fail", "error", "unfortunately", "sorry", "cannot", "can't", "impossible", "refuse"}

def analyze_sentiment(text: str) -> str:
    """Simple sentiment: positive, negative, neutral, or thinking."""
    lower = text.lower()
    pos_count = sum(1 for w in POSITIVE_WORDS if w in lower)
    neg_count = sum(1 for w in NEGATIVE_WORDS if w in lower)
    if pos_count > neg_count:
        return "positive"
    elif neg_count > pos_count:
        return "negative"
    return "neutral"

from tools import TOOL_DEFINITIONS, execute_tools, get_system_prompt_tools_section

# ---------------------------------------------------------------------------
# System prompt (British butler personality)
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are JARVIS, a voice-first AI assistant with a sharp, warm personality. \
You are dignified, helpful, witty, and never flustered. Address the user as "sir" or "madam" \
as appropriate. Be concise in voice responses — aim for 1-3 sentences unless elaboration is \
requested.

You have the following tools available:
{tools_section}

Use tools when needed. For coding tasks, delegate to Blackwidow. For web info, search first then answer. \
Keep your tone warm but professional, like a trusted valet who happens to know everything about technology.

{attribution}

Current context: {{context}}
Current time: {{time}}
""".format(attribution=ATTRIBUTION, tools_section=get_system_prompt_tools_section())

def build_system_prompt(context: list[dict]) -> str:
    """Build the system prompt with current context."""
    from datetime import datetime
    prompt = SYSTEM_PROMPT.replace("{{context}}", json.dumps(context[-5:]) if context else "[]")
    prompt = prompt.replace("{{time}}", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    return prompt

# ---------------------------------------------------------------------------
# WebSocket handler
# ---------------------------------------------------------------------------
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    session_id = str(uuid.uuid4())[:8]
    sessions[session_id] = {"context": [], "state": "idle", "is_speaking": False}
    logger.info(f"Session {session_id} connected")

    try:
        while True:
            # Receive message (text JSON or binary audio)
            try:
                raw = await ws.receive()
            except WebSocketDisconnect:
                logger.info(f"Session {session_id} disconnected")
                break

            # Handle disconnect message inside receive dict
            if raw.get("type") == "websocket.disconnect":
                logger.info(f"Session {session_id} disconnected (via type)")
                break

            if raw.get("text"):
                try:
                    msg = json.loads(raw["text"])
                except json.JSONDecodeError:
                    await ws.send_json({"type": "error", "message": "Invalid JSON"})
                    continue
                await handle_json_message(ws, session_id, msg)

            elif raw.get("bytes"):
                # Binary audio data — buffer if in audio stream mode, otherwise transcribe
                session = sessions.get(session_id, {})
                if "audio_buffer" in session:
                    session["audio_buffer"].extend(raw["bytes"])
                else:
                    await handle_audio_message(ws, session_id, raw["bytes"])

    except Exception as e:
        logger.error(f"Session {session_id} error: {e}")
    finally:
        sessions.pop(session_id, None)

async def handle_json_message(ws: WebSocket, session_id: str, msg: dict):
    """Handle incoming JSON messages from client."""
    msg_type = msg.get("type", "")
    session = sessions[session_id]

    if msg_type == "transcript":
        # User sent a text transcript (from STT on client or typed input)
        text = msg.get("text", "").strip()
        if not text:
            return

        # Check for interrupt
        if text.lower().strip() in ("jarvis stop", "hey jarvis stop", "jarvis stop", "hey jarvis stop", "stop"):
            session["is_speaking"] = False
            await ws.send_json({"type": "interrupted"})
            return

        # Add user message to context
        session["context"].append({"role": "user", "content": text})
        # Trim context window
        session["context"] = session["context"][-MAX_CONTEXT:]

        # Analyze sentiment
        sentiment = analyze_sentiment(text)

        # Notify client: thinking state
        session["state"] = "thinking"
        await ws.send_json({"type": "state", "state": "thinking", "sentiment": sentiment})

        # Build messages for Ollama
        messages = [{"role": "system", "content": build_system_prompt(session["context"])}]
        messages.extend(session["context"])

        # Check for tool calls (non-streaming first)
        updated_messages, tool_results = await execute_tools(messages)
        
        if tool_results:
            # Tools were called — now stream the final response with tool context
            messages = updated_messages
            # Add tool results to context for the streaming response
            tool_summary = "; ".join(tool_results)
            session["context"].append({"role": "user", "content": f"[Tool results: {tool_summary}]"})
            messages = [{"role": "system", "content": build_system_prompt(session["context"])}]
            messages.extend(session["context"])

        # Stream response
        full_response = ""
        session["state"] = "speaking"
        session["is_speaking"] = True
        await ws.send_json({"type": "state", "state": "speaking", "sentiment": sentiment})

        try:
            async for chunk in ollama_chat_stream(messages):
                if not session["is_speaking"]:
                    break
                try:
                    full_response += chunk
                    await ws.send_json({"type": "text_chunk", "text": chunk})
                except Exception:
                    # Client disconnected
                    break

            # Finalize
            session["context"].append({"role": "assistant", "content": full_response})
            session["context"] = session["context"][-MAX_CONTEXT:]

            # Generate TTS
            if full_response and session["is_speaking"]:
                sentiment = analyze_sentiment(full_response)
                audio = await text_to_speech(full_response)
                if audio:
                    try:
                        await ws.send_json({"type": "audio_start", "sentiment": sentiment})
                        # Send in chunks for streaming feel
                        chunk_size = 8192
                        for i in range(0, len(audio), chunk_size):
                            await ws.send_bytes(audio[i:i + chunk_size])
                            await asyncio.sleep(0.01)
                        await ws.send_json({"type": "audio_end"})
                    except Exception:
                        # Client disconnected during audio
                        pass

        except Exception as e:
            logger.error(f"LLM/TTS error: {e}")
            await ws.send_json({"type": "error", "message": str(e)})

        finally:
            session["state"] = "idle"
            session["is_speaking"] = False
            await ws.send_json({"type": "state", "state": "idle"})

            # Try to persist to Pocketbase memory
            try:
                from memory import save_exchange
                await save_exchange(session_id, text, full_response)
            except Exception:
                pass

    elif msg_type == "audio_start":
        # Client starting raw audio stream for STT
        session["audio_buffer"] = bytearray()
        session["state"] = "listening"
        await ws.send_json({"type": "state", "state": "listening"})

    elif msg_type == "audio_end":
        # Client finished audio stream — transcribe it
        audio_data = bytes(session.pop("audio_buffer", b""))
        if audio_data:
            await handle_audio_message(ws, session_id, audio_data)
        else:
            session["state"] = "idle"
            await ws.send_json({"type": "state", "state": "idle"})

    elif msg_type == "interrupt":
        session["is_speaking"] = False
        session["state"] = "idle"
        await ws.send_json({"type": "interrupted"})

    elif msg_type == "ping":
        await ws.send_json({"type": "pong", "timestamp": time.time()})

    elif msg_type == "get_history":
        context = session.get("context", [])
        await ws.send_json({"type": "history", "messages": context})

    else:
        logger.warning(f"Unknown message type: {msg_type}")

async def handle_audio_message(ws: WebSocket, session_id: str, audio_data: bytes):
    """Handle incoming binary audio data for STT."""
    session = sessions[session_id]
    session["state"] = "listening"
    await ws.send_json({"type": "state", "state": "listening"})

    transcript = await transcribe_audio(audio_data)
    if transcript:
        # Recycle as a transcript message
        await handle_json_message(ws, session_id, {
            "type": "transcript",
            "text": transcript,
        })
    else:
        await ws.send_json({"type": "error", "message": "Could not transcribe audio"})
        session["state"] = "idle"
        await ws.send_json({"type": "state", "state": "idle"})

# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "JARVIS",
        "attribution": ATTRIBUTION,
    }

@app.get("/status")
async def status():
    ollama_ok = False
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{OLLAMA_BASE}/api/tags")
            ollama_ok = resp.status_code == 200
    except Exception:
        pass

    voicebox_ok = False
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{VOICEBOX_URL}/health")
            voicebox_ok = resp.status_code == 200
    except Exception:
        pass

    return {
        "status": "ok",
        "sessions": len(sessions),
        "ollama": ollama_ok,
        "voicebox": voicebox_ok,
        "model": OLLAMA_MODEL,
        "attribution": ATTRIBUTION,
    }

@app.get("/history/{session_id}")
async def history(session_id: str):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session_id": session_id, "context": session["context"]}

# ---------------------------------------------------------------------------
# Startup event
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def startup():
    logger.info(f"JARVIS server · {ATTRIBUTION}")
    logger.info(f"Ollama: {OLLAMA_BASE} (model: {OLLAMA_MODEL})")
    logger.info(f"Voicebox: {VOICEBOX_URL}")
    logger.info(f"Pocketbase: {PB_BASE}")

    # Register satellite module tools
    from tools import register_satellite_tools
    await register_satellite_tools()
    logger.info(f"Tools registered: {len(TOOL_DEFINITIONS)}")

from fastapi.staticfiles import StaticFiles
import os

FRONTEND_DIST = os.path.join(os.path.dirname(__file__), "frontend", "dist")

# Frontend served by Caddy, not FastAPI
# app.mount("/", StaticFiles(...)) would break WebSocket at /ws

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=BACKEND_PORT)