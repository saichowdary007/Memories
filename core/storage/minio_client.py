from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import BinaryIO, Optional

from minio import Minio
from minio.commonconfig import Tags

from core.config import settings
from core.logging import log_event

logger = logging.getLogger(__name__)


class MinioStorage:
    def __init__(self) -> None:
        endpoint = settings.minio_endpoint.replace("http://", "").replace("https://", "")
        self._client = Minio(
            endpoint=endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        self._bucket = settings.minio_bucket

    async def ensure_bucket(self) -> None:
        exists = await asyncio.to_thread(self._client.bucket_exists, self._bucket)
        if not exists:
            await asyncio.to_thread(self._client.make_bucket, self._bucket)

    async def ping(self) -> bool:
        await self.ensure_bucket()
        return True

    async def upload_file(self, object_name: str, file_path: Path, content_type: str, tags: Optional[dict[str, str]] = None) -> str:
        await self.ensure_bucket()
        await asyncio.to_thread(
            self._client.fput_object,
            self._bucket,
            object_name,
            str(file_path),
            content_type=content_type,
            tags=Tags(tags or {}),
        )
        log_event(logger, "storage.upload", object=object_name)
        return f"{settings.minio_endpoint}/{self._bucket}/{object_name}"

    async def upload_stream(self, object_name: str, stream: BinaryIO, length: int, content_type: str) -> str:
        await self.ensure_bucket()
        await asyncio.to_thread(
            self._client.put_object,
            self._bucket,
            object_name,
            stream,
            length,
            content_type=content_type,
        )
        log_event(logger, "storage.upload_stream", object=object_name)
        return f"{settings.minio_endpoint}/{self._bucket}/{object_name}"

    async def download_to_path(self, object_name: str, destination: Path) -> Path:
        await self.ensure_bucket()
        await asyncio.to_thread(self._client.fget_object, self._bucket, object_name, str(destination))
        return destination


minio_storage = MinioStorage()
