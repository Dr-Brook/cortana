"""
JARVIS — TTS Module
Voicebox (primary) + macOS `say` (fallback). Returns audio bytes.

Built from CLAUDE.md by RJ - https://itsbrook.com
"""

import asyncio
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

import httpx

from config import VOICEBOX_URL, VOICEBOX_PROFILE

logger = logging.getLogger("jarvis.tts")

VOICEBOX_DATA_DIR = Path("/Users/rj/Library/Application Support/sh.voicebox.app/generations")


async def tts_voicebox(text: str, profile_id: str = VOICEBOX_PROFILE) -> Optional[bytes]:
    """Generate TTS audio via Voicebox API. Returns WAV bytes or None."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Request generation (must specify kokoro engine)
            resp = await client.post(
                f"{VOICEBOX_URL}/generate",
                json={"text": text, "profile_id": profile_id, "engine": "kokoro"},
            )
            resp.raise_for_status()
            gen = resp.json()
            gen_id = gen.get("id") or gen.get("generation_id")
            if not gen_id:
                logger.warning("Voicebox: no generation ID returned")
                return None

            # Poll until complete
            for _ in range(60):
                await asyncio.sleep(0.5)
                status_resp = await client.get(f"{VOICEBOX_URL}/history/{gen_id}")
                if status_resp.status_code == 200:
                    data = status_resp.json()
                    if data.get("status") == "completed":
                        audio_path = data.get("audio_path") or data.get("path", "")
                        if audio_path:
                            # Resolve relative paths against Voicebox data dir
                            full_path = Path(audio_path) if Path(audio_path).is_absolute() else VOICEBOX_DATA_DIR / Path(audio_path).name
                            if full_path.exists():
                                return full_path.read_bytes()
                            # Try downloading via API
                            dl_resp = await client.get(f"{VOICEBOX_URL}/history/{gen_id}/download")
                            if dl_resp.status_code == 200:
                                return dl_resp.content
                elif status_resp.status_code != 202:
                    break

            logger.warning("Voicebox: generation timed out")
            return None
    except Exception as e:
        logger.warning(f"Voicebox TTS failed: {e}")
        return None


async def tts_say(text: str) -> Optional[bytes]:
    """Fallback TTS using macOS `say` command. Returns AIFF bytes."""
    try:
        with tempfile.NamedTemporaryFile(suffix=".aiff", delete=False) as tmp:
            tmp_path = tmp.name
        proc = await asyncio.create_subprocess_exec(
            "say", "-o", tmp_path, text,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
        if proc.returncode == 0 and Path(tmp_path).exists():
            data = Path(tmp_path).read_bytes()
            os.unlink(tmp_path)
            return data
        return None
    except Exception as e:
        logger.warning(f"say TTS failed: {e}")
        return None


async def text_to_speech(text: str) -> Optional[bytes]:
    """TTS pipeline: Voicebox first, fallback to macOS say.
    Converts to 16kHz mono WAV for maximum browser compatibility."""
    audio = await tts_voicebox(text)
    if not audio:
        logger.info("Voicebox unavailable, falling back to macOS say")
        audio = await tts_say(text)
    if not audio:
        return None

    # Normalize to 16kHz mono WAV — iOS Safari and all browsers handle this reliably
    try:
        import subprocess
        with tempfile.NamedTemporaryFile(suffix=".in", delete=False) as tmp_in:
            tmp_in.write(audio)
            in_path = tmp_in.name
        out_path = in_path + ".wav"
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", in_path, "-ar", "16000", "-ac", "1", "-f", "wav", out_path],
            capture_output=True, timeout=10
        )
        if result.returncode == 0 and Path(out_path).exists():
            audio = Path(out_path).read_bytes()
        try:
            os.unlink(in_path)
            os.unlink(out_path)
        except OSError:
            pass
    except Exception as e:
        logger.warning(f"Audio normalization failed: {e}")

    return audio