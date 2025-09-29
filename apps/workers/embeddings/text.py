from __future__ import annotations

import asyncio
import logging
from typing import Iterable, List

import torch
from transformers import AutoModel, AutoTokenizer

from core.config import settings
from core.system.memory import memory_guard
from apps.workers.model_manager import model_manager

logger = logging.getLogger(__name__)


class TextEmbeddingService:
    def __init__(self) -> None:
        self._model_name = settings.embeddings_model

    async def _load(self) -> tuple[AutoTokenizer, AutoModel]:
        async def loader() -> tuple[AutoTokenizer, AutoModel]:
            def _load_sync() -> tuple[AutoTokenizer, AutoModel]:
                tokenizer = AutoTokenizer.from_pretrained(self._model_name)
                model = AutoModel.from_pretrained(self._model_name)
                model.eval()
                if torch.cuda.is_available():
                    model.to("cuda")
                elif torch.backends.mps.is_available():
                    model.to("mps")
                return tokenizer, model

            return await asyncio.to_thread(_load_sync)

        tokenizer, model = await model_manager.get_or_load(self._model_name, loader)
        return tokenizer, model

    async def embed(self, texts: Iterable[str]) -> List[List[float]]:
        tokenizer, model = await self._load()
        batches: List[List[float]] = []
        batch: List[str] = []
        batch_size = 8
        for text in texts:
            batch.append(text)
            if len(batch) >= batch_size:
                batches.extend(await self._embed_batch(batch, tokenizer, model, batch_size))
                batch = []
                if memory_guard.is_under_pressure():
                    batch_size = max(2, batch_size // 2)
        if batch:
            batches.extend(await self._embed_batch(batch, tokenizer, model, batch_size))
        return batches

    async def _embed_batch(
        self,
        texts: List[str],
        tokenizer: AutoTokenizer,
        model: AutoModel,
        batch_size: int,
    ) -> List[List[float]]:
        async def _forward(batch_texts: List[str]) -> List[List[float]]:
            def _run() -> List[List[float]]:
                inputs = tokenizer(batch_texts, padding=True, truncation=True, return_tensors="pt")
                if torch.cuda.is_available():
                    inputs = {k: v.to("cuda") for k, v in inputs.items()}
                elif torch.backends.mps.is_available():
                    inputs = {k: v.to("mps") for k, v in inputs.items()}
                with torch.no_grad():
                    outputs = model(**inputs)
                    embeddings = outputs.last_hidden_state[:, 0]
                    embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)
                return embeddings.cpu().tolist()

            return await asyncio.to_thread(_run)

        return await _forward(texts)


text_embedding_service = TextEmbeddingService()
