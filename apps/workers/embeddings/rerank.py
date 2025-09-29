from __future__ import annotations

import asyncio
import logging
from typing import Iterable, List, Tuple

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from core.config import settings
from apps.workers.model_manager import model_manager

logger = logging.getLogger(__name__)


class RerankerService:
    def __init__(self) -> None:
        self._primary_model = settings.reranker_model
        self._fallback_model = settings.reranker_fallback_model

    async def _load(self, name: str) -> tuple[AutoTokenizer, AutoModelForSequenceClassification]:
        async def loader() -> tuple[AutoTokenizer, AutoModelForSequenceClassification]:
            def _sync() -> tuple[AutoTokenizer, AutoModelForSequenceClassification]:
                tokenizer = AutoTokenizer.from_pretrained(name)
                model = AutoModelForSequenceClassification.from_pretrained(name)
                model.eval()
                if torch.cuda.is_available():
                    model.to("cuda")
                elif torch.backends.mps.is_available():
                    model.to("mps")
                return tokenizer, model

            return await asyncio.to_thread(_sync)

        return await model_manager.get_or_load(name, loader)

    async def _score_batch(
        self,
        tokenizer: AutoTokenizer,
        model: AutoModelForSequenceClassification,
        query: str,
        batch_pairs: List[Tuple[str, str]],
    ) -> List[float]:
        def _run() -> List[float]:
            inputs = tokenizer([[query, passage] for _, passage in batch_pairs], padding=True, truncation=True, return_tensors="pt")
            if torch.cuda.is_available():
                inputs = {k: v.to("cuda") for k, v in inputs.items()}
            elif torch.backends.mps.is_available():
                inputs = {k: v.to("mps") for k, v in inputs.items()}
            with torch.no_grad():
                logits = model(**inputs).logits.squeeze()
                scores = torch.sigmoid(logits)
            return scores.cpu().tolist()

        return await asyncio.to_thread(_run)

    async def rerank(self, query: str, candidates: Iterable[Tuple[str, str]]) -> List[Tuple[str, str, float]]:
        pairs = list(candidates)
        if not pairs:
            return []
        tokenizer, model = await self._load(self._primary_model)
        batch_size = 16
        results: List[Tuple[str, str, float]] = []
        for i in range(0, len(pairs), batch_size):
            batch = pairs[i : i + batch_size]
            try:
                scores = await self._score_batch(tokenizer, model, query, batch)
            except Exception:
                tokenizer, model = await self._load(self._fallback_model)
                scores = await self._score_batch(tokenizer, model, query, batch)
            for (doc_id, passage), score in zip(batch, scores):
                results.append((doc_id, passage, float(score)))
        results.sort(key=lambda item: item[2], reverse=True)
        return results


reranker_service = RerankerService()
