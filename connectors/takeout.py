from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Dict

from connectors.base import BaseConnector, SyncResult
from connectors.state_store import load_state, save_state
from core.config import settings


class GoogleTakeoutConnector(BaseConnector):
    name = "google_takeout"

    def __init__(self) -> None:
        self._base_path = Path(settings.google_takeout_path).expanduser()
        if not self._base_path.exists():
            raise RuntimeError(f"Google Takeout path not found: {self._base_path}")

    async def sync(self) -> AsyncIterator[SyncResult]:  # type: ignore[override]
        state = await load_state(self.name)
        known_hashes = state.get("hashes", {})
        new_hashes: Dict[str, str] = {}
        for file_path in self._base_path.rglob("*.json"):
            raw = await asyncio.to_thread(file_path.read_text, encoding="utf-8")
            sha = hashlib.sha256(raw.encode("utf-8")).hexdigest()
            new_hashes[str(file_path)] = sha
            if known_hashes.get(str(file_path)) == sha:
                continue
            data = json.loads(raw)
            doc_id = f"takeout:{sha[:12]}"
            document = {
                "doc_id": doc_id,
                "version": sha,
                "title": file_path.stem,
                "source": "google_takeout",
                "created_at": datetime.fromtimestamp(file_path.stat().st_ctime, tz=timezone.utc).isoformat(),
                "valid_from": datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc).isoformat(),
                "valid_to": None,
                "system_from": datetime.now(timezone.utc).isoformat(),
                "system_to": None,
            }
            block_content = json.dumps(data, indent=2)[:5000]
            block = {
                "block_id": doc_id,
                "block_type": "json",
                "bounding_box": None,
                "text_content": block_content,
                "text_vector": None,
            }
            files = [
                {
                    "uri": str(file_path),
                    "mime_type": "application/json",
                    "size_bytes": file_path.stat().st_size,
                    "created_at": document["created_at"],
                }
            ]
            yield SyncResult({"document": document, "block": block, "files": files})
        await save_state(self.name, {"hashes": new_hashes})

    async def checkpoint(self, state: Dict[str, Any]) -> None:
        await save_state(self.name, state)
