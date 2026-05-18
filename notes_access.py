"""
JARVIS — Apple Notes Access
Read and create notes via AppleScript bridge.

Built from CLAUDE.md by RJ - https://itsbrook.com
"""

import asyncio
import logging
from typing import Optional

logger = logging.getLogger("jarvis.notes")


async def _run_applescript(script: str) -> Optional[str]:
    """Run an AppleScript command and return output."""
    proc = await asyncio.create_subprocess_exec(
        "osascript", "-e", script,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        logger.warning(f"AppleScript error: {stderr.decode().strip()}")
        return None
    return stdout.decode().strip()


async def list_notes(limit: int = 20, folder: Optional[str] = None) -> list[dict]:
    """List notes, optionally filtered by folder."""
    folder_clause = f'folder "{folder}"' if folder else "default folder"
    script = f'''
    set output to ""
    tell application "Notes"
        set noteList to notes of {folder_clause}
        repeat with i from 1 to {limit}
            if i > (count of noteList) then exit repeat
            set n to item i of noteList
            set noteInfo to (name of n) & "|||" & (modification date of n as string) & "|||" & (body of n)
            set output to output & noteInfo & linefeed & "===NOTE_SEP===" & linefeed
        end repeat
    end tell
    return output
    '''
    result = await _run_applescript(script)
    notes = []
    if result:
        for block in result.strip().split("===NOTE_SEP==="):
            block = block.strip()
            if "|||" in block:
                parts = block.split("|||")
                notes.append({
                    "name": parts[0].strip() if len(parts) > 0 else "",
                    "modified": parts[1].strip() if len(parts) > 1 else "",
                    "body": parts[2].strip() if len(parts) > 2 else "",
                })
    return notes[:limit]


async def create_note(title: str, body: str, folder: str = "Notes") -> bool:
    """Create a new note in Apple Notes."""
    # Escape quotes in title and body
    safe_title = title.replace('"', '\\"')
    safe_body = body.replace('"', '\\"').replace("\\", "\\\\")
    script = f'''
    tell application "Notes"
        tell folder "{folder}"
            make new note with properties {{name:"{safe_title}", body:"{safe_body}"}}
        end tell
    end tell
    '''
    result = await _run_applescript(script)
    if result is not None:
        logger.info(f"Created note: {title}")
        return True
    return False


async def search_notes(query: str, limit: int = 10) -> list[dict]:
    """Search notes by name or content."""
    script = f'''
    set output to ""
    tell application "Notes"
        set foundNotes to (every note whose name contains "{query}" or body contains "{query}")
        repeat with i from 1 to {limit}
            if i > (count of foundNotes) then exit repeat
            set n to item i of foundNotes
            set noteInfo to (name of n) & "|||" & (modification date of n as string)
            set output to output & noteInfo & linefeed
        end repeat
    end tell
    return output
    '''
    result = await _run_applescript(script)
    notes = []
    if result:
        for line in result.strip().split("\n"):
            if "|||" in line:
                parts = line.split("|||")
                notes.append({
                    "name": parts[0].strip() if len(parts) > 0 else "",
                    "modified": parts[1].strip() if len(parts) > 1 else "",
                })
    return notes[:limit]

# ---------------------------------------------------------------------------
# Tool Registration Interface (for tools.py auto-discovery)
# ---------------------------------------------------------------------------
MODULE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "apple_notes",
            "description": "Access Apple Notes: list, create, and search notes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "description": "Action: list|create|search"},
                    "query": {"type": "string", "description": "Search query (for search action)"},
                    "title": {"type": "string", "description": "Note title (for create action)"},
                    "body": {"type": "string", "description": "Note body (for create action)"},
                    "limit": {"type": "integer", "description": "Max results (default 10)"}
                },
                "required": ["action"]
            }
        }
    },
]


async def tool_apple_notes(action: str, query: str = "", title: str = "",
                           body: str = "", limit: int = 10) -> str:
    """Execute a notes action."""
    if action == "list":
        notes = await list_notes(limit=limit)
        if not notes:
            return "No notes found."
        lines = []
        for n in notes:
            lines.append(f"- {n['name']} (modified: {n['modified']})")
        return "\n".join(lines)
    elif action == "create":
        if not title:
            return "Need a title to create a note"
        ok = await create_note(title, body or title)
        return f"Created note: {title}" if ok else "Failed to create note"
    elif action == "search":
        if not query:
            return "Need a search query"
        notes = await search_notes(query, limit=limit)
        if not notes:
            return f"No notes found for: {query}"
        lines = []
        for n in notes:
            lines.append(f"- {n['name']} (modified: {n['modified']})")
        return "\n".join(lines)
    else:
        return f"Unknown notes action: {action}"


MODULE_EXECUTORS = {
    "apple_notes": tool_apple_notes,
}
