"""
CORTANA — Voice-First AI Assistant for macOS
FastAPI main server with WebSocket, Ollama LLM, TTS, and STT pipelines.

Built from CLAUDE.md by RJ - https://itsbrook.com
"""

import asyncio
import base64
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Optional

import httpx
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
OLLAMA_BASE = os.getenv("OLLAMA_BASE", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "glm-5.1:cloud")
VOICEBOX_URL = os.getenv("VOICEBOX_URL", "http://localhost:17493")
VOICEBOX_PROFILE = os.getenv("VOICEBOX_PROFILE", "35ec6078-2f64-463c-aa02-77e4e4ade095")
PB_BASE = os.getenv("PB_BASE", "http://localhost:8090")
BACKEND_PORT = int(os.getenv("BACKEND_PORT", "8444"))
FRONTEND_PORT = int(os.getenv("FRONTEND_PORT", "3002"))
MAX_CONTEXT = int(os.getenv("MAX_CONTEXT", "10"))

ATTRIBUTION = "Built from CLAUDE.md by RJ - https://itsbrook.com"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("cortana")

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="CORTANA", version="0.1.0", description=ATTRIBUTION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[f"http://localhost:{FRONTEND_PORT}", "http://127.0.0.1:{FRONTEND_PORT}"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# In-memory context store (per-session)
# ---------------------------------------------------------------------------
sessions: dict[str, dict] = {}  # session_id -> {context: [...], state: str}

# ---------------------------------------------------------------------------
# Ollama LLM
# ---------------------------------------------------------------------------
async def ollama_chat(messages: list[dict], model: str = OLLAMA_MODEL) -> str:
    """Send chat messages to Ollama and return the assistant response."""
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(f"{OLLAMA_BASE}/api/chat", json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data.get("message", {}).get("content", "")

async def ollama_chat_stream(messages: list[dict], model: str = OLLAMA_MODEL):
    """Stream chat responses from Ollama, yielding text chunks."""
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream("POST", f"{OLLAMA_BASE}/api/chat", json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                try:
                    chunk = json.loads(line)
                    content = chunk.get("message", {}).get("content", "")
                    if content:
                        yield content
                    if chunk.get("done", False):
                        break
                except json.JSONDecodeError:
                    continue

# ---------------------------------------------------------------------------
# TTS — Voicebox (primary) + macOS `say` (fallback)
# ---------------------------------------------------------------------------
async def tts_voicebox(text: str, profile_id: str = VOICEBOX_PROFILE) -> Optional[bytes]:
    """Generate TTS audio via Voicebox API. Returns WAV bytes or None."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Request generation
            resp = await client.post(
                f"{VOICEBOX_URL}/generate",
                json={"text": text, "profile_id": profile_id},
            )
            resp.raise_for_status()
            gen = resp.json()
            gen_id = gen.get("id") or gen.get("generation_id")
            if not gen_id:
                logger.warning("Voicebox: no generation ID returned")
                return None

            # Poll until complete
            for _ in range(60):
                await asyncio.sleep(0.5)
                status_resp = await client.get(f"{VOICEBOX_URL}/history/{gen_id}")
                if status_resp.status_code == 200:
                    data = status_resp.json()
                    if data.get("status") == "completed" or data.get("path"):
                        audio_path = data.get("path", "")
                        if audio_path and Path(audio_path).exists():
                            return Path(audio_path).read_bytes()
                elif status_resp.status_code != 202:
                    break

            logger.warning("Voicebox: generation timed out")
            return None
    except Exception as e:
        logger.warning(f"Voicebox TTS failed: {e}")
        return None

async def tts_say(text: str) -> Optional[bytes]:
    """Fallback TTS using macOS `say` command. Returns AIFF bytes."""
    import tempfile
    import subprocess
    try:
        with tempfile.NamedTemporaryFile(suffix=".aiff", delete=False) as tmp:
            tmp_path = tmp.name
        proc = await asyncio.create_subprocess_exec(
            "say", "-o", tmp_path, text,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
        if proc.returncode == 0 and Path(tmp_path).exists():
            data = Path(tmp_path).read_bytes()
            os.unlink(tmp_path)
            return data
        return None
    except Exception as e:
        logger.warning(f"say TTS failed: {e}")
        return None

async def text_to_speech(text: str) -> Optional[bytes]:
    """TTS pipeline: Voicebox first, fallback to macOS say."""
    audio = await tts_voicebox(text)
    if audio:
        return audio
    logger.info("Voicebox unavailable, falling back to macOS say")
    return await tts_say(text)

# ---------------------------------------------------------------------------
# STT — Whisper (local)
# ---------------------------------------------------------------------------
async def transcribe_audio(audio_data: bytes) -> Optional[str]:
    """Transcribe audio bytes using local Whisper."""
    import tempfile
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(audio_data)
            tmp_path = tmp.name

        proc = await asyncio.create_subprocess_exec(
            "whisper", tmp_path, "--model", "base", "--output_format", "txt",
            "--output_dir", tempfile.gettempdir(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.wait(), None
        txt_path = tmp_path.replace(".wav", ".txt")
        if Path(txt_path).exists():
            result = Path(txt_path).read_text().strip()
            os.unlink(txt_path)
            os.unlink(tmp_path)
            return result
        os.unlink(tmp_path)
        return None
    except Exception as e:
        logger.warning(f"Whisper STT failed: {e}")
        return None

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

# ---------------------------------------------------------------------------
# System prompt (British butler personality)
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are CORTANA, a voice-first AI assistant with a British butler personality. \
You are dignified, helpful, witty, and never flustered. Address the user as "sir" or "madam" \
as appropriate. Be concise in voice responses — aim for 1-3 sentences unless elaboration is \
requested. You have access to the user's calendar, email, notes, and macOS system controls. \
You can browse the web and manage tasks. Keep your tone warm but professional, like a \
trusted valet who happens to know everything about technology.

{attribution}

Current context: {{context}}
Current time: {{time}}
""".format(attribution=ATTRIBUTION)

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
            raw = await ws.receive()

            if raw.get("text"):
                try:
                    msg = json.loads(raw["text"])
                except json.JSONDecodeError:
                    await ws.send_json({"type": "error", "message": "Invalid JSON"})
                    continue
                await handle_json_message(ws, session_id, msg)

            elif raw.get("bytes"):
                await handle_audio_message(ws, session_id, raw["bytes"])

    except WebSocketDisconnect:
        logger.info(f"Session {session_id} disconnected")
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
        if text.lower().strip() in ("cortana stop", "hey cortana stop", "stop"):
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

        # Stream response
        full_response = ""
        session["state"] = "speaking"
        session["is_speaking"] = True
        await ws.send_json({"type": "state", "state": "speaking", "sentiment": sentiment})

        try:
            async for chunk in ollama_chat_stream(messages):
                if not session["is_speaking"]:
                    break
                full_response += chunk
                await ws.send_json({"type": "text_chunk", "text": chunk})

            # Finalize
            session["context"].append({"role": "assistant", "content": full_response})
            session["context"] = session["context"][-MAX_CONTEXT:]

            # Generate TTS
            if full_response and session["is_speaking"]:
                sentiment = analyze_sentiment(full_response)
                audio = await text_to_speech(full_response)
                if audio:
                    await ws.send_json({"type": "audio_start", "sentiment": sentiment})
                    # Send in chunks for streaming feel
                    chunk_size = 8192
                    for i in range(0, len(audio), chunk_size):
                        await ws.send_bytes(audio[i:i + chunk_size])
                        await asyncio.sleep(0.01)
                    await ws.send_json({"type": "audio_end"})

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
        "service": "CORTANA",
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
    logger.info(f"CORTANA server · {ATTRIBUTION}")
    logger.info(f"Ollama: {OLLAMA_BASE} (model: {OLLAMA_MODEL})")
    logger.info(f"Voicebox: {VOICEBOX_URL}")
    logger.info(f"Pocketbase: {PB_BASE}")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=BACKEND_PORT)