"""
JARVIS — Unified Tool Registry
Tool definitions, executors, and execution engine. All satellite modules
are imported and registered here.

Built from CLAUDE.md by RJ - https://itsbrook.com
"""

import asyncio
import json
import logging
import re
import subprocess
from datetime import datetime
from typing import Optional

import httpx

from config import (
    OLLAMA_BASE, OLLAMA_MODEL, DUCKDUCKGO_URL,
    TELEGRAM_CHAT_ID, TOPIC_BLACKWIDOW, TOPIC_RUFLO,
)

logger = logging.getLogger("jarvis.tools")

# ---------------------------------------------------------------------------
# Tool Definitions (Ollama tool format)
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
    },
]

# ---------------------------------------------------------------------------
# Tool Executors
# ---------------------------------------------------------------------------

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
        topic_map = {"blackwidow": TOPIC_BLACKWIDOW, "ruflo": TOPIC_RUFLO}
        topic_id = topic_map.get(agent, TOPIC_BLACKWIDOW)

        result = subprocess.run(
            ["openclaw", "message", "send",
             "--channel", "telegram",
             "--target", TELEGRAM_CHAT_ID,
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
    return datetime.now().strftime("%A, %B %d, %Y at %I:%M %p EDT")


# ---------------------------------------------------------------------------
# Tool Executor Registry
# ---------------------------------------------------------------------------
TOOL_EXECUTORS = {
    "web_search": tool_web_search,
    "delegate_task": tool_delegate_task,
    "get_current_time": tool_get_current_time,
}


# ---------------------------------------------------------------------------
# Dynamic Tool Registration (for satellite modules)
# ---------------------------------------------------------------------------
def register_tool(definition: dict, executor: callable) -> None:
    """Register a new tool at runtime. Used by satellite modules."""
    name = definition["function"]["name"]
    TOOL_DEFINITIONS.append(definition)
    TOOL_EXECUTORS[name] = executor
    logger.info(f"Registered tool: {name}")


def get_tool_names() -> list[str]:
    """Get list of all registered tool names."""
    return [t["function"]["name"] for t in TOOL_DEFINITIONS]


def get_system_prompt_tools_section() -> str:
    """Generate the tools section for the system prompt."""
    lines = []
    for t in TOOL_DEFINITIONS:
        fn = t["function"]
        desc = fn["description"].split(".")[0]  # First sentence only
        lines.append(f"- {fn['name']}: {desc}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool Execution Engine
# ---------------------------------------------------------------------------
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
# Satellite Module Registration
# ---------------------------------------------------------------------------
async def register_satellite_tools() -> None:
    """Import and register tools from satellite modules.

    Each module that wants to expose tools should define:
      - MODULE_TOOLS: list of tool definitions (Ollama format)
      - MODULE_EXECUTORS: dict of tool_name -> async callable
    """
    modules = []

    # Try importing each satellite module
    for mod_name in ["actions", "calendar_access", "mail_access", "notes_access", "memory", "browser", "work_mode"]:
        try:
            mod = __import__(mod_name)
            modules.append((mod_name, mod))
            logger.info(f"Loaded satellite module: {mod_name}")
        except ImportError as e:
            logger.warning(f"Could not import satellite module {mod_name}: {e}")
        except Exception as e:
            logger.warning(f"Error loading satellite module {mod_name}: {e}")

    # Register tools from each module
    for mod_name, mod in modules:
        tools = getattr(mod, "MODULE_TOOLS", [])
        executors = getattr(mod, "MODULE_EXECUTORS", {})

        for tool_def in tools:
            name = tool_def.get("function", {}).get("name", "")
            executor = executors.get(name)
            if name and executor:
                register_tool(tool_def, executor)
            else:
                logger.warning(f"Module {mod_name}: tool {name} has no executor")