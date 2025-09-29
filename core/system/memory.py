from __future__ import annotations

import asyncio
import logging
import subprocess
from dataclasses import dataclass
from typing import Optional

import psutil

from core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class MemorySnapshot:
    total: int
    available: int
    free: int
    used: int
    percent: float
    mps_free: Optional[int] = None


class MemoryGuard:
    def __init__(self, min_free_bytes: int = settings.backpressure_free_mem_bytes) -> None:
        self._min_free_bytes = min_free_bytes

    @property
    def min_free_bytes(self) -> int:
        return self._min_free_bytes

    def snapshot(self) -> MemorySnapshot:
        vm = psutil.virtual_memory()
        mps_free = self._query_mps_free_memory()
        return MemorySnapshot(
            total=vm.total,
            available=vm.available,
            free=vm.free,
            used=vm.used,
            percent=vm.percent,
            mps_free=mps_free,
        )

    def is_under_pressure(self) -> bool:
        snap = self.snapshot()
        logger.debug("Memory snapshot", extra={"free": snap.free, "available": snap.available, "mps_free": snap.mps_free})
        pressure = snap.free < self._min_free_bytes or (snap.mps_free is not None and snap.mps_free < self._min_free_bytes)
        return pressure

    async def wait_for_recovery(self) -> None:
        while self.is_under_pressure():
            logger.warning("Memory pressure detected; backing off", extra={"min_free": self._min_free_bytes})
            await asyncio.sleep(2)

    def _query_mps_free_memory(self) -> Optional[int]:
        try:
            result = subprocess.run(
                ["/usr/bin/python3", "-c", "import torch; print(torch.mps.driver_allocated_memory())"],
                capture_output=True,
                text=True,
                check=True,
            )
            value = int(result.stdout.strip())
            return value
        except Exception:
            return None


memory_guard = MemoryGuard()
