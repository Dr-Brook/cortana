"""
JARVIS — Obsidian Vault Integration
Read/write/search the Obsidian vault at ~/.openclaw/workspace/vault/.
Provides access to daily notes, MEMORY.md, and other vault content.

Built from CLAUDE.md by RJ - https://itsbrook.com
"""

import asyncio
import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from config import VAULT_DIR

logger = logging.getLogger("jarvis.obsidian")

# Vault paths
DAILY_DIR = Path(VAULT_DIR) / "Daily"
MEMORY_FILE = Path(VAULT_DIR) / "Memory" / "MEMORY.md"


def _ensure_daily_dir() -> Path:
    """Ensure the Daily directory exists."""
    DAILY_DIR.mkdir(parents=True, exist_ok=True)
    return DAILY_DIR


async def read_daily_note(date_str: Optional[str] = None) -> str:
    """Read a daily note. Defaults to today.

    Args:
        date_str: YYYY-MM-DD format, defaults to today
    """
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")

    note_path = _ensure_daily_dir() / f"{date_str}.md"
    if note_path.exists():
        return note_path.read_text(encoding="utf-8")
    return f"No daily note for {date_str}"


async def append_to_daily_note(content: str, date_str: Optional[str] = None) -> str:
    """Append content to a daily note. Creates if doesn't exist.

    Args:
        content: Text to append
        date_str: YYYY-MM-DD format, defaults to today
    """
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")

    note_path = _ensure_daily_dir() / f"{date_str}.md"

    if note_path.exists():
        existing = note_path.read_text(encoding="utf-8")
        new_content = existing.rstrip() + "\n\n" + content
    else:
        new_content = f"# {date_str}\n\n{content}"

    note_path.write_text(new_content, encoding="utf-8")
    logger.info(f"Appended to daily note: {date_str}")
    return f"Appended to {date_str}.md"


async def read_memory() -> str:
    """Read the MEMORY.md file."""
    if MEMORY_FILE.exists():
        return MEMORY_FILE.read_text(encoding="utf-8")
    return "MEMORY.md not found"


async def update_memory(section: str, content: str) -> str:
    """Update or add a section to MEMORY.md.

    If section header exists, replaces content until next header.
    If not, appends as new section.
    """
    if not MEMORY_FILE.exists():
        MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        MEMORY_FILE.write_text(f"# Long-Term Memory\n\n## {section}\n{content}\n", encoding="utf-8")
        return "Created MEMORY.md with new section"

    current = MEMORY_FILE.read_text(encoding="utf-8")
    header = f"## {section}"

    if header in current:
        # Replace existing section
        lines = current.split("\n")
        start_idx = None
        end_idx = None

        for i, line in enumerate(lines):
            if line.strip() == header:
                start_idx = i
            elif start_idx is not None and line.startswith("## ") and i > start_idx:
                end_idx = i
                break

        if start_idx is not None:
            if end_idx is None:
                end_idx = len(lines)
            new_lines = lines[:start_idx + 1] + [content] + lines[end_idx:]
            MEMORY_FILE.write_text("\n".join(new_lines), encoding="utf-8")
            return f"Updated section: {section}"
    else:
        # Append new section
        new_content = current.rstrip() + f"\n\n{header}\n{content}\n"
        MEMORY_FILE.write_text(new_content, encoding="utf-8")
        return f"Added section: {section}"


async def search_vault(query: str, limit: int = 10) -> str:
    """Search the vault using ripgrep.

    Returns matching file paths and context lines.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "rg", "-i", "--max-count", "3", "--no-heading",
            "-C", "1", query, str(VAULT_DIR),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode == 0 and stdout:
            output = stdout.decode("utf-8")
            # Limit output
            lines = output.strip().split("\n")[:limit * 3]
            return "\n".join(lines)
        elif proc.returncode == 1:
            return "No results found"
        else:
            return f"Search error: {stderr.decode('utf-8').strip()}"

    except FileNotFoundError:
        # ripgrep not installed — fallback to grep
        try:
            proc = await asyncio.create_subprocess_exec(
                "grep", "-ri", "-C", "1", query, str(VAULT_DIR),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            if stdout:
                output = stdout.decode("utf-8")
                lines = output.strip().split("\n")[:limit * 3]
                return "\n".join(lines)
            return "No results found"
        except Exception as e:
            return f"Search failed: {e}"

    except Exception as e:
        return f"Search failed: {e}"


async def read_vault_file(path: str) -> str:
    """Read a specific file from the vault.

    Args:
        path: Relative path within vault (e.g., 'Daily/2026-05-18.md')
    """
    file_path = Path(VAULT_DIR) / path
    if not file_path.exists():
        return f"File not found: {path}"
    # Safety: ensure path doesn't escape vault
    try:
        file_path.resolve().relative_to(Path(VAULT_DIR).resolve())
    except ValueError:
        return "Access denied: path outside vault"
    return file_path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Tool Registration Interface (for tools.py auto-discovery)
# ---------------------------------------------------------------------------
MODULE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_memory",
            "description": "Read JARVIS's long-term memory (MEMORY.md) or a daily note from the Obsidian vault.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "Optional date in YYYY-MM-DD format for daily note. Omit for MEMORY.md."}
                },
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_memory",
            "description": "Write to the Obsidian vault — append to today's daily note or update MEMORY.md.",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "Content to write"},
                    "section": {"type": "string", "description": "Section name for MEMORY.md. Omit for daily note."}
                },
                "required": ["content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_vault",
            "description": "Search the Obsidian vault for information using text search.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"}
                },
                "required": ["query"]
            }
        }
    },
]


async def tool_read_memory(date: str = "") -> str:
    """Read memory or daily note."""
    if date:
        return await read_daily_note(date)
    return await read_memory()


async def tool_write_memory(content: str, section: str = "") -> str:
    """Write to memory or daily note."""
    if section:
        return await update_memory(section, content)
    return await append_to_daily_note(content)


async def tool_search_vault(query: str) -> str:
    """Search vault."""
    return await search_vault(query)


MODULE_EXECUTORS = {
    "read_memory": tool_read_memory,
    "write_memory": tool_write_memory,
    "search_vault": tool_search_vault,
}