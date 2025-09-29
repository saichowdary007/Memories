from __future__ import annotations

import asyncio
import json

import httpx
from neo4j import AsyncGraphDatabase
from redis.asyncio import Redis

from core.config import settings


async def check_api() -> dict[str, str]:
    url = "http://localhost:8000/health"
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.json()


async def check_neo4j() -> bool:
    driver = AsyncGraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password))
    async with driver.session() as session:
        result = await session.run("RETURN 1")
        record = await result.single()
    await driver.close()
    return bool(record and record[0] == 1)


async def check_valkey() -> bool:
    client = Redis(host=settings.valkey_host, port=settings.valkey_port)
    pong = await client.ping()
    await client.close()
    return bool(pong)


async def main() -> None:
    api_task = asyncio.create_task(check_api())
    neo4j_task = asyncio.create_task(check_neo4j())
    valkey_task = asyncio.create_task(check_valkey())

    api_status = await api_task
    neo4j_status = await neo4j_task
    valkey_status = await valkey_task

    result = {
        "api": api_status,
        "neo4j": neo4j_status,
        "valkey": valkey_status,
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
