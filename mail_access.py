"""
JARVIS — Apple Mail Access
Read-only mail access via AppleScript bridge.

Built from CLAUDE.md by RJ - https://itsbrook.com
"""

import asyncio
import logging
from typing import Optional

logger = logging.getLogger("jarvis.mail")


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


async def get_unread_count() -> int:
    """Get count of unread emails across all accounts."""
    script = '''
    tell application "Mail"
        set unreadCount to 0
        repeat with acct in accounts
            repeat with mb in mailboxes of acct
                set unreadCount to unreadCount + (count of messages in mb whose read status is false)
            end repeat
        end repeat
        return unreadCount
    end tell
    '''
    result = await _run_applescript(script)
    if result:
        try:
            return int(result.strip())
        except ValueError:
            pass
    return 0


async def get_recent_messages(limit: int = 10, account: Optional[str] = None) -> list[dict]:
    """Get recent email messages (read-only)."""
    acct_clause = f'account "{account}"' if account else "accounts"
    script = f'''
    set output to ""
    tell application "Mail"
        repeat with acct in {acct_clause}
            repeat with mb in mailboxes of acct
                set msgs to (messages of mb whose read status is false)
                repeat with i from 1 to {limit}
                    if i > (count of msgs) then exit repeat
                    set m to item i of msgs
                    set msgInfo to (subject of m) & "|||" & (sender of m) & "|||" & (date received of m as string) & "|||" & (content of m)
                    set output to output & msgInfo & linefeed & "===MSG_SEP===" & linefeed
                end repeat
            end repeat
        end repeat
    end tell
    return output
    '''
    result = await _run_applescript(script)
    messages = []
    if result:
        for block in result.strip().split("===MSG_SEP==="):
            block = block.strip()
            if "|||" in block:
                parts = block.split("|||")
                messages.append({
                    "subject": parts[0].strip() if len(parts) > 0 else "",
                    "sender": parts[1].strip() if len(parts) > 1 else "",
                    "date": parts[2].strip() if len(parts) > 2 else "",
                    "content": parts[3].strip() if len(parts) > 3 else "",
                })
    return messages[:limit]


async def search_emails(query: str, limit: int = 10) -> list[dict]:
    """Search emails by subject or content."""
    script = f'''
    set output to ""
    tell application "Mail"
        set searchResults to (every message of accounts whose subject contains "{query}" or content contains "{query}")
        repeat with i from 1 to {limit}
            if i > (count of searchResults) then exit repeat
            set m to item i of searchResults
            set msgInfo to (subject of m) & "|||" & (sender of m) & "|||" & (date received of m as string)
            set output to output & msgInfo & linefeed & "===MSG_SEP===" & linefeed
        end repeat
    end tell
    return output
    '''
    result = await _run_applescript(script)
    messages = []
    if result:
        for block in result.strip().split("===MSG_SEP==="):
            block = block.strip()
            if "|||" in block:
                parts = block.split("|||")
                messages.append({
                    "subject": parts[0].strip() if len(parts) > 0 else "",
                    "sender": parts[1].strip() if len(parts) > 1 else "",
                    "date": parts[2].strip() if len(parts) > 2 else "",
                })
    return messages[:limit]