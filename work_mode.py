"""
JARVIS — Work Mode Module
Persistent Claude Code session management.

Built from CLAUDE.md by RJ - https://itsbrook.com
"""

import asyncio
import logging
from typing import Optional

logger = logging.getLogger("jarvis.workmode")

_sessions: dict[str, dict] = {}  # session_name -> {process, created, last_active}


async def start_session(name: str, prompt: str = "", working_dir: str = "~") -> dict:
    """Start a persistent Claude Code session."""
    import os
    working_dir = os.path.expanduser(working_dir)
    
    proc = await asyncio.create_subprocess_exec(
        "claude", "-p", "--continue", prompt if prompt else "",
        cwd=working_dir,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    
    _sessions[name] = {
        "process": proc,
        "created": asyncio.get_event_loop().time(),
        "last_active": asyncio.get_event_loop().time(),
        "working_dir": working_dir,
    }
    
    logger.info(f"Started work session: {name}")
    return {"name": name, "status": "started", "pid": proc.pid}


async def send_to_session(name: str, message: str) -> Optional[str]:
    """Send a message to an active Claude Code session."""
    session = _sessions.get(name)
    if not session:
        return None
    
    proc = session["process"]
    if proc.returncode is not None:
        # Process ended
        _sessions.pop(name, None)
        return None
    
    try:
        proc.stdin.write(f"{message}\n".encode())
        await proc.stdin.drain()
        session["last_active"] = asyncio.get_event_loop().time()
        
        # Read response with timeout
        try:
            output = await asyncio.wait_for(proc.stdout.readline(), timeout=30.0)
            return output.decode().strip()
        except asyncio.TimeoutError:
            return "Session is processing..."
    except Exception as e:
        logger.warning(f"Error sending to session {name}: {e}")
        return None


async def end_session(name: str) -> bool:
    """End a Claude Code session."""
    session = _sessions.pop(name, None)
    if not session:
        return False
    
    proc = session["process"]
    if proc.returncode is None:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            proc.kill()
    
    logger.info(f"Ended work session: {name}")
    return True


async def list_sessions() -> list[dict]:
    """List active work sessions."""
    result = []
    for name, session in _sessions.items():
        proc = session["process"]
        result.append({
            "name": name,
            "active": proc.returncode is None,
            "pid": proc.pid,
            "working_dir": session["working_dir"],
            "last_active": session["last_active"],
        })
    return result