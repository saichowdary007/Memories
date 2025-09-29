from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from typing import Any, Dict

from minio import Minio
from neo4j import AsyncGraphDatabase
from redis.asyncio import Redis

from core.config import settings


BACKUP_ROOT = Path(settings.backup_path).expanduser()


async def restore_neo4j(source: Path) -> None:
    data_path = source / "neo4j.json"
    if not data_path.exists():
        return
    payload = json.loads(data_path.read_text())
    driver = AsyncGraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password))
    async with driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
        for node in payload.get("nodes", []):
            labels = ":".join(node["labels"])
            properties = node["properties"]
            primary = node.get("primary")
            if primary:
                cypher = f"MERGE (n:{labels} {{{primary['key']}: $value}}) SET n += $props"
                await session.run(cypher, value=primary["value"], props=properties)
            else:
                cypher = f"CREATE (n:{labels}) SET n += $props"
                await session.run(cypher, props=properties)
        for rel in payload.get("relationships", []):
            start = rel.get("start")
            end = rel.get("end")
            if not start or not end:
                continue
            cypher = (
                f"MATCH (a:{start['label']} {{{start['key']}: $start_value}}) "
                f"MATCH (b:{end['label']} {{{end['key']}: $end_value}}) "
                f"MERGE (a)-[r:{rel['type']}]->(b) SET r += $props"
            )
            await session.run(
                cypher,
                start_value=start["value"],
                end_value=end["value"],
                props=rel.get("properties", {}),
            )
    await driver.close()


def restore_lancedb(source: Path) -> None:
    archive = source / "lancedb.zip"
    if not archive.exists():
        return
    target = Path(settings.lancedb_uri)
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
    shutil.unpack_archive(archive, target)


def restore_minio(source: Path) -> None:
    artifact_dir = source / "minio"
    if not artifact_dir.exists():
        return
    client = Minio(
        endpoint=settings.minio_endpoint.replace("http://", "").replace("https://", ""),
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )
    bucket = settings.minio_bucket
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)
    else:
        for obj in client.list_objects(bucket, recursive=True):
            client.remove_object(bucket, obj.object_name)
    for file_path in artifact_dir.rglob("*"):
        if file_path.is_file():
            object_name = str(file_path.relative_to(artifact_dir))
            client.fput_object(bucket, object_name, str(file_path))


async def restore_valkey(source: Path) -> None:
    snapshot_path = source / "valkey.json"
    if not snapshot_path.exists():
        return
    snapshot = json.loads(snapshot_path.read_text())
    client = Redis(host=settings.valkey_host, port=settings.valkey_port, decode_responses=True)
    await client.flushdb()
    for key, value in snapshot.items():
        if isinstance(value, str):
            await client.set(key, value)
        elif isinstance(value, list):
            await client.rpush(key, *value)
        elif isinstance(value, dict):
            await client.hset(key, mapping=value)
    await client.close()


async def main(backup_name: str | None = None) -> None:
    if backup_name:
        source = BACKUP_ROOT / backup_name
    else:
        backups = sorted([p for p in BACKUP_ROOT.iterdir() if p.is_dir()])
        if not backups:
            raise SystemExit("No backups found")
        source = backups[-1]
    await restore_neo4j(source)
    restore_lancedb(source)
    restore_minio(source)
    await restore_valkey(source)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Restore Personal Knowledge Brain data")
    parser.add_argument("backup", nargs="?", help="Backup directory name")
    args = parser.parse_args()
    asyncio.run(main(args.backup))
