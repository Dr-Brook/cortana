"""
CORTANA — System Actions
macOS system control via AppleScript wrappers.

Built from CLAUDE.md by RJ - https://itsbrook.com
"""

import asyncio
import logging
from typing import Optional

logger = logging.getLogger("cortana.actions")


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


async def open_application(app_name: str) -> bool:
    """Open a macOS application."""
    script = f'''
    tell application "{app_name}"
        activate
    end tell
    '''
    result = await _run_applescript(script)
    return result is not None


async def set_volume(level: int) -> bool:
    """Set system volume (0-100)."""
    level = max(0, min(100, level))
    script = f'''
    set volume output volume {level}
    '''
    result = await _run_applescript(script)
    return result is not None


async def get_volume() -> int:
    """Get current system volume."""
    script = "output volume of (get volume settings)"
    result = await _run_applescript(script)
    if result:
        try:
            return int(result.strip())
        except ValueError:
            pass
    return -1


async def set_brightness(level: float) -> bool:
    """Set display brightness (0.0-1.0). Requires external brightness utility."""
    # macOS doesn't have a direct AppleScript for brightness
    # Using brightness CLI if available, otherwise fall back
    level = max(0.0, min(1.0, level))
    proc = await asyncio.create_subprocess_exec(
        "brightness", str(level),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()
    return proc.returncode == 0


async def toggle_mute() -> bool:
    """Toggle mute on/off."""
    script = '''
    set isMuted to output muted of (get volume settings)
    if isMuted then
        set volume without output muted
    else
        set volume with output muted
    end if
    '''
    result = await _run_applescript(script)
    return result is not None


async def lock_screen() -> bool:
    """Lock the screen."""
    script = '''
    tell application "System Events" to keystroke "q" using {control down}
    '''
    # Alternative: use pmset
    proc = await asyncio.create_subprocess_exec(
        "pmset", "displaysleepnow",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()
    return proc.returncode == 0


async def sleep_display() -> bool:
    """Put displays to sleep."""
    proc = await asyncio.create_subprocess_exec(
        "pmset", "displaysleepnow",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()
    return proc.returncode == 0


async def get_battery() -> dict:
    """Get battery status."""
    proc = await asyncio.create_subprocess_exec(
        "pmset", "-g", "batt",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    result = {}
    if proc.returncode == 0:
        output = stdout.decode()
        if "%" in output:
            try:
                result["percent"] = int(output.split("%")[0].strip().split()[-1])
            except (ValueError, IndexError):
                pass
        if "AC" in output:
            result["charging"] = True
        elif "Battery" in output:
            result["charging"] = False
    return result


async def tell_time() -> str:
    """Get the current time as a spoken-friendly string."""
    from datetime import datetime
    now = datetime.now()
    return now.strftime("It is %I:%M %p on %A, %B %d, %Y")


# Registry of available actions for the LLM
ACTIONS = {
    "open_app": {"func": open_application, "desc": "Open a macOS application", "args": ["app_name"]},
    "set_volume": {"func": set_volume, "desc": "Set system volume (0-100)", "args": ["level"]},
    "get_volume": {"func": get_volume, "desc": "Get current system volume", "args": []},
    "toggle_mute": {"func": toggle_mute, "desc": "Toggle mute on/off", "args": []},
    "lock_screen": {"func": lock_screen, "desc": "Lock the screen", "args": []},
    "sleep_display": {"func": sleep_display, "desc": "Put displays to sleep", "args": []},
    "get_battery": {"func": get_battery, "desc": "Get battery status", "args": []},
    "tell_time": {"func": tell_time, "desc": "Get current time", "args": []},
}