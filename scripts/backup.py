from __future__ import annotations

import asyncio
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from minio import Minio
from neo4j import AsyncGraphDatabase
from redis.asyncio import Redis

from core.config import settings


BACKUP_ROOT = Path(settings.backup_path).expanduser()
BACKUP_ROOT.mkdir(parents=True, exist_ok=True)


PRIMARY_KEYS = {
    "Document": "doc_id",
    "File": "sha256",
    "Email": "message_id",
    "Page": "page_id",
    "Block": "block_id",
    "Image": "image_id",
    "Audio": "audio_id",
    "Transcript": "transcript_id",
    "Person": "person_id",
    "Organization": "org_id",
    "Project": "project_id",
    "Event": "event_id",
    "Place": "place_id",
}


def _primary_reference(labels: List[str], properties: Dict[str, Any]) -> Dict[str, str] | None:
    for label in labels:
        key = PRIMARY_KEYS.get(label)
        if key and key in properties:
            return {"label": label, "key": key, "value": properties[key]}
    return None


async def export_neo4j(target: Path) -> None:
    driver = AsyncGraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password))
    async with driver.session() as session:
        node_result = await session.run("MATCH (n) RETURN elementId(n) AS id, labels(n) AS labels, properties(n) AS properties")
        nodes: List[Dict[str, Any]] = []
        primary_map: Dict[str, Dict[str, str]] = {}
        for record in await node_result.to_list():
            data = record.data()
            primary = _primary_reference(data["labels"], data["properties"])
            if primary:
                primary_map[data["id"]] = primary
            nodes.append({"labels": data["labels"], "properties": data["properties"], "primary": primary})
        rel_result = await session.run(
            "MATCH (a)-[r]->(b) RETURN type(r) AS type, properties(r) AS properties, elementId(a) AS start, elementId(b) AS end"
        )
        rels: List[Dict[str, Any]] = []
        for record in await rel_result.to_list():
            data = record.data()
            rels.append(
                {
                    "type": data["type"],
                    "properties": data["properties"],
                    "start": primary_map.get(data["start"]),
                    "end": primary_map.get(data["end"]),
                }
            )
    await driver.close()
    (target / "neo4j.json").write_text(json.dumps({"nodes": nodes, "relationships": rels}, indent=2))


def export_lancedb(target: Path) -> None:
    source = Path(settings.lancedb_uri)
    if not source.exists():
        return
    shutil.make_archive(str(target / "lancedb"), "zip", root_dir=source)


def export_minio(target: Path) -> None:
    client = Minio(
        endpoint=settings.minio_endpoint.replace("http://", "").replace("https://", ""),
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )
    bucket = settings.minio_bucket
    objects = client.list_objects(bucket, recursive=True)
    artifact_dir = target / "minio"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    for obj in objects:
        data = client.get_object(bucket, obj.object_name)
        file_path = artifact_dir / obj.object_name
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "wb") as fh:
            shutil.copyfileobj(data, fh)
        data.close()
        data.release_conn()


async def export_valkey(target: Path) -> None:
    client = Redis(host=settings.valkey_host, port=settings.valkey_port, decode_responses=True)
    cursor = "0"
    snapshot: Dict[str, Any] = {}
    while True:
        cursor, keys = await client.scan(cursor=cursor, count=100)
        for key in keys:
            key_type = await client.type(key)
            if key_type == "string":
                snapshot[key] = await client.get(key)
            elif key_type == "hash":
                snapshot[key] = await client.hgetall(key)
            elif key_type == "list":
                snapshot[key] = await client.lrange(key, 0, -1)
            elif key_type == "set":
                snapshot[key] = list(await client.smembers(key))
            elif key_type == "zset":
                snapshot[key] = await client.zrange(key, 0, -1, withscores=True)
        if cursor == "0":
            break
    await client.close()
    (target / "valkey.json").write_text(json.dumps(snapshot, indent=2))


async def main() -> None:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = BACKUP_ROOT / timestamp
    target.mkdir(parents=True, exist_ok=True)

    await export_neo4j(target)
    export_lancedb(target)
    export_minio(target)
    await export_valkey(target)

    metadata = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "neo4j_uri": settings.neo4j_uri,
        "lancedb_uri": settings.lancedb_uri,
        "minio_bucket": settings.minio_bucket,
    }
    (target / "metadata.json").write_text(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
