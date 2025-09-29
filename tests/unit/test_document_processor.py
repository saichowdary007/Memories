import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import pytest

from apps.workers.processors.document_processor import DocumentProcessor


class FakeStorage:
    async def upload_file(self, object_name: str, path: Path, mime_type: str, tags: Dict[str, str] | None = None) -> str:
        return f"minio://bucket/{object_name}"


class FakeGraph:
    def __init__(self) -> None:
        self.documents: List[Dict[str, Any]] = []
        self.files: List[Dict[str, Any]] = []
        self.blocks: List[Dict[str, Any]] = []

    async def ingest_document_bundle(self, document, files, pages, blocks, relationships):
        self.documents.append(document)
        self.files.extend(files)
        self.blocks.extend(blocks)

    async def upsert_email(self, email_props):
        return None

    async def link_email_document(self, message_id: str, doc_id: str) -> None:
        return None

    async def upsert_person(self, person_props):
        return None

    async def link_email_person(self, message_id: str, person_id: str, relation: str) -> None:
        return None

    async def upsert_image(self, image_props):
        return None

    async def link_image_file(self, image_id: str, sha256: str) -> None:
        return None

    async def upsert_transcript(self, transcript):
        return None

    async def upsert_audio(self, audio_props):
        return None

    async def link_audio_transcript(self, audio_id: str, transcript_id: str):
        return None

    async def set_block_vector(self, block_id: str, vector: List[float]) -> None:
        return None

    async def upsert_project(self, project_props):
        return None

    async def upsert_organization(self, org_props):
        return None

    async def upsert_place(self, place_props):
        return None

    async def upsert_event(self, event_props):
        return None


class FakeVectors:
    def __init__(self) -> None:
        self.tables: Dict[str, List[Dict[str, Any]]] = {}

    async def upsert_vectors(self, table_name: str, records: List[Dict[str, Any]], primary_key: str = "id") -> None:
        self.tables.setdefault(table_name, []).extend(records)


class FakeTextEmbeddings:
    async def embed(self, texts):
        return [[0.1 for _ in range(4)] for _ in texts]


class FakeImageEmbeddings:
    async def embed(self, image):
        return [0.2 for _ in range(4)]


class FakeValkey:
    def __init__(self) -> None:
        self.store: Dict[str, Dict[str, str]] = {}

    @property
    def raw(self):
        return self

    async def hgetall(self, key: str) -> Dict[str, str]:
        return self.store.get(key, {})

    async def hset(self, key: str, field: str, value: str) -> None:
        self.store.setdefault(key, {})[field] = value


@pytest.mark.asyncio
async def test_document_processor_handles_text(tmp_path, monkeypatch):
    from apps.workers.processors import document_processor as module

    file_path = tmp_path / "alpha.md"
    file_path.write_text("Project Alpha kickoff meeting notes", encoding="utf-8")

    fake_storage = FakeStorage()
    fake_graph = FakeGraph()
    fake_vectors = FakeVectors()
    fake_valkey = FakeValkey()

    monkeypatch.setattr(module, "minio_storage", fake_storage)
    monkeypatch.setattr(module, "graph_service", fake_graph)
    monkeypatch.setattr(module, "lancedb_client", fake_vectors)
    monkeypatch.setattr(module, "text_embedding_service", FakeTextEmbeddings())
    monkeypatch.setattr(module, "image_embedding_service", FakeImageEmbeddings())
    monkeypatch.setattr(module, "valkey_client", fake_valkey)

    processor = DocumentProcessor()

    payload = {
        "document": {
            "doc_id": "seed:doc",
            "version": "1",
            "title": "Seed Doc",
            "source": "seed",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "valid_from": datetime.now(timezone.utc).isoformat(),
            "valid_to": None,
            "system_from": datetime.now(timezone.utc).isoformat(),
            "system_to": None,
        },
        "files": [
            {
                "uri": str(file_path),
                "mime_type": "text/markdown",
                "size_bytes": file_path.stat().st_size,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        ],
        "entities": {"projects": ["Project Alpha"]},
    }

    await processor.process(payload)

    assert fake_graph.documents
    assert fake_vectors.tables["documents"]
    assert fake_valkey.store["dedupe:simhash"]
