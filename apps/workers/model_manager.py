from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any, Awaitable, Callable, Dict

from core.system.memory import memory_guard

logger = logging.getLogger(__name__)


class ModelManager:
    def __init__(self) -> None:
        self._locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._models: Dict[str, Any] = {}

    async def get_or_load(self, name: str, loader: Callable[[], Awaitable[Any]]) -> Any:
        lock = self._locks[name]
        async with lock:
            if name in self._models:
                return self._models[name]
            await memory_guard.wait_for_recovery()
            model = await loader()
            self._models[name] = model
            logger.info("Model loaded", extra={"model": name})
            return model

    async def unload(self, name: str) -> None:
        if name in self._models:
            del self._models[name]
            logger.info("Model unloaded", extra={"model": name})


model_manager = ModelManager()
