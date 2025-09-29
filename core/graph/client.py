from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Iterable, List

from neo4j import AsyncGraphDatabase, AsyncTransaction

from core.config import settings
from core.logging import log_event
from .queries import GraphQueries

logger = logging.getLogger(__name__)


class GraphService:
    def __init__(self) -> None:
        self._driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
            max_connection_pool_size=50,
            max_transaction_retry_time=5,
        )

    async def close(self) -> None:
        await self._driver.close()

    async def ping(self) -> bool:
        async with self._driver.session() as session:
            result = await session.run("RETURN 1 AS alive")
            record = await result.single()
            return bool(record and record["alive"] == 1)

    async def _execute(self, query: str, parameters: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
        async with self._driver.session() as session:
            result = await session.run(query, parameters or {})
            return [record.data() for record in await result.to_list()]

    async def upsert_document(self, doc: Dict[str, Any]) -> None:
        await self._execute(GraphQueries.upsert_document(), {"doc_id": doc["doc_id"], "props": doc})

    async def link_document_file(self, doc_id: str, sha256: str) -> None:
        await self._execute(GraphQueries.link_document_file(), {"doc_id": doc_id, "sha256": sha256})

    async def upsert_file(self, file_props: Dict[str, Any]) -> None:
        await self._execute(
            GraphQueries.upsert_file(),
            {"sha256": file_props["sha256"], "props": file_props},
        )

    async def upsert_email(self, email_props: Dict[str, Any]) -> None:
        await self._execute(GraphQueries.upsert_email(), {"message_id": email_props["message_id"], "props": email_props})

    async def upsert_person(self, person_props: Dict[str, Any]) -> None:
        await self._execute(
            GraphQueries.upsert_person(),
            {"person_id": person_props["person_id"], "props": person_props},
        )

    async def upsert_project(self, project_props: Dict[str, Any]) -> None:
        await self._execute(
            GraphQueries.upsert_project(),
            {"project_id": project_props["project_id"], "props": project_props},
        )

    async def upsert_organization(self, org_props: Dict[str, Any]) -> None:
        await self._execute(
            GraphQueries.upsert_organization(),
            {"org_id": org_props["org_id"], "props": org_props},
        )

    async def upsert_place(self, place_props: Dict[str, Any]) -> None:
        await self._execute(
            GraphQueries.upsert_place(),
            {"place_id": place_props["place_id"], "props": place_props},
        )

    async def upsert_event(self, event_props: Dict[str, Any]) -> None:
        await self._execute(
            GraphQueries.upsert_event(),
            {"event_id": event_props["event_id"], "props": event_props},
        )

    async def upsert_image(self, image_props: Dict[str, Any]) -> None:
        await self._execute(
            GraphQueries.upsert_image(),
            {"image_id": image_props["image_id"], "props": image_props},
        )

    async def upsert_audio(self, audio_props: Dict[str, Any]) -> None:
        await self._execute(
            GraphQueries.upsert_audio(),
            {"audio_id": audio_props["audio_id"], "props": audio_props},
        )

    async def link_audio_transcript(self, audio_id: str, transcript_id: str) -> None:
        await self._execute(
            GraphQueries.link_audio_transcript(),
            {"audio_id": audio_id, "transcript_id": transcript_id},
        )

    async def link_files_near_duplicate(self, source_sha: str, target_sha: str) -> None:
        await self._execute(
            GraphQueries.link_files_near_duplicate(),
            {"source_sha": source_sha, "target_sha": target_sha},
        )

    async def link_email_person(self, message_id: str, person_id: str, relation: str) -> None:
        await self._execute(
            GraphQueries.link_email_person(relation),
            {"message_id": message_id, "person_id": person_id},
        )

    async def link_email_document(self, message_id: str, doc_id: str) -> None:
        await self._execute(
            GraphQueries.link_email_document(),
            {"message_id": message_id, "doc_id": doc_id},
        )

    async def upsert_transcript(self, transcript: Dict[str, Any]) -> None:
        await self._execute(
            GraphQueries.upsert_transcript(),
            {"transcript_id": transcript["transcript_id"], "props": transcript},
        )

    async def bm25_search(self, query: str, limit: int = 50) -> List[Dict[str, Any]]:
        records = await self._execute(GraphQueries.bm25_search(), {"query": query, "limit": limit})
        return records

    async def entity_search(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        return await self._execute(GraphQueries.entity_search(), {"query": query, "limit": limit})

    async def traverse_related(self, element_ids: Iterable[str], limit: int = 100) -> List[Dict[str, Any]]:
        return await self._execute(
            GraphQueries.match_related_entities(),
            {"element_ids": list(element_ids), "limit": limit},
        )

    async def set_block_vector(self, block_id: str, vector: List[float]) -> None:
        await self._execute(
            GraphQueries.set_block_vector(),
            {"block_id": block_id, "vector": vector},
        )

    async def link_image_file(self, image_id: str, sha256: str) -> None:
        await self._execute(
            GraphQueries.link_image_file(),
            {"image_id": image_id, "sha256": sha256},
        )

    async def run_in_transaction(self, statements: List[tuple[str, Dict[str, Any]]]) -> None:
        async with self._driver.session() as session:
            async def work(tx: AsyncTransaction) -> None:
                for cypher, params in statements:
                    await tx.run(cypher, params)

            await session.execute_write(work)

    async def ingest_document_bundle(
        self,
        document: Dict[str, Any],
        files: List[Dict[str, Any]],
        pages: List[Dict[str, Any]],
        blocks: List[Dict[str, Any]],
        relationships: List[Dict[str, Any]],
    ) -> None:
        statements: List[tuple[str, Dict[str, Any]]] = []
        statements.append((GraphQueries.upsert_document(), {"doc_id": document["doc_id"], "props": document}))
        for file_obj in files:
            statements.append((GraphQueries.upsert_file(), {"sha256": file_obj["sha256"], "props": file_obj}))
            statements.append(
                (
                    GraphQueries.link_document_file(),
                    {"doc_id": document["doc_id"], "sha256": file_obj["sha256"]},
                )
            )
        for page in pages:
            statements.append((GraphQueries.upsert_page(), {"page_id": page["page_id"], "props": page}))
            statements.append((GraphQueries.link_page_document(), {"page_id": page["page_id"], "doc_id": document["doc_id"]}))
        for block in blocks:
            statements.append((GraphQueries.upsert_block(), {"block_id": block["block_id"], "props": block}))
            statements.append((GraphQueries.link_block_page(), {"block_id": block["block_id"], "page_id": block["page_id"]}))
        for rel in relationships:
            statements.append((GraphQueries.create_document_relationships(), {"relations": [rel]}))
        await self.run_in_transaction(statements)
        log_event(logger, "graph.document_ingested", doc_id=document["doc_id"], blocks=len(blocks))


graph_service = GraphService()
