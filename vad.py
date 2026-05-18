"""
JARVIS — VAD Module
Silero VAD for voice activity detection. Server-side preprocessing
strips silence before Whisper transcription. Can also detect speech
end for auto-stop recording.

Built from CLAUDE.md by RJ - https://itsbrook.com
"""

import asyncio
import logging
from typing import Optional

import numpy as np

logger = logging.getLogger("jarvis.vad")

# Lazy-loaded model
_vad_model = None


def _get_vad_model():
    """Lazy-load Silero VAD model."""
    global _vad_model
    if _vad_model is None:
        try:
            import torch
            model, utils = torch.hub.load(
                repo_or_dir="snakers4/silero-vad",
                model="silero_vad",
                trust_repo=True,
            )
            _vad_model = (model, utils)
            logger.info("Silero VAD model loaded")
        except Exception as e:
            logger.error(f"Failed to load Silero VAD: {e}")
            raise
    return _vad_model


def detect_speech(audio_data: bytes, sample_rate: int = 16000) -> dict:
    """Detect speech segments in audio data.

    Returns dict with:
      - has_speech: bool
      - speech_segments: list of (start_sec, end_sec)
      - speech_ratio: float (0-1, fraction of audio that is speech)
    """
    try:
        model, utils = _get_vad_model()
        (get_speech_timestamps, _, read_audio, _, _) = utils

        # Convert bytes to tensor
        # Silero expects 16kHz mono audio
        audio_tensor = read_audio(audio_data, sampling_rate=sample_rate)

        # Get speech timestamps
        speech_timestamps = get_speech_timestamps(
            audio_tensor,
            model,
            sampling_rate=sample_rate,
            threshold=0.5,
            min_speech_duration_ms=250,
            min_silence_duration_ms=100,
        )

        # Convert sample indices to seconds
        segments = []
        for ts in speech_timestamps:
            start_sec = ts["start"] / sample_rate
            end_sec = ts["end"] / sample_rate
            segments.append((start_sec, end_sec))

        total_duration = len(audio_tensor) / sample_rate
        speech_duration = sum(end - start for start, end in segments)
        speech_ratio = speech_duration / total_duration if total_duration > 0 else 0

        return {
            "has_speech": len(segments) > 0,
            "speech_segments": segments,
            "speech_ratio": speech_ratio,
        }

    except Exception as e:
        logger.warning(f"VAD detection failed: {e}")
        # If VAD fails, assume all audio is speech (safe fallback)
        return {
            "has_speech": True,
            "speech_segments": [],
            "speech_ratio": 1.0,
        }


def extract_speech_audio(audio_data: bytes, sample_rate: int = 16000) -> bytes:
    """Extract only speech segments from audio, stripping silence.

    Returns the audio data containing only speech segments.
    """
    try:
        model, utils = _get_vad_model()
        (get_speech_timestamps, _, read_audio, save_audio, _) = utils

        audio_tensor = read_audio(audio_data, sampling_rate=sample_rate)
        speech_timestamps = get_speech_timestamps(
            audio_tensor, model,
            sampling_rate=sample_rate,
            threshold=0.5,
        )

        if not speech_timestamps:
            # No speech detected
            return b""

        # Concatenate speech segments
        import torch
        speech_chunks = []
        for ts in speech_timestamps:
            speech_chunks.append(audio_tensor[ts["start"]:ts["end"]])

        speech_audio = torch.cat(speech_chunks)

        # Convert back to bytes (16-bit PCM)
        import io
        import wave
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(sample_rate)
            wf.writeframes((speech_audio.numpy() * 32767).astype(np.int16).tobytes())
        return buf.getvalue()

    except Exception as e:
        logger.warning(f"VAD extraction failed: {e}")
        return audio_data  # Return original if VAD fails


async def async_detect_speech(audio_data: bytes, sample_rate: int = 16000) -> dict:
    """Async wrapper for detect_speech (runs in thread pool)."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, detect_speech, audio_data, sample_rate)


async def async_extract_speech(audio_data: bytes, sample_rate: int = 16000) -> bytes:
    """Async wrapper for extract_speech_audio (runs in thread pool)."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, extract_speech_audio, audio_data, sample_rate)