from __future__ import annotations

import asyncio
import hashlib
import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Dict

from connectors.base import BaseConnector, SyncResult
from connectors.state_store import load_state, save_state
from core.config import settings


class LocalFilesystemConnector(BaseConnector):
    name = "local_fs"

    async def sync(self) -> AsyncIterator[SyncResult]:  # type: ignore[override]
        state = await load_state(self.name)
        known = state.get("files", {})
        new_state: Dict[str, Any] = {"files": {}}
        for root in settings.local_watch_paths:
            base_path = Path(root)
            if not base_path.exists():
                continue
            for file_path in base_path.rglob("*"):
                if not file_path.is_file():
                    continue
                mtime = file_path.stat().st_mtime
                str_path = str(file_path)
                new_state["files"][str_path] = mtime
                if known.get(str_path) and known[str_path] >= mtime:
                    continue
                sha256 = await asyncio.to_thread(self._hash_file, file_path)
                mime_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
                created = datetime.fromtimestamp(file_path.stat().st_ctime, tz=timezone.utc)
                modified = datetime.fromtimestamp(mtime, tz=timezone.utc)
                doc_id = f"local:{sha256[:16]}"
                document = {
                    "doc_id": doc_id,
                    "version": sha256,
                    "title": file_path.name,
                    "source": "local_filesystem",
                    "created_at": created.isoformat(),
                    "valid_from": modified.isoformat(),
                    "valid_to": None,
                    "system_from": datetime.now(timezone.utc).isoformat(),
                    "system_to": None,
                }
                files = [
                    {
                        "uri": str_path,
                        "mime_type": mime_type,
                        "size_bytes": file_path.stat().st_size,
                        "created_at": created.isoformat(),
                    }
                ]
                if mime_type.startswith("text"):
                    content = await asyncio.to_thread(file_path.read_text, encoding="utf-8", errors="ignore")
                    block = {
                        "block_id": doc_id,
                        "block_type": "file_text",
                        "bounding_box": None,
                        "text_content": content,
                        "text_vector": None,
                    }
                    yield SyncResult({"document": document, "block": block, "files": files})
                else:
                    yield SyncResult({"document": document, "files": files})
        await save_state(self.name, new_state)

    async def checkpoint(self, state: Dict[str, Any]) -> None:
        await save_state(self.name, state)

    def _hash_file(self, path: Path) -> str:
        hasher = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
