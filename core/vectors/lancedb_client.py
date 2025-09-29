from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List

import lancedb

from core.config import settings
from core.logging import log_event

logger = logging.getLogger(__name__)


class LanceDBClient:
    def __init__(self, uri: str | None = None) -> None:
        self._uri = uri or settings.lancedb_uri
        Path(self._uri).mkdir(parents=True, exist_ok=True)
        self._db = lancedb.connect(self._uri)

    async def _run(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        return await asyncio.to_thread(func, *args, **kwargs)

    async def health_check(self) -> bool:
        await self._run(self._db.table_names)
        return True

    async def upsert_vectors(
        self,
        table_name: str,
        records: Iterable[Dict[str, Any]],
        primary_key: str = "id",
    ) -> None:
        payload = list(records)
        if not payload:
            return
        if table_name not in self._db.table_names():
            self._db.create_table(table_name, data=payload)
            log_event(logger, "vectors.create_table", table=table_name, count=len(payload))
            return
        table = self._db.open_table(table_name)
        await self._run(table.merge_insert, payload, on=primary_key)
        log_event(logger, "vectors.upsert", table=table_name, count=len(payload))

    async def search(
        self,
        table_name: str,
        vector: List[float],
        limit: int = 20,
        filters: Dict[str, Any] | None = None,
    ) -> List[Dict[str, Any]]:
        if table_name not in self._db.table_names():
            return []
        table = self._db.open_table(table_name)
        query = table.search(vector)
        if filters:
            for key, value in filters.items():
                query = query.where(f"{key} = '{value}'")
        result = await self._run(query.limit, limit)
        return [row.as_dict() for row in result]

    async def hybrid_search(
        self,
        table_name: str,
        dense_vector: List[float],
        sparse_vector: Dict[str, float],
        alpha: float = 0.5,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        if table_name not in self._db.table_names():
            return []
        table = self._db.open_table(table_name)
        query = table.search(dense_vector).with_hybrid(dense=dense_vector, sparse=sparse_vector, alpha=alpha)
        result = await self._run(query.limit, limit)
        return [row.as_dict() for row in result]


lancedb_client = LanceDBClient()
