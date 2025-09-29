from __future__ import annotations

import asyncio
import hashlib
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from PIL import Image

from apps.workers.embeddings.image import image_embedding_service
from apps.workers.embeddings.text import text_embedding_service
from apps.workers.processors.audio_processor import transcribe_audio
from apps.workers.processors.dedup import compute_phash, compute_sha256, compute_simhash, hamming_distance
from apps.workers.processors.image_processor import ocr_image
from apps.workers.processors.pdf_processor import PDFPageContent, extract_pdf_pages
from apps.workers.processors.text_processor import extract_text_from_file
from core.cache import valkey_client
from core.config import settings
from core.graph import graph_service
from core.storage import minio_storage
from core.vectors import lancedb_client


CACHE_DIR = Path.home() / ".cache" / "pkb" / "ingest"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class BlockRecord:
    block_id: str
    text: str
    page_id: Optional[str]
    uri: str
    mime_type: str
    metadata: Dict[str, Any]


class DocumentProcessor:
    def __init__(self) -> None:
        self._storage = minio_storage
        self._graph = graph_service
        self._vectors = lancedb_client
        self._cache = valkey_client

    async def process(self, payload: Dict[str, Any]) -> None:
        document = payload["document"]
        files = payload.get("files", [])
        pages: List[Dict[str, Any]] = []
        blocks: List[Dict[str, Any]] = []
        file_records: List[Dict[str, Any]] = []
        relationships: List[Dict[str, Any]] = payload.get("relationships", [])
        block_vectors: List[BlockRecord] = []
        image_embeddings: List[Dict[str, Any]] = []
        transcript_records: List[Dict[str, Any]] = []
        audio_nodes: List[Dict[str, Any]] = []

        for index, file_desc in enumerate(files):
            local_path = await self._ensure_local_file(file_desc)
            path_obj = Path(local_path)
            mime_type = file_desc.get("mime_type") or mimetypes.guess_type(path_obj.name)[0] or "application/octet-stream"
            sha256 = compute_sha256(path_obj)
            size_bytes = file_desc.get("size_bytes") or path_obj.stat().st_size
            created_at = file_desc.get("created_at") or document.get("created_at")
            object_name = f"{document['doc_id'].replace(':', '_')}/{path_obj.name}"
            remote_uri = await self._storage.upload_file(object_name, path_obj, mime_type)
            perceptual_hash = compute_phash(path_obj) if mime_type.startswith("image/") else None
            file_record = {
                "sha256": sha256,
                "uri": remote_uri,
                "mime_type": mime_type,
                "size_bytes": size_bytes,
                "perceptual_hash": perceptual_hash,
                "created_at": created_at,
            }
            file_records.append(file_record)

            page_id = f"{document['doc_id']}::page::{index}"
            page_node = {
                "page_id": page_id,
                "page_index": index,
                "preview_uri": None,
                "pooled_vector": None,
            }
            page_texts: List[str] = []

            if mime_type.startswith("text/") or mime_type in {"application/json", "application/xml"} or path_obj.suffix.lower() in {".md", ".txt", ".csv", ".log"}:
                text_content = await asyncio.to_thread(extract_text_from_file, path_obj, mime_type)
                if text_content:
                    block_id = f"{page_id}#block"
                    blocks.append(
                        {
                            "block_id": block_id,
                            "block_type": "text",
                            "bounding_box": None,
                            "text_content": text_content,
                            "text_vector": None,
                            "page_id": page_id,
                        }
                    )
                    block_vectors.append(
                        BlockRecord(
                            block_id=block_id,
                            text=text_content,
                            page_id=page_id,
                            uri=remote_uri,
                            mime_type=mime_type,
                            metadata={"sha256": sha256},
                        )
                    )
                    simhash_value = compute_simhash(text_content)
                    await self._handle_simhash_duplicates(sha256, simhash_value)
                    page_texts.append(text_content)
            elif mime_type == "application/pdf":
                pdf_pages: List[PDFPageContent] = await asyncio.to_thread(extract_pdf_pages, path_obj)
                for pdf_page in pdf_pages:
                    block_id = f"{page_id}#block#{pdf_page.page_index}"
                    blocks.append(
                        {
                            "block_id": block_id,
                            "block_type": "pdf_page",
                            "bounding_box": None,
                            "text_content": pdf_page.text,
                            "text_vector": None,
                            "page_id": page_id,
                        }
                    )
                    block_vectors.append(
                        BlockRecord(
                            block_id=block_id,
                            text=pdf_page.text,
                            page_id=page_id,
                            uri=remote_uri,
                            mime_type=mime_type,
                            metadata={"sha256": sha256, "page_index": pdf_page.page_index},
                        )
                    )
                    simhash_value = compute_simhash(pdf_page.text)
                    await self._handle_simhash_duplicates(sha256, simhash_value)
                    page_texts.append(pdf_page.text)
            elif mime_type.startswith("image/"):
                ocr_text = await asyncio.to_thread(ocr_image, path_obj)
                block_id = f"{page_id}#image"
                blocks.append(
                    {
                        "block_id": block_id,
                        "block_type": "image",
                        "bounding_box": None,
                        "text_content": ocr_text,
                        "text_vector": None,
                        "page_id": page_id,
                    }
                )
                block_vectors.append(
                    BlockRecord(
                        block_id=block_id,
                        text=ocr_text,
                        page_id=page_id,
                        uri=remote_uri,
                        mime_type=mime_type,
                        metadata={"sha256": sha256},
                    )
                )
                if ocr_text:
                    simhash_value = compute_simhash(ocr_text)
                    await self._handle_simhash_duplicates(sha256, simhash_value)
                with Image.open(path_obj) as img:
                    image_vector = await image_embedding_service.embed(img.copy())
                image_embeddings.append(
                    {
                        "id": block_id,
                        "doc_id": document["doc_id"],
                        "uri": remote_uri,
                        "vector": image_vector,
                        "mime_type": mime_type,
                    }
                )
                if perceptual_hash:
                    await self._handle_phash_duplicates(sha256, perceptual_hash)
                page_texts.append(ocr_text)
            elif mime_type.startswith("audio/"):
                transcription = await transcribe_audio(path_obj)
                transcript_id = f"{document['doc_id']}::transcript::{index}"
                transcript_records.append(
                    {
                        "transcript_id": transcript_id,
                        "text_content": transcription,
                        "text_vector": None,
                    }
                )
                block_vectors.append(
                    BlockRecord(
                        block_id=transcript_id,
                        text=transcription,
                        page_id=None,
                        uri=remote_uri,
                        mime_type=mime_type,
                        metadata={"sha256": sha256},
                    )
                )
                audio_nodes.append(
                    {
                        "audio_id": f"{document['doc_id']}::audio::{index}",
                        "recorded_at": created_at,
                        "duration_seconds": file_desc.get("duration_seconds", 0),
                        "file_uri": remote_uri,
                    }
                )
                simhash_value = compute_simhash(transcription)
                await self._handle_simhash_duplicates(sha256, simhash_value)
                page_texts.append(transcription)

            if page_texts:
                embeddings = await text_embedding_service.embed(page_texts)
                pooled = [sum(component) / len(embeddings) for component in zip(*embeddings)] if embeddings else None
                page_node["pooled_vector"] = pooled
                pages.append(page_node)
            else:
                pages.append(page_node)

        # include extra block payload
        if payload.get("block"):
            block = payload["block"]
            blocks.append({**block, "page_id": block.get("page_id")})
            block_vectors.append(
                BlockRecord(
                    block_id=block["block_id"],
                    text=block.get("text_content", ""),
                    page_id=block.get("page_id"),
                    uri=document.get("source", ""),
                    mime_type="text/plain",
                    metadata={},
                )
            )

        await self._graph.ingest_document_bundle(document, file_records, pages, blocks, relationships)

        await self._persist_vectors(document["doc_id"], block_vectors, image_embeddings)

        if payload.get("email"):
            await self._ingest_email(document, payload["email"], file_records)

        if payload.get("image"):
            image_payload = payload["image"]
            await self._graph.upsert_image(image_payload)
            for file_record in file_records:
                if file_record["mime_type"].startswith("image/"):
                    await self._graph.link_image_file(image_payload["image_id"], file_record["sha256"])
                    break

        if transcript_records:
            for transcript in transcript_records:
                await self._graph.upsert_transcript(transcript)

        for index, audio_node in enumerate(audio_nodes):
            await self._graph.upsert_audio(audio_node)
            if index < len(transcript_records):
                await self._graph.link_audio_transcript(
                    audio_node["audio_id"], transcript_records[index]["transcript_id"]
                )

        if payload.get("entities"):
            await self._ingest_entities(payload["entities"])

    async def _ensure_local_file(self, file_desc: Dict[str, Any]) -> str:
        uri = file_desc.get("uri")
        if not uri:
            raise ValueError("File descriptor missing uri")
        if uri.startswith("http://") or uri.startswith("https://"):
            return await self._download_remote(uri)
        return uri

    async def _download_remote(self, uri: str) -> str:
        headers = {}
        if "slack.com" in uri and settings.slack_bot_token:
            headers["Authorization"] = f"Bearer {settings.slack_bot_token}"
        async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
            response = await client.get(uri)
            response.raise_for_status()
            file_name = uri.split("?")[0].split("/")[-1]
            file_path = CACHE_DIR / file_name
            file_path.write_bytes(response.content)
            return str(file_path)

    async def _persist_vectors(
        self,
        doc_id: str,
        block_vectors: List[BlockRecord],
        image_embeddings: List[Dict[str, Any]],
    ) -> None:
        text_payload = []
        texts = [block.text for block in block_vectors if block.text]
        if texts:
            vectors = await text_embedding_service.embed(texts)
            vector_iter = iter(vectors)
            for block in block_vectors:
                if not block.text:
                    continue
                vector = next(vector_iter)
                text_payload.append(
                    {
                        "id": block.block_id,
                        "doc_id": doc_id,
                        "text": block.text,
                        "uri": block.uri,
                        "vector": vector,
                        "mime_type": block.mime_type,
                    }
                )
                await self._graph.set_block_vector(block.block_id, vector)
        if text_payload:
            await self._vectors.upsert_vectors("documents", text_payload, primary_key="id")
        if image_embeddings:
            await self._vectors.upsert_vectors("images", image_embeddings, primary_key="id")

    async def _handle_simhash_duplicates(self, sha256: str, simhash_value: int) -> None:
        if not simhash_value:
            return
        existing = await self._cache.raw.hgetall("dedupe:simhash")
        for other_sha, value in existing.items():
            other_value = int(value)
            if other_sha == sha256:
                continue
            if hamming_distance(simhash_value, other_value) <= 3:
                await self._graph.link_files_near_duplicate(sha256, other_sha)
        await self._cache.raw.hset("dedupe:simhash", sha256, str(simhash_value))

    async def _handle_phash_duplicates(self, sha256: str, phash_value: str) -> None:
        existing = await self._cache.raw.hgetall("dedupe:phash")
        phash_int = int(phash_value, 16)
        for other_sha, value in existing.items():
            if other_sha == sha256:
                continue
            distance = hamming_distance(phash_int, int(value, 16))
            if distance <= 6:
                await self._graph.link_files_near_duplicate(sha256, other_sha)
        await self._cache.raw.hset("dedupe:phash", sha256, phash_value)

    async def _ingest_email(self, document: Dict[str, Any], email_payload: Dict[str, Any], file_records: List[Dict[str, Any]]) -> None:
        message_id = email_payload["message_id"]
        await self._graph.upsert_email({**email_payload, "message_id": message_id})
        await self._graph.link_email_document(message_id, document["doc_id"])
        people = []
        for address in [email_payload.get("sender"), *(email_payload.get("recipients") or [])]:
            if not address:
                continue
            person_id = self._person_id(address)
            await self._graph.upsert_person({"person_id": person_id, "full_name": address.split("@")[0], "email_addresses": [address]})
            relation = "sent_by" if address == email_payload.get("sender") else "received_by"
            await self._graph.link_email_person(message_id, person_id, relation)
            people.append(person_id)

    def _person_id(self, identifier: str) -> str:
        return f"person:{hashlib.sha256(identifier.lower().encode()).hexdigest()[:16]}"

    async def _ingest_entities(self, entities: Dict[str, Any]) -> None:
        for person in entities.get("people", []):
            identifier = person if isinstance(person, str) else person.get("email")
            if not identifier:
                continue
            person_id = self._person_id(identifier)
            await self._graph.upsert_person(
                {
                    "person_id": person_id,
                    "full_name": identifier.split("@")[0],
                    "email_addresses": [identifier],
                }
            )
        for org in entities.get("organizations", []):
            org_name = org if isinstance(org, str) else org.get("name")
            if not org_name:
                continue
            org_id = f"org:{hashlib.sha256(org_name.lower().encode()).hexdigest()[:16]}"
            await self._graph.upsert_organization({"org_id": org_id, "org_name": org_name})
        for project in entities.get("projects", []):
            project_name = project if isinstance(project, str) else project.get("name")
            if not project_name:
                continue
            project_id = f"project:{hashlib.sha256(project_name.lower().encode()).hexdigest()[:16]}"
            tags = project.get("tags") if isinstance(project, dict) else []
            await self._graph.upsert_project({"project_id": project_id, "project_name": project_name, "tags": tags})
        for place in entities.get("places", []):
            place_name = place if isinstance(place, str) else place.get("name")
            if not place_name:
                continue
            place_id = f"place:{hashlib.sha256(place_name.lower().encode()).hexdigest()[:16]}"
            geo = place.get("geo_coordinates") if isinstance(place, dict) else None
            await self._graph.upsert_place({"place_id": place_id, "place_name": place_name, "geo_coordinates": geo})
        for event in entities.get("events", []):
            if not isinstance(event, dict):
                continue
            event_id = event.get("event_id") or f"event:{hashlib.sha256(event.get('title', '').encode()).hexdigest()[:16]}"
            await self._graph.upsert_event(event | {"event_id": event_id})
