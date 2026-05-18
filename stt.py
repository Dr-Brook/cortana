"""
JARVIS — STT Module
Speech-to-text using faster-whisper (CTranslate2 backend) for low-latency
local transcription on Apple Silicon.

Built from CLAUDE.md by RJ - https://itsbrook.com
"""

import asyncio
import logging
import tempfile
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger("jarvis.stt")

# Lazy-loaded model (avoids startup delay)
_model = None


def _get_model():
    """Lazy-load faster-whisper model. Downloads on first use."""
    global _model
    if _model is None:
        try:
            from faster_whisper import WhisperModel
            logger.info("Loading faster-whisper model (base)...")
            _model = WhisperModel("base", device="cpu", compute_type="int8")
            logger.info("faster-whisper model loaded")
        except Exception as e:
            logger.error(f"Failed to load faster-whisper: {e}")
            raise
    return _model


async def transcribe_audio(audio_data: bytes) -> Optional[str]:
    """Transcribe audio bytes using faster-whisper.

    Accepts WAV or raw audio. Returns transcript text or None.
    Runs transcription in a thread pool to avoid blocking the event loop.
    Optionally uses Silero VAD to strip silence before transcription.
    """
    try:
        # Try VAD preprocessing to strip silence
        try:
            from vad import async_extract_speech
            speech_audio = await async_extract_speech(audio_data)
            if speech_audio and len(speech_audio) > 0:
                audio_data = speech_audio
            else:
                # No speech detected
                logger.info("VAD: no speech detected in audio")
                return None
        except ImportError:
            logger.debug("VAD module not available, transcribing full audio")
        except Exception as e:
            logger.warning(f"VAD preprocessing failed, transcribing full audio: {e}")

        model = _get_model()

        # Write audio to temp file for faster-whisper
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(audio_data)
            tmp_path = tmp.name

        # Run transcription in thread pool (CPU-bound)
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _transcribe_file, tmp_path)

        # Cleanup
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

        return result

    except Exception as e:
        logger.warning(f"STT transcription failed: {e}")
        return None


def _transcribe_file(filepath: str) -> Optional[str]:
    """Synchronous transcription — called from thread pool."""
    try:
        model = _get_model()
        segments, info = model.transcribe(filepath, beam_size=5, language="en")
        text = " ".join(segment.text.strip() for segment in segments)
        if text:
            logger.info(f"Transcribed: {text[:100]}...")
            return text
        return None
    except Exception as e:
        logger.warning(f"Transcription error: {e}")
        return None


async def transcribe_with_vad(audio_data: bytes, vad_segments: list[dict] = None) -> Optional[str]:
    """Transcribe audio with optional VAD pre-processing.

    If vad_segments provided, only transcribe the speech segments.
    vad_segments format: [{"start": 0.0, "end": 2.5}, ...]
    """
    if vad_segments:
        # Filter audio to speech segments only
        # For now, transcribe the whole thing — VAD filtering
        # will be enhanced when Silero VAD is integrated
        pass

    return await transcribe_audio(audio_data)