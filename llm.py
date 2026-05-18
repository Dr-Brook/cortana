"""
JARVIS — LLM Module
Ollama chat (local) with OpenRouter cloud fallback. Streaming and non-streaming.

Built from CLAUDE.md by RJ - https://itsbrook.com
"""

import json
import logging
from typing import AsyncGenerator

import httpx

from config import OLLAMA_BASE, OLLAMA_MODEL, OPENROUTER_API_KEY, OPENROUTER_MODEL

logger = logging.getLogger("jarvis.llm")


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


async def ollama_chat_stream(messages: list[dict], model: str = OLLAMA_MODEL) -> AsyncGenerator[str, None]:
    """Stream chat responses from Ollama, with OpenRouter fallback."""
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
    }
    try:
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
    except Exception as e:
        logger.warning(f"Ollama failed, falling back to OpenRouter: {e}")
        async for chunk in openrouter_chat_stream(messages):
            yield chunk


async def openrouter_chat_stream(messages: list[dict], model: str = OPENROUTER_MODEL) -> AsyncGenerator[str, None]:
    """Stream chat responses from OpenRouter (cloud fallback)."""
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
    }
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://jarvis.local",
        "X-Title": "JARVIS Voice Assistant",
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        async with client.stream("POST", "https://openrouter.ai/api/v1/chat/completions", json=payload, headers=headers) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.strip() or not line.startswith("data: "):
                    continue
                data = line[6:]  # strip "data: "
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                    content = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                    if content:
                        yield content
                except json.JSONDecodeError:
                    continue