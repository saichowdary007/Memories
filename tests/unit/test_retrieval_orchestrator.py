import asyncio
from typing import Any, Dict, List

import pytest

from apps.api.services.retrieval import RetrievalOrchestrator, RetrievedDocument


class FakeGraph:
    async def bm25_search(self, query: str, limit: int = 50) -> List[Dict[str, Any]]:
        return [{"node": {"doc_id": "doc-1", "text_content": "Alpha details"}, "score": 0.7}]

    async def entity_search(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        return []

    async def traverse_related(self, doc_ids, limit: int = 50):
        return []


class FakeVectors:
    async def search(self, table_name: str, vector: List[float], limit: int = 20, filters=None):
        return [{"doc_id": "doc-1", "text": "Project Alpha", "score": 0.9, "uri": "minio://alpha"}]


class FakeCache:
    def __init__(self) -> None:
        self.store: Dict[str, Any] = {}

    async def get(self, key: str):
        return self.store.get(key)

    async def set(self, key: str, value: Any, ttl_seconds: int = 86400):
        self.store[key] = value


class FakeTextEmbeddings:
    async def embed(self, texts):
        return [[0.1, 0.2, 0.3, 0.4] for _ in texts]


class FakeReranker:
    async def rerank(self, query: str, candidates):
        return [(doc_id, text, 0.95) for doc_id, text in candidates]


@pytest.mark.asyncio
async def test_retrieval_orchestrator(monkeypatch):
    orchestrator = RetrievalOrchestrator(
        graph=FakeGraph(),
        vectors=FakeVectors(),
        cache=FakeCache(),
        text_embeddings=FakeTextEmbeddings(),
        reranker=FakeReranker(),
    )

    results = await orchestrator.retrieve("Project Alpha details", top_k=1)
    assert results
    doc = results[0]
    assert isinstance(doc, RetrievedDocument)
    assert doc.doc_id == "doc-1"
    assert doc.score > 0
