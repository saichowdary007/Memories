from __future__ import annotations

import asyncio
import io
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

from connectors.base import BaseConnector, SyncResult
from connectors.google_auth import ensure_credentials
from connectors.state_store import load_state, save_state

CACHE_DIR = Path.home() / ".cache" / "pkb" / "drive"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


class DriveConnector(BaseConnector):
    name = "google_drive"

    def __init__(self) -> None:
        self._fields = "id,name,mimeType,modifiedTime,createdTime,version,ownedByMe,owners(displayName,emailAddress),size,webViewLink"

    async def _service(self):
        creds = await ensure_credentials("drive")

        def _build():
            return build("drive", "v3", credentials=creds, cache_discovery=False)

        return await asyncio.to_thread(_build)

    async def sync(self) -> AsyncIterator[SyncResult]:  # type: ignore[override]
        service = await self._service()
        state = await load_state(self.name)
        page_token = state.get("start_page_token")
        if not page_token:
            about = await asyncio.to_thread(service.changes().getStartPageToken().execute)
            page_token = about.get("startPageToken")
            await save_state(self.name, {"start_page_token": page_token})

        current_token = page_token
        while True:
            request = service.changes().list(pageToken=current_token, pageSize=100, spaces="drive", fields="nextPageToken,newStartPageToken,changes(fileId,file({fields}))".format(fields=self._fields))
            response = await asyncio.to_thread(request.execute)
            for change in response.get("changes", []):
                file_obj = change.get("file")
                if not file_obj or file_obj.get("trashed"):
                    continue
                file_id = file_obj["id"]
                metadata = await self._fetch_metadata(service, file_id)
                if metadata is None:
                    continue
                local_files = await self._download_file(service, metadata)
                doc_id = f"drive:{file_id}:{metadata.get('version')}"
                document = {
                    "doc_id": doc_id,
                    "version": metadata.get("version"),
                    "title": metadata.get("name"),
                    "source": "google_drive",
                    "created_at": metadata.get("createdTime"),
                    "valid_from": metadata.get("modifiedTime"),
                    "valid_to": None,
                    "system_from": datetime.now(timezone.utc).isoformat(),
                    "system_to": None,
                }
                yield SyncResult(
                    {
                        "document": document,
                        "files": local_files,
                        "entities": {
                            "people": [owner.get("emailAddress") for owner in metadata.get("owners", []) if owner.get("emailAddress")],
                        },
                    }
                )
            current_token = response.get("nextPageToken")
            if not current_token:
                new_token = response.get("newStartPageToken")
                if new_token:
                    await save_state(self.name, {"start_page_token": new_token})
                break

    async def checkpoint(self, state: Dict[str, Any]) -> None:
        await save_state(self.name, state)

    async def _fetch_metadata(self, service, file_id: str) -> Optional[Dict[str, Any]]:
        request = service.files().get(fileId=file_id, fields=self._fields, supportsAllDrives=True)
        try:
            return await asyncio.to_thread(request.execute)
        except HttpError as exc:
            if exc.resp.status in {404, 410}:
                return None
            raise

    async def _download_file(self, service, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        mime_type = metadata.get("mimeType", "application/octet-stream")
        export_map = {
            "application/vnd.google-apps.document": "application/pdf",
            "application/vnd.google-apps.spreadsheet": "text/csv",
            "application/vnd.google-apps.presentation": "application/pdf",
        }
        target_mime = export_map.get(mime_type, mime_type)
        file_id = metadata["id"]
        file_name = metadata.get("name", file_id)
        file_path = CACHE_DIR / f"{file_id}-{metadata.get('version')}.{self._extension_for_mime(target_mime)}"

        if mime_type.startswith("application/vnd.google-apps"):
            request = service.files().export_media(fileId=file_id, mimeType=target_mime)
        else:
            request = service.files().get_media(fileId=file_id, supportsAllDrives=True)
        fh = io.FileIO(file_path, mode="wb")
        try:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = await asyncio.to_thread(downloader.next_chunk)
        finally:
            fh.close()
        size_bytes = file_path.stat().st_size if file_path.exists() else 0
        return [
            {
                "uri": str(file_path),
                "mime_type": target_mime,
                "size_bytes": size_bytes,
                "created_at": metadata.get("createdTime"),
            }
        ]

    def _extension_for_mime(self, mime: str) -> str:
        if mime == "application/pdf":
            return "pdf"
        if mime == "text/csv":
            return "csv"
        if mime == "application/vnd.openxmlformats-officedocument.presentationml.presentation":
            return "pptx"
        if mime.startswith("image/"):
            return mime.split("/")[-1]
        if mime.startswith("text/"):
            return "txt"
        return "bin"
