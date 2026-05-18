"""
CORTANA — Apple Notes Access
Read and create notes via AppleScript bridge.

Built from CLAUDE.md by RJ - https://itsbrook.com
"""

import asyncio
import logging
from typing import Optional

logger = logging.getLogger("cortana.notes")


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