"""
JARVIS — Apple Calendar Access
Read and create calendar events via AppleScript bridge.

Built from CLAUDE.md by RJ - https://itsbrook.com
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger("jarvis.calendar")

# Cache
_cache: dict = {"events": [], "last_refresh": 0}
_CACHE_TTL = 300  # 5 minutes


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


async def list_calendars() -> list[str]:
    """List all available calendar names."""
    script = '''
    tell application "Calendar"
        set calNames to {}
        repeat with c in calendars
            set end of calNames to name of c
        end repeat
        return calNames
    end tell
    '''
    result = await _run_applescript(script)
    if result:
        # Parse AppleScript list output
        return [name.strip() for name in result.split(",") if name.strip()]
    return []


async def get_upcoming_events(days: int = 7, calendar_name: Optional[str] = None) -> list[dict]:
    """Get upcoming calendar events."""
    cal_filter = ""
    if calendar_name:
        cal_filter = f'calendar "{calendar_name}"'

    script = f'''
    set output to ""
    set currentDate to current date
    set endDate to currentDate + ({days} * days)
    tell application "Calendar"
        repeat with evt in (every event of {cal_filter if cal_filter else "calendars"} whose start date >= currentDate and start date <= endDate)
            set evtInfo to (summary of evt) & "|||" & (start date of evt as string) & "|||" & (end date of evt as string) & "|||" & (location of evt) & "|||" & (description of evt)
            set output to output & evtInfo & linefeed
        end repeat
    end tell
    return output
    '''
    result = await _run_applescript(script)
    events = []
    if result:
        for line in result.strip().split("\n"):
            if "|||" in line:
                parts = line.split("|||")
                events.append({
                    "summary": parts[0].strip() if len(parts) > 0 else "",
                    "start": parts[1].strip() if len(parts) > 1 else "",
                    "end": parts[2].strip() if len(parts) > 2 else "",
                    "location": parts[3].strip() if len(parts) > 3 else "",
                    "description": parts[4].strip() if len(parts) > 4 else "",
                })
    return events


async def create_event(
    summary: str,
    start_date: str,
    end_date: str,
    location: str = "",
    description: str = "",
    calendar_name: str = "Calendar",
) -> bool:
    """Create a new calendar event via AppleScript."""
    script = f'''
    tell application "Calendar"
        tell calendar "{calendar_name}"
            make new event with properties {{summary:"{summary}", start date:date "{start_date}", end date:date "{end_date}", location:"{location}", description:"{description}"}}
        end tell
    end tell
    '''
    result = await _run_applescript(script)
    return result is not None


async def refresh_cache():
    """Background cache refresh."""
    global _cache
    now = datetime.now().timestamp()
    if now - _cache["last_refresh"] < _CACHE_TTL:
        return
    _cache["events"] = await get_upcoming_events(days=7)
    _cache["last_refresh"] = now
    logger.info(f"Calendar cache refreshed: {len(_cache['events'])} events")


async def get_cached_events() -> list[dict]:
    """Get events from cache, refreshing if needed."""
    await refresh_cache()
    return _cache["events"]

# ---------------------------------------------------------------------------
# Tool Registration Interface (for tools.py auto-discovery)
# ---------------------------------------------------------------------------
MODULE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "calendar",
            "description": "Access Apple Calendar: list upcoming events, create events.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "description": "Action: list_events|create_event|list_calendars"},
                    "days": {"type": "integer", "description": "Days ahead to look (default 7)"},
                    "summary": {"type": "string", "description": "Event title (for create_event)"},
                    "start_date": {"type": "string", "description": "Start date/time (for create_event)"},
                    "end_date": {"type": "string", "description": "End date/time (for create_event)"},
                    "location": {"type": "string", "description": "Event location (for create_event)"}
                },
                "required": ["action"]
            }
        }
    },
]


async def tool_calendar(action: str, days: int = 7, summary: str = "",
                        start_date: str = "", end_date: str = "",
                        location: str = "") -> str:
    """Execute a calendar action."""
    if action == "list_events":
        events = await get_upcoming_events(days=days)
        if not events:
            return "No upcoming events."
        lines = []
        for e in events:
            line = f"- {e['summary']} | {e['start']}"
            if e.get("location"):
                line += f" | {e['location']}"
            lines.append(line)
        return "\n".join(lines)
    elif action == "list_calendars":
        cals = await list_calendars()
        return "Calendars: " + ", ".join(cals) if cals else "No calendars found"
    elif action == "create_event":
        if not summary or not start_date:
            return "Need summary and start_date to create event"
        ok = await create_event(summary, start_date, end_date or start_date, location=location)
        return f"Created event: {summary}" if ok else "Failed to create event"
    else:
        return f"Unknown calendar action: {action}"


MODULE_EXECUTORS = {
    "calendar": tool_calendar,
}
