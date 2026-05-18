"""
JARVIS — Memory Module
Pocketbase-backed persistent memory with three-tier context.

Built from CLAUDE.md by RJ - https://itsbrook.com
"""

import json
import logging
import os
from datetime import datetime
from typing import Optional

import httpx

logger = logging.getLogger("jarvis.memory")

PB_BASE = os.getenv("PB_BASE", "http://localhost:8090")
PB_USER = os.getenv("PB_USER", "jarvis")
PB_PASS = os.getenv("PB_PASS", "jarvis123")

_auth_token: Optional[str] = None


async def _ensure_auth() -> str:
    """Authenticate with Pocketbase and return token."""
    global _auth_token
    if _auth_token:
        return _auth_token
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{PB_BASE}/api/collections/users/auth-with-password",
            json={"identity": PB_USER, "password": PB_PASS},
        )
        if resp.status_code == 200:
            _auth_token = resp.json().get("token", "")
            return _auth_token
        # If auth fails, try without auth (dev mode)
        logger.warning(f"Pocketbase auth failed: {resp.status_code}")
        return ""


async def _headers() -> dict:
    token = await _ensure_auth()
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


async def init_collections():
    """Ensure required Pocketbase collections exist."""
    collections = ["facts", "tasks", "notes", "conversations"]
    headers = await _headers()
    async with httpx.AsyncClient(timeout=10.0) as client:
        for col in collections:
            # Try to check if collection exists
            resp = await client.get(
                f"{PB_BASE}/api/collections/{col}",
                headers=headers,
            )
            if resp.status_code == 404:
                # Create collection
                schema = [
                    {"name": "content", "type": "text", "required": True},
                    {"name": "session_id", "type": "text"},
                    {"name": "tags", "type": "text"},
                    {"name": "created", "type": "date"},
                ]
                if col == "conversations":
                    schema = [
                        {"name": "session_id", "type": "text", "required": True},
                        {"name": "role", "type": "text", "required": True},
                        {"name": "content", "type": "text", "required": True},
                        {"name": "sentiment", "type": "text"},
                        {"name": "created", "type": "date"},
                    ]
                elif col == "facts":
                    schema = [
                        {"name": "key", "type": "text", "required": True},
                        {"name": "value", "type": "text", "required": True},
                        {"name": "tags", "type": "text"},
                        {"name": "created", "type": "date"},
                    ]
                elif col == "tasks":
                    schema = [
                        {"name": "title", "type": "text", "required": True},
                        {"name": "description", "type": "text"},
                        {"name": "status", "type": "text", "default": "pending"},
                        {"name": "priority", "type": "text"},
                        {"name": "created", "type": "date"},
                    ]
                elif col == "notes":
                    schema = [
                        {"name": "title", "type": "text", "required": True},
                        {"name": "body", "type": "text"},
                        {"name": "tags", "type": "text"},
                        {"name": "created", "type": "date"},
                    ]

                await client.post(
                    f"{PB_BASE}/api/collections",
                    json={
                        "name": col,
                        "type": "base",
                        "schema": schema,
                    },
                    headers=headers,
                )
                logger.info(f"Created Pocketbase collection: {col}")


async def save_exchange(session_id: str, user_text: str, assistant_text: str, sentiment: str = "neutral"):
    """Save a conversation exchange to Pocketbase."""
    headers = await _headers()
    now = datetime.utcnow().isoformat() + "Z"
    async with httpx.AsyncClient(timeout=10.0) as client:
        for role, content in [("user", user_text), ("assistant", assistant_text)]:
            try:
                await client.post(
                    f"{PB_BASE}/api/collections/conversations/records",
                    json={
                        "session_id": session_id,
                        "role": role,
                        "content": content,
                        "sentiment": sentiment if role == "assistant" else "",
                        "created": now,
                    },
                    headers=headers,
                )
            except Exception as e:
                logger.warning(f"Failed to save {role} exchange: {e}")


async def save_fact(key: str, value: str, tags: str = ""):
    """Save a fact to Pocketbase."""
    headers = await _headers()
    now = datetime.utcnow().isoformat() + "Z"
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            await client.post(
                f"{PB_BASE}/api/collections/facts/records",
                json={"key": key, "value": value, "tags": tags, "created": now},
                headers=headers,
            )
        except Exception as e:
            logger.warning(f"Failed to save fact: {e}")


async def search_facts(query: str, limit: int = 10) -> list[dict]:
    """Search facts by content."""
    headers = await _headers()
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(
                f"{PB_BASE}/api/collections/facts/records",
                params={"filter": f"key~'{query}'||value~'{query}'||tags~'{query}'", "perPage": limit},
                headers=headers,
            )
            if resp.status_code == 200:
                return resp.json().get("items", [])
        except Exception as e:
            logger.warning(f"Failed to search facts: {e}")
    return []


async def get_recent_conversations(session_id: str = "", limit: int = 20) -> list[dict]:
    """Get recent conversation history."""
    headers = await _headers()
    params = {"perPage": limit, "sort": "-created"}
    if session_id:
        params["filter"] = f"session_id='{session_id}'"
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(
                f"{PB_BASE}/api/collections/conversations/records",
                params=params,
                headers=headers,
            )
            if resp.status_code == 200:
                return resp.json().get("items", [])
        except Exception as e:
            logger.warning(f"Failed to get conversations: {e}")
    return []


async def save_task(title: str, description: str = "", priority: str = "medium") -> Optional[dict]:
    """Create a new task."""
    headers = await _headers()
    now = datetime.utcnow().isoformat() + "Z"
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                f"{PB_BASE}/api/collections/tasks/records",
                json={"title": title, "description": description, "status": "pending", "priority": priority, "created": now},
                headers=headers,
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            logger.warning(f"Failed to save task: {e}")
    return None


async def save_note(title: str, body: str = "", tags: str = "") -> Optional[dict]:
    """Create a new note."""
    headers = await _headers()
    now = datetime.utcnow().isoformat + "Z" if hasattr(datetime, "utcnow") else datetime.now().isoformat() + "Z"
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                f"{PB_BASE}/api/collections/notes/records",
                json={"title": title, "body": body, "tags": tags, "created": now},
                headers=headers,
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            logger.warning(f"Failed to save note: {e}")
    return None