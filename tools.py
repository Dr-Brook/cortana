"""
JARVIS — Unified Tool Registry
Tool definitions, executors, and execution engine. All satellite modules
are imported and registered here.

Built from CLAUDE.md by RJ - https://itsbrook.com
"""

import asyncio
import json
import logging
import os
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
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather forecast for Montgomery County, MD. Returns temperature, wind, precipitation chance, and detailed forecast for the next few days.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_news",
            "description": "Get current news headlines. Search by keyword, category, country, or language. Uses multiple free news APIs (Currents API, Google News RSS, FreeNewsApi.io, GNews).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search keyword or topic (e.g. 'technology', 'AI', 'public health')"},
                    "category": {"type": "string", "description": "News category: general, business, entertainment, health, science, sports, technology", "default": "general"},
                    "country": {"type": "string", "description": "Country code (e.g. 'us', 'gb', 'et' for Ethiopia)", "default": "us"},
                    "language": {"type": "string", "description": "Language code (e.g. 'en', 'es', 'fr')", "default": "en"},
                    "limit": {"type": "integer", "description": "Max number of articles to return", "default": 5}
                },
                "required": []
            }
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


async def tool_get_weather() -> str:
    """Fetch weather forecast from weather.gov for Montgomery County, MD."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://api.weather.gov/gridpoints/LWX/96,90/forecast",
                headers={"User-Agent": "JARVIS/1.0", "Accept": "application/geo+json"},
            )
            if resp.status_code != 200:
                return f"Weather unavailable (status {resp.status_code})"
            data = resp.json()
            periods = data.get("properties", {}).get("periods", [])[:6]
            lines = []
            for p in periods:
                name = p.get("name", "")
                temp = f"{p.get('temperature', '?')}°F"
                wind = f"{p.get('windSpeed', '?')} {p.get('windDirection', '?')}"
                short = p.get("shortForecast", "")
                precip = p.get("probabilityOfPrecipitation", {}).get("value", "?")
                lines.append(f"{name}: {temp}, {short}, wind {wind}, rain {precip}%")
            return "Montgomery County, MD forecast:\n" + "\n".join(lines)
    except Exception as e:
        return f"Weather fetch failed: {e}"


async def tool_get_news(query: str = "", category: str = "general", country: str = "us", language: str = "en", limit: int = 5) -> str:
    """Fetch news from multiple free APIs. Tries Currents API first, then GNews, then Google News RSS."""
    articles = []

    # --- Source 1: Currents API (600 req/day, 14k+ sources, no key for basic) ---
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            params = {"language": language, "country": country}
            if category != "general":
                params["category"] = category
            if query:
                params["keywords"] = query
            resp = await client.get(
                "https://api.currentsapi.services/v1/latest-news",
                params=params,
                headers={"User-Agent": "JARVIS/1.0"}
            )
            if resp.status_code == 200:
                data = resp.json()
                for a in data.get("news", [])[:limit]:
                    title = a.get("title", "")
                    desc = (a.get("description") or a.get("content") or "")[:120]
                    source = a.get("author", a.get("source", ""))
                    url = a.get("url", "")
                    published = a.get("published", "")[:10]
                    articles.append(f"• {title} ({source}, {published})\n  {desc}\n  {url}")
    except Exception as e:
        logger.warning(f"Currents API failed: {e}")

    if articles:
        header = f"📰 News{f' - {query}' if query else ''} ({category}, {country.upper()})"
        return header + "\n\n" + "\n".join(articles[:limit])

    # --- Source 2: GNews (100 req/day, requires free key) ---
    # Skipped if no key configured — fallback to RSS below

    # --- Source 3: Google News RSS (unlimited, no key) ---
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            search_q = query or category
            url = f"https://news.google.com/rss/search?q={search_q}&hl={language}&gl={country}&ceid={country}:{language}"
            resp = await client.get(url, headers={"User-Agent": "JARVIS/1.0"})
            if resp.status_code == 200:
                # Parse RSS XML
                import xml.etree.ElementTree as ET
                root = ET.fromstring(resp.text)
                for item in root.iter("item")[:limit]:
                    title = item.findtext("title", "")
                    link = item.findtext("link", "")
                    pub_date = item.findtext("pubDate", "")[:16]
                    source_el = item.find("source")
                    source_name = source_el.text if source_el is not None else ""
                    articles.append(f"• {title} ({source_name}, {pub_date})\n  {link}")
    except Exception as e:
        logger.warning(f"Google News RSS failed: {e}")

    if articles:
        header = f"📰 News{f' - {query}' if query else ''} ({category}, {country.upper()})"
        return header + "\n\n" + "\n".join(articles[:limit])

    # --- Source 4: FreeNewsApi.io (5000 req/day, requires free key) ---
    # Skipped without key — user can add FREENEWS_KEY to .env
    freenews_key = os.environ.get("FREENEWS_KEY", "")
    if freenews_key:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                params = {"apikey": freenews_key, "language": language, "country": country}
                if query:
                    params["q"] = query
                if category != "general":
                    params["category"] = category
                resp = await client.get("https://freenewsapi.io/api/v1/articles", params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    for a in data.get("articles", [])[:limit]:
                        title = a.get("title", "")
                        desc = (a.get("description") or "")[:120]
                        source = a.get("source", {}).get("name", "")
                        url = a.get("url", "")
                        articles.append(f"• {title} ({source})\n  {desc}\n  {url}")
        except Exception as e:
            logger.warning(f"FreeNewsApi failed: {e}")

    if articles:
        header = f"📰 News{f' - {query}' if query else ''} ({category}, {country.upper()})"
        return header + "\n\n" + "\n".join(articles[:limit])

    return "No news available at the moment. All sources failed."


# ---------------------------------------------------------------------------
# Tool Executor Registry
# ---------------------------------------------------------------------------
TOOL_EXECUTORS = {
    "web_search": tool_web_search,
    "delegate_task": tool_delegate_task,
    "get_current_time": tool_get_current_time,
    "get_weather": tool_get_weather,
    "get_news": tool_get_news,
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
    for mod_name in ["actions", "calendar_access", "mail_access", "notes_access", "memory", "obsidian", "browser", "work_mode"]:
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