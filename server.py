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
    TELEGRAM_CHAT_ID, OPENCLAW_TELEGRAM_TOPIC,
)

# ---------------------------------------------------------------------------
# Telegram Relay
# ---------------------------------------------------------------------------
async def relay_to_telegram(user_text: str, jarvis_response: str) -> None:
    """Send a conversation summary to Telegram via OpenClaw CLI."""
    try:
        summary = f"🎙️ **You:** {user_text[:150]}\n🤖 **JARVIS:** {jarvis_response[:300]}"
        proc = await asyncio.create_subprocess_exec(
            "openclaw", "message", "send",
            "--channel", "telegram",
            "--target", "-1003471219808",
            "--thread-id", "19",
            "--message", summary,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.wait()
    except Exception as e:
        logger.warning(f"Telegram relay failed: {e}")


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
When the user asks about weather, call the /weather endpoint to get real-time forecast data from weather.gov (Montgomery County, MD). \
Keep your tone warm but professional, like a trusted valet who happens to know everything about technology.

{attribution}

{{{{memory_section}}}}
Current context: {{{{context}}}}
Current time: {{{{time}}}}
""".format(attribution=ATTRIBUTION, tools_section=get_system_prompt_tools_section())

async def _load_memory() -> str:
    """Load Obsidian memory and daily note for system prompt."""
    from datetime import datetime
    try:
        from obsidian import read_memory, read_daily_note
        memory_content = await read_memory()
        today = datetime.now().strftime("%Y-%m-%d")
        daily = await read_daily_note(today)
        return f"""## Your Long-Term Memory\n{memory_content[:2000]}\n\n## Today's Notes\n{daily[:1500]}"""
    except Exception as e:
        logger.warning(f"Failed to load memory: {e}")
        return ""


def build_system_prompt(context: list[dict], memory_section: str = "") -> str:
    """Build the system prompt with current context and Obsidian memory."""
    from datetime import datetime
    prompt = SYSTEM_PROMPT.replace("{{memory_section}}", memory_section)
    prompt = prompt.replace("{{context}}", json.dumps(context[-5:]) if context else "[]")
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

    # Tell client their session ID
    await ws.send_json({"type": "session_assigned", "session_id": session_id})

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
                # Echo cancel: discard audio while speaking
                if session.get("is_speaking"):
                    continue
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
        memory_section = await _load_memory()
        messages = [{"role": "system", "content": build_system_prompt(session["context"], memory_section)}]
        messages.extend(session["context"])

        # Check for tool calls (non-streaming first)
        updated_messages, tool_results = await execute_tools(messages)
        
        if tool_results:
            # Tools were called — now stream the final response with tool context
            messages = updated_messages
            # Add tool results to context for the streaming response
            tool_summary = "; ".join(tool_results)
            session["context"].append({"role": "user", "content": f"[Tool results: {tool_summary}]"})
            messages = [{"role": "system", "content": build_system_prompt(session["context"], memory_section)}]
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
                    logger.info(f"TTS audio ready: {len(audio)} bytes, sending to client")
                    try:
                        await ws.send_json({"type": "audio_start", "sentiment": sentiment})
                        # Send in chunks for streaming feel
                        chunk_size = 8192
                        for i in range(0, len(audio), chunk_size):
                            await ws.send_bytes(audio[i:i + chunk_size])
                            await asyncio.sleep(0.01)
                        await ws.send_json({"type": "audio_end"})
                        logger.info("TTS audio sent successfully")
                    except Exception as e:
                        logger.warning(f"Client disconnected during audio: {e}")
                        pass
                else:
                    logger.warning("TTS returned no audio")

        except Exception as e:
            logger.error(f"LLM/TTS error: {e}")
            await ws.send_json({"type": "error", "message": str(e)})

        finally:
            session["state"] = "idle"
            session["is_speaking"] = False
            await ws.send_json({"type": "state", "state": "idle"})

            # Persist to Pocketbase memory
            try:
                from memory import save_exchange
                await save_exchange(session_id, text, full_response, sentiment)

                # Also save to Obsidian daily note
                from obsidian import append_to_daily_note
                from datetime import datetime
                ts = datetime.now().strftime("%H:%M")
                await append_to_daily_note(f"**{ts}** User: {text[:200]}\n**{ts}** JARVIS: {full_response[:200]}")

                # Relay to Telegram
                await relay_to_telegram(text, full_response)
            except Exception as e:
                logger.warning(f"Failed to save exchange to memory: {e}")
                logger.debug(f"Saved exchange to memory for session {session_id}")
            except Exception as e:
                logger.warning(f"Failed to save exchange to Pocketbase: {e}")

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

    elif msg_type == "resume_session":
        # Client wants to resume an existing session
        old_session_id = msg.get("session_id", "")
        if old_session_id and old_session_id in sessions:
            # Session still in memory — switch to it
            session = sessions[old_session_id]
            # Delete the new empty session we just created
            sessions.pop(session_id, None)
            session_id = old_session_id
            logger.info(f"Resumed session {session_id}")
            await ws.send_json({"type": "session_resumed", "session_id": session_id})
        else:
            # Session not found — try loading from Pocketbase
            try:
                from memory import get_recent_conversations
                conversations = await get_recent_conversations(session_id=old_session_id, limit=MAX_CONTEXT)
                if conversations:
                    # Load context from Pocketbase
                    context = []
                    for conv in reversed(conversations):
                        context.append({"role": conv.get("role", ""), "content": conv.get("content", "")})
                    sessions[session_id]["context"] = context
                    logger.info(f"Loaded {len(context)} messages from Pocketbase for session {old_session_id}")
                await ws.send_json({"type": "session_resumed", "session_id": session_id})
            except Exception as e:
                logger.warning(f"Failed to load session from Pocketbase: {e}")
                await ws.send_json({"type": "session_assigned", "session_id": session_id})

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

@app.get("/weather")
async def weather():
    """Fetch weather forecast from weather.gov API (no key needed)."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://api.weather.gov/gridpoints/LWX/96,90/forecast",
                headers={"User-Agent": "JARVIS/1.0", "Accept": "application/geo+json"},
            )
            if resp.status_code != 200:
                return {"error": f"weather.gov returned {resp.status_code}"}
            data = resp.json()
            periods = data.get("properties", {}).get("periods", [])[:8]
            forecast = []
            for p in periods:
                forecast.append({
                    "name": p.get("name", ""),
                    "temperature": f"{p.get('temperature', '?')}°F",
                    "wind": f"{p.get('windSpeed', '?')} {p.get('windDirection', '?')}",
                    "short": p.get("shortForecast", ""),
                    "detail": p.get("detailedForecast", ""),
                    "precip": f"{p.get('probabilityOfPrecipitation', {}).get('value', '?')}%",
                })
            return {"location": "Montgomery County, MD", "forecast": forecast}
    except Exception as e:
        return {"error": str(e)}


@app.get("/news")
async def news():
    """Fetch top news headlines from free APIs."""
    import xml.etree.ElementTree as ET
    articles = []

    # Source 1: Google News RSS (unlimited, no key)
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            resp = await client.get(
                "https://news.google.com/rss/search?q=us+top+stories&hl=en-US&gl=US&ceid=US:en",
                headers={"User-Agent": "JARVIS/1.0"}
            )
            if resp.status_code == 200:
                root = ET.fromstring(resp.text)
                items = list(root.iter("item"))[:10]
                for item in items:
                    title = item.findtext("title", "")
                    link = item.findtext("link", "")
                    pub_date = item.findtext("pubDate", "")[:16]
                    source_el = item.find("source")
                    source_name = source_el.text if source_el is not None else ""
                    desc = item.findtext("description", "")[:140]
                    articles.append({"title": title, "source": source_name, "url": link, "published": pub_date, "desc": desc})
    except Exception as e:
        logger.warning(f"Google News RSS failed: {e}")

    # Source 2: Currents API (needs free key from currentsapi.services)
    currents_key = os.environ.get("CURRENTS_API_KEY", "")
    if not articles and currents_key:
        try:
            async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
                resp = await client.get(
                    "https://api.currentsapi.services/v1/latest-news",
                    params={"language": "en", "country": "US", "apiKey": currents_key},
                    headers={"User-Agent": "JARVIS/1.0"}
                )
                if resp.status_code == 200:
                    data = resp.json()
                    for a in data.get("news", [])[:10 - len(articles)]:
                        title = a.get("title", "")
                        if not title:
                            continue
                        source = a.get("author", a.get("source", "")) or ""
                        if isinstance(source, dict):
                            source = source.get("name", "")
                        published = (a.get("published", "") or "")[:10]
                        desc = (a.get("description") or a.get("content") or "")[:140]
                        url = a.get("url", "")
                        articles.append({"title": title, "source": source, "url": url, "published": published, "desc": desc})
        except Exception as e:
            logger.warning(f"Currents API failed: {e}")

    if not articles:
        return {"articles": [], "message": "No news available"}
    return {"articles": articles[:10]}

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