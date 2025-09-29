from __future__ import annotations

import asyncio
import datetime as dt
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx
from googleapiclient.discovery import build

from connectors.base import BaseConnector, SyncResult
from connectors.google_auth import ensure_credentials
from connectors.state_store import load_state, save_state

CACHE_DIR = Path.home() / ".cache" / "pkb" / "photos"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


class GooglePhotosConnector(BaseConnector):
    name = "google_photos"

    async def _service(self):
        creds = await ensure_credentials("photos")

        def _build():
            return build("photoslibrary", "v1", credentials=creds, static_discovery=False)

        return await asyncio.to_thread(_build)

    async def sync(self) -> AsyncIterator[SyncResult]:  # type: ignore[override]
        service = await self._service()
        state = await load_state(self.name)
        latest_iso = state.get("latest_creation_time")
        latest_dt = dt.datetime.fromisoformat(latest_iso) if latest_iso else None
        page_token: Optional[str] = None
        new_latest = latest_dt

        async with httpx.AsyncClient(timeout=30.0) as client:
            while True:
                request = service.mediaItems().list(pageSize=100, pageToken=page_token)
                response = await asyncio.to_thread(request.execute)
                for item in response.get("mediaItems", []):
                    metadata = item.get("mediaMetadata", {})
                    creation = metadata.get("creationTime")
                    if creation:
                        creation_dt = dt.datetime.fromisoformat(creation.replace("Z", "+00:00"))
                        if latest_dt and creation_dt <= latest_dt:
                            continue
                        if not new_latest or creation_dt > new_latest:
                            new_latest = creation_dt
                    else:
                        creation_dt = dt.datetime.now(dt.timezone.utc)
                    mime_type = item.get("mimeType", "image/jpeg")
                    local_path = await self._download_media(client, item["baseUrl"], item["filename"], mime_type)
                    gps = metadata.get("location") or {}
                    geo_coords = None
                    if gps:
                        geo_coords = {
                            "latitude": gps.get("latitude"),
                            "longitude": gps.get("longitude"),
                        }
                    document = {
                        "doc_id": f"photos:{item['id']}",
                        "version": item.get("mediaMetadata", {}).get("creationTime"),
                        "title": item.get("filename"),
                        "source": "google_photos",
                        "created_at": creation_dt.isoformat(),
                        "valid_from": creation_dt.isoformat(),
                        "valid_to": None,
                        "system_from": dt.datetime.now(dt.timezone.utc).isoformat(),
                        "system_to": None,
                    }
                    image_node = {
                        "image_id": item["id"],
                        "capture_time_utc": creation_dt.isoformat(),
                        "capture_time_local": creation_dt.astimezone().isoformat(),
                        "gps_coords": geo_coords,
                        "image_type": mime_type,
                        "image_vector": None,
                    }
                    files = [
                        {
                            "uri": local_path,
                            "mime_type": mime_type,
                            "size_bytes": Path(local_path).stat().st_size,
                            "created_at": creation_dt.isoformat(),
                        }
                    ]
                    yield SyncResult({"document": document, "image": image_node, "files": files})
                page_token = response.get("nextPageToken")
                if not page_token:
                    break
        if new_latest:
            await save_state(self.name, {"latest_creation_time": new_latest.isoformat()})

    async def checkpoint(self, state: Dict[str, Any]) -> None:
        await save_state(self.name, state)

    async def _download_media(self, client: httpx.AsyncClient, base_url: str, filename: str, mime_type: str) -> str:
        url = f"{base_url}=d"
        response = await client.get(url)
        response.raise_for_status()
        extension = mime_type.split("/")[-1]
        safe_name = filename if filename else f"photo.{extension}"
        file_path = CACHE_DIR / f"{safe_name}-{hash(base_url) & 0xfffffff}.{extension}"
        file_path.write_bytes(response.content)
        return str(file_path)
