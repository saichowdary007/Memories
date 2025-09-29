from __future__ import annotations

import logging
from typing import Dict, List

import httpx

from core.config import settings
from core.logging import log_event

logger = logging.getLogger(__name__)


class LLMService:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(base_url=settings.ollama_host, timeout=60.0)
        self._model = settings.llm_model

    async def generate(
        self,
        query: str,
        context_documents: List[Dict[str, Any]],
        stream: bool = False,
    ) -> str:
        prompt = self._build_prompt(query, context_documents)
        payload: Dict[str, object] = {
            "model": self._model,
            "prompt": prompt,
            "options": {
                "temperature": 0.2,
                "top_p": 0.9,
                "num_ctx": 4096,
            },
            "stream": stream,
        }
        if stream:
            async with self._client.stream("POST", "/api/generate", json=payload) as response:
                response.raise_for_status()
                chunks: List[str] = []
                async for piece in response.aiter_text():
                    chunks.append(piece)
                return "".join(chunks)
        response = await self._client.post("/api/generate", json=payload)
        response.raise_for_status()
        data = response.json()
        log_event(logger, "llm.response", tokens=data.get("eval_count", 0))
        return data["response"]

    def _build_prompt(self, query: str, documents: List[Dict[str, Any]]) -> str:
        context_sections = []
        for idx, doc in enumerate(documents, start=1):
            citation = doc.get("uri", "unknown")
            snippet = doc.get("text", "")
            context_sections.append(f"[{idx}] Source: {citation}\n{snippet}")
        context_block = "\n\n".join(context_sections)
        instructions = (
            "You are a privacy-focused assistant. Answer using only the provided documents. "
            "Cite sources using [number] references. If unsure, say you cannot find the answer."
        )
        return f"{instructions}\n\nQuestion: {query}\n\nContext:\n{context_block}\n\nAnswer:"

    async def close(self) -> None:
        await self._client.aclose()
