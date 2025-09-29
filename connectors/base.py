from __future__ import annotations

import abc
from typing import Any, AsyncIterator, Dict


class SyncResult(Dict[str, Any]):
    """Wrapper for ingestion payload."""


class BaseConnector(abc.ABC):
    name: str

    @abc.abstractmethod
    async def sync(self) -> AsyncIterator[SyncResult]:
        """Yield SyncResult objects ready for ingestion."""

    @abc.abstractmethod
    async def checkpoint(self, state: Dict[str, Any]) -> None:
        """Persist connector state for incremental updates."""
