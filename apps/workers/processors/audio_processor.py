from __future__ import annotations

import asyncio
from pathlib import Path
from faster_whisper import WhisperModel

from apps.workers.model_manager import model_manager
from core.config import settings


async def _load_model() -> WhisperModel:
    async def loader() -> WhisperModel:
        def _sync() -> WhisperModel:
            device = "cpu"
            compute_type = "int8"
            return WhisperModel(settings.speech_model, device=device, compute_type=compute_type)

        return await asyncio.to_thread(_sync)

    model = await model_manager.get_or_load(settings.speech_model, loader)
    return model


async def transcribe_audio(path: Path) -> str:
    model = await _load_model()

    def _run() -> str:
        segments, _ = model.transcribe(str(path), beam_size=1)
        return " ".join(segment.text.strip() for segment in segments)

    return await asyncio.to_thread(_run)
