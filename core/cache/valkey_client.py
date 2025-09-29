from __future__ import annotations

import json
import logging
from typing import Any, Callable, Coroutine, Optional

from redis.asyncio import Redis

from core.config import settings
from core.logging import log_event

logger = logging.getLogger(__name__)


class ValkeyClient:
    def __init__(self) -> None:
        self._client = Redis(host=settings.valkey_host, port=settings.valkey_port, decode_responses=True)

    async def close(self) -> None:
        await self._client.close()

    async def ping(self) -> bool:
        response = await self._client.ping()
        return bool(response)

    async def get(self, key: str) -> Optional[Any]:
        value = await self._client.get(key)
        if value:
            log_event(logger, "cache.hit", key=key)
            return json.loads(value)
        log_event(logger, "cache.miss", key=key)
        return None

    async def set(self, key: str, value: Any, ttl_seconds: int = 86400) -> None:
        await self._client.set(key, json.dumps(value), ex=ttl_seconds)
        log_event(logger, "cache.store", key=key)

    async def cached(self, key: str, ttl_seconds: int, loader: Callable[[], Coroutine[Any, Any, Any]]) -> Any:
        data = await self.get(key)
        if data is not None:
            return data
        data = await loader()
        await self.set(key, data, ttl_seconds)
        return data

    async def enqueue(self, queue: str, payload: Any) -> None:
        await self._client.lpush(queue, json.dumps(payload))
        log_event(logger, "queue.enqueue", queue=queue)

    async def dequeue(self, queue: str, timeout: int = 5) -> Optional[Any]:
        result = await self._client.brpop(queue, timeout=timeout)
        if result:
            _, data = result
            return json.loads(data)
        return None

    @property
    def raw(self) -> Redis:
        return self._client


valkey_client = ValkeyClient()
