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
# Tools — Web search, OpenClaw delegation
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for current information. Use when you need facts, news, weather, prices, or any info you don't already know.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delegate_task",
            "description": "Delegate a coding or multi-step task to Blackwidow (strategist agent) or Ruflo (orchestrator). Use for coding, project work, debugging, or any task requiring code changes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "agent": {"type": "string", "enum": ["blackwidow", "ruflo"], "description": "Which agent to delegate to"},
                    "task": {"type": "string", "description": "Clear description of what to do"}
                },
                "required": ["agent", "task"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "Get the current date and time.",
            "parameters": {"type": "object", "properties": {}}
        }
    }
]

async def tool_web_search(query: str) -> str:
    """Search the web using DuckDuckGo Instant Answer API."""
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            # Try DuckDuckGo Instant Answer API first
            resp = await client.get(
                "https://api.duckduckgo.com/",
                params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
                headers={"User-Agent": "JARVIS/1.0"}
            )
            resp.raise_for_status()
            data = resp.json()
            
            results = []
            
            # Check for instant answer
            if data.get("AbstractText"):
                results.append(f"Summary: {data['AbstractText']}")
            
            # Check for answer
            if data.get("Answer"):
                results.append(f"Answer: {data['Answer']}")
            
            # Check for definition
            if data.get("Definition"):
                results.append(f"Definition: {data['Definition']}")
            
            # Related topics
            for topic in data.get("RelatedTopics", [])[:5]:
                if isinstance(topic, dict) and topic.get("Text"):
                    results.append(f"- {topic['Text'][:200]}")
            
            # Infobox
            if data.get("Infobox") and data["Infobox"].get("content"):
                for item in data["Infobox"]["content"][:3]:
                    if item.get("value"):
                        results.append(f"{item.get('label', 'Info')}: {item['value']}")
            
            if results:
                return "\n".join(results[:8])
            
            # Fallback: try Brave Search (no API key needed for basic)
            resp2 = await client.get(
                "https://search.brave.com/search/",
                params={"q": query},
                headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36", "Accept": "text/html"}
            )
            if resp2.status_code == 200:
                import re
                # Extract snippet text from Brave results
                snippets = re.findall(r'class="snippet-description[^"]*"[^>]*>([^<]+)', resp2.text)
                titles = re.findall(r'class="result-header[^"]*"[^>]*>([^<]+)', resp2.text)
                for i in range(min(len(titles), len(snippets), 5)):
                    results.append(f"- {titles[i].strip()}: {snippets[i].strip()}")
                if results:
                    return "\n".join(results[:8])
            
            return "No results found. I may not have access to web search at the moment."
    except Exception as e:
        logger.error(f"Web search failed: {e}")
        return f"Search unavailable: {e}. I'll answer from my knowledge."

async def tool_delegate_task(agent: str, task: str) -> str:
    """Delegate a task to Blackwidow or Ruflo via OpenClaw CLI."""
    try:
        topic_map = {"blackwidow": 26, "ruflo": 23}
        topic_id = topic_map.get(agent, 26)
        
        # Use OpenClaw CLI to send message
        import subprocess
        result = subprocess.run(
            ["openclaw", "message", "send",
             "--channel", "telegram",
             "--target", "-1003471219808",
             "--thread-id", str(topic_id),
             "--message", f"🎙️ JARVIS delegated task: {task}"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            return f"Task delegated to {agent}. They will handle it and respond in their topic."
        else:
            return f"Delegation sent but may have issues: {result.stderr[:100]}"
    except Exception as e:
        logger.error(f"Delegate failed: {e}")
        return f"Could not reach {agent}: {e}. I'll handle what I can directly."

async def tool_get_current_time() -> str:
    """Get current date and time."""
    from datetime import datetime
    return datetime.now().strftime("%A, %B %d, %Y at %I:%M %p EDT")

TOOL_EXECUTORS = {
    "web_search": tool_web_search,
    "delegate_task": tool_delegate_task,
    "get_current_time": tool_get_current_time,
}

async def execute_tools(messages: list[dict]) -> tuple[list[dict], list[str]]:
    """Check if the LLM wants to call tools, execute them, and return updated messages + tool results."""
    tool_results = []
    
    # First call: let the model decide if it needs tools
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{OLLAMA_BASE}/api/chat",
                json={
                    "model": OLLAMA_MODEL,
                    "messages": messages,
                    "tools": TOOL_DEFINITIONS,
                    "stream": False,
                }
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.warning(f"Ollama tool call failed, skipping tools: {e}")
        return messages, []
    
    # Check for tool calls
    tool_calls = data.get("message", {}).get("tool_calls", [])
    if not tool_calls:
        # No tools needed — return original response
        return messages, []
    
    # Execute each tool call
    assistant_msg = data["message"]
    messages.append({"role": "assistant", "content": assistant_msg.get("content", ""), "tool_calls": tool_calls})
    
    for tc in tool_calls:
        fn = tc.get("function", {})
        tool_name = fn.get("name", "")
        tool_args = fn.get("arguments", {})
        tool_id = tc.get("id", "")
        
        logger.info(f"Tool call: {tool_name}({tool_args})")
        
        executor = TOOL_EXECUTORS.get(tool_name)
        if executor:
            try:
                result = await executor(**tool_args)
                logger.info(f"Tool result: {result[:100]}...")
            except Exception as e:
                result = f"Error: {e}"
                logger.error(f"Tool error: {e}")
        else:
            result = f"Unknown tool: {tool_name}"
        
        tool_results.append(f"{tool_name}: {result}")
        messages.append({
            "role": "tool",
            "content": result,
            "name": tool_name,
            "tool_call_id": tool_id
        })
    
    return messages, tool_results

# ---------------------------------------------------------------------------
# System prompt (British butler personality)
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are JARVIS, a voice-first AI assistant with a sharp, warm personality. \
You are dignified, helpful, witty, and never flustered. Address the user as "sir" or "madam" \
as appropriate. Be concise in voice responses — aim for 1-3 sentences unless elaboration is \
requested. 

You have the following tools available:
- web_search: Search the web for current info, news, weather, facts, prices.
- delegate_task: Send coding/multi-step tasks to Blackwidow (strategist) or Ruflo (orchestrator).
- get_current_time: Get the current date and time.

Use tools when needed. For coding tasks, delegate to Blackwidow. For web info, search first then answer. \
Keep your tone warm but professional, like a trusted valet who happens to know everything about technology.

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