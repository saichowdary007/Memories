from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Dict, List

from neo4j.graph import Node

from core.cache import ValkeyClient, valkey_client
from core.graph import GraphService, graph_service
from core.vectors import LanceDBClient, lancedb_client
from apps.workers.embeddings import RerankerService, TextEmbeddingService
from apps.workers.embeddings.rerank import reranker_service
from apps.workers.embeddings.text import text_embedding_service

logger = logging.getLogger(__name__)


@dataclass
class RetrievedDocument:
    doc_id: str
    uri: str
    text: str
    score: float


class RetrievalOrchestrator:
    def __init__(
        self,
        graph: GraphService | None = None,
        vectors: LanceDBClient | None = None,
        cache: ValkeyClient | None = None,
        text_embeddings: TextEmbeddingService | None = None,
        reranker: RerankerService | None = None,
    ) -> None:
        self._graph = graph or graph_service
        self._vectors = vectors or lancedb_client
        self._cache = cache or valkey_client
        self._text_embeddings = text_embeddings or text_embedding_service
        self._reranker = reranker or reranker_service

    async def retrieve(self, query: str, top_k: int = 12) -> List[RetrievedDocument]:
        cache_key = f"ask:{query}:{top_k}"
        cached = await self._cache.get(cache_key)
        if cached:
            return [RetrievedDocument(**doc) for doc in cached]

        dense_task = asyncio.create_task(self._dense_search(query, limit=50))
        bm25_task = asyncio.create_task(self._graph.bm25_search(query, limit=50))
        entity_task = asyncio.create_task(self._graph.entity_search(query, limit=20))

        dense_results, bm25_results, entity_results = await asyncio.gather(dense_task, bm25_task, entity_task)
        entity_related = await self._entity_expand(entity_results)

        combined = self._merge_results(dense_results, bm25_results, entity_related)
        reranked = await self._rerank(query, combined)
        diversified = self._mmr(reranked, lambda_param=0.7, top_n=top_k)
        await self._cache.set(cache_key, [doc.__dict__ for doc in diversified])
        return diversified

    async def _dense_search(self, query: str, limit: int) -> List[Dict[str, Any]]:
        vectors = await self._text_embeddings.embed([query])
        if not vectors:
            return []
        return await self._vectors.search("documents", vectors[0], limit=limit)

    async def _entity_expand(self, entity_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        doc_ids: List[str] = []
        for record in entity_results:
            node = record.get("node")
            if not node:
                continue
            element_id = getattr(node, "element_id", None)
            if element_id:
                doc_ids.append(element_id)
        if not doc_ids:
            return []
        return await self._graph.traverse_related(doc_ids, limit=50)

    def _merge_results(
        self,
        dense_results: List[Dict[str, Any]],
        bm25_results: List[Dict[str, Any]],
        entity_related: List[Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        merged: Dict[str, Dict[str, Any]] = {}
        for item in dense_results:
            doc_id = item.get("doc_id") or item.get("id")
            if not doc_id:
                continue
            merged.setdefault(doc_id, {"doc_id": doc_id, "scores": [], "text": item.get("text", ""), "uri": item.get("uri", "")})
            merged[doc_id]["scores"].append(float(item.get("score", 0.0)))
        for record in bm25_results:
            node = record.get("node")
            if node is None:
                continue
            properties = self._node_to_dict(node)
            doc_id = properties.get("doc_id") or properties.get("message_id") or properties.get("page_id") or properties.get("block_id") or properties.get("id")
            merged.setdefault(doc_id, {"doc_id": doc_id, "scores": [], "text": properties.get("text_content") or properties.get("snippet", ""), "uri": properties.get("uri", "")})
            merged[doc_id]["scores"].append(float(record.get("score", 0.0)))
        for record in entity_related:
            node = record.get("m") or record.get("node") or record.get("n")
            if not node:
                continue
            properties = self._node_to_dict(node)
            doc_id = properties.get("doc_id") or properties.get("message_id") or properties.get("id")
            merged.setdefault(doc_id, {"doc_id": doc_id, "scores": [], "text": properties.get("text_content", ""), "uri": properties.get("uri", "")})
            merged[doc_id]["scores"].append(0.1)
        return merged

    async def _rerank(self, query: str, merged: Dict[str, Dict[str, Any]]) -> List[RetrievedDocument]:
        candidates = [(doc_id, payload.get("text", "")) for doc_id, payload in merged.items() if payload.get("text")]
        reranked = await self._reranker.rerank(query, candidates)
        results: List[RetrievedDocument] = []
        for doc_id, passage, score in reranked:
            payload = merged[doc_id]
            scores = payload.get("scores", [0.0])
            avg_score = sum(scores) / max(len(scores), 1)
            combined_score = (score * 0.7) + (avg_score * 0.3)
            results.append(RetrievedDocument(doc_id=doc_id, uri=payload.get("uri", ""), text=passage, score=combined_score))
        results.sort(key=lambda item: item.score, reverse=True)
        return results

    def _mmr(self, docs: List[RetrievedDocument], lambda_param: float, top_n: int) -> List[RetrievedDocument]:
        selected: List[RetrievedDocument] = []
        candidates = docs.copy()
        while candidates and len(selected) < top_n:
            if not selected:
                selected.append(candidates.pop(0))
                continue
            best_doc: RetrievedDocument | None = None
            best_score = float("-inf")
            for candidate in candidates:
                relevance = candidate.score
                diversity = max(
                    self._cosine_similarity(candidate.text, chosen.text) for chosen in selected
                )
                mmr_score = lambda_param * relevance - (1 - lambda_param) * diversity
                if mmr_score > best_score:
                    best_score = mmr_score
                    best_doc = candidate
            if best_doc:
                selected.append(best_doc)
                candidates.remove(best_doc)
            else:
                break
        return selected

    def _cosine_similarity(self, text_a: str, text_b: str) -> float:
        a_tokens = set(text_a.split())
        b_tokens = set(text_b.split())
        if not a_tokens or not b_tokens:
            return 0.0
        intersection = len(a_tokens & b_tokens)
        denom = (len(a_tokens) ** 0.5) * (len(b_tokens) ** 0.5)
        return intersection / denom

    def _node_to_dict(self, node: Node | Dict[str, Any]) -> Dict[str, Any]:
        if isinstance(node, Node):
            return dict(node)
        return node
