from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import APIRouter

from apps.api.metrics import HEALTH_STATUS
from apps.api.models import HealthDependency, HealthStatus
from core.cache import valkey_client
from core.graph import graph_service
from core.storage import minio_storage
from core.system.memory import memory_guard
from core.vectors import lancedb_client

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=HealthStatus)
async def health() -> HealthStatus:
    dependencies: list[HealthDependency] = []

    start = time.perf_counter()
    neo_status = "pass"
    neo_details = None
    try:
        alive = await graph_service.ping()
        neo_status = "pass" if alive else "fail"
    except Exception as exc:
        neo_status = "fail"
        neo_details = str(exc)
    dependencies.append(
        HealthDependency(
            name="neo4j",
            status=neo_status,
            latency_ms=int((time.perf_counter() - start) * 1000),
            details=neo_details,
        )
    )

    start = time.perf_counter()
    valkey_status = "pass"
    valkey_details = None
    try:
        pong = await valkey_client.ping()
        valkey_status = "pass" if pong else "fail"
    except Exception as exc:
        valkey_status = "fail"
        valkey_details = str(exc)
    dependencies.append(
        HealthDependency(
            name="valkey",
            status=valkey_status,
            latency_ms=int((time.perf_counter() - start) * 1000),
            details=valkey_details,
        )
    )

    start = time.perf_counter()
    minio_status = "pass"
    minio_details = None
    try:
        await minio_storage.ping()
    except Exception as exc:
        minio_status = "fail"
        minio_details = str(exc)
    dependencies.append(
        HealthDependency(
            name="minio",
            status=minio_status,
            latency_ms=int((time.perf_counter() - start) * 1000),
            details=minio_details,
        )
    )

    start = time.perf_counter()
    vector_status = "pass"
    vector_details = None
    try:
        await lancedb_client.health_check()
    except Exception as exc:
        vector_status = "fail"
        vector_details = str(exc)
    dependencies.append(
        HealthDependency(
            name="lancedb",
            status=vector_status,
            latency_ms=int((time.perf_counter() - start) * 1000),
            details=vector_details,
        )
    )

    snapshot = memory_guard.snapshot()
    memory_status = "pass" if snapshot.free >= memory_guard.min_free_bytes else "warn"
    dependencies.append(
        HealthDependency(
            name="memory",
            status=memory_status,
            latency_ms=0,
            details=f"free={snapshot.free} available={snapshot.available} mps_free={snapshot.mps_free}",
        )
    )

    overall = "pass" if all(dep.status == "pass" for dep in dependencies) else "fail"
    HEALTH_STATUS.set(1 if overall == "pass" else 0)
    return HealthStatus(status=overall, timestamp=datetime.now(tz=timezone.utc), dependencies=dependencies)
