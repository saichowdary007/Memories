from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Dict

from connectors.base import BaseConnector, SyncResult
from connectors.state_store import load_state, save_state
from core.config import settings


class ObsidianConnector(BaseConnector):
    name = "obsidian"

    def __init__(self) -> None:
        self._vault_path = Path(settings.obsidian_vault_path).expanduser()
        if not self._vault_path.exists():
            raise RuntimeError(f"Obsidian vault path not found: {self._vault_path}")

    async def sync(self) -> AsyncIterator[SyncResult]:  # type: ignore[override]
        state = await load_state(self.name)
        known = state.get("files", {})
        new_state: Dict[str, Any] = {"files": {}}
        for file_path in self._vault_path.rglob("*.md"):
            mtime = file_path.stat().st_mtime
            str_path = str(file_path)
            new_state["files"][str_path] = mtime
            if known.get(str_path) and known[str_path] >= mtime:
                continue
            content = await asyncio.to_thread(file_path.read_text, encoding="utf-8")
            doc_id = f"obsidian:{hashlib.sha256(str_path.encode()).hexdigest()}"
            created = datetime.fromtimestamp(file_path.stat().st_ctime, tz=timezone.utc)
            modified = datetime.fromtimestamp(mtime, tz=timezone.utc)
            document = {
                "doc_id": doc_id,
                "version": str(mtime),
                "title": file_path.stem,
                "source": "obsidian",
                "created_at": created.isoformat(),
                "valid_from": modified.isoformat(),
                "valid_to": None,
                "system_from": datetime.now(timezone.utc).isoformat(),
                "system_to": None,
            }
            block = {
                "block_id": doc_id,
                "block_type": "markdown",
                "bounding_box": None,
                "text_content": content,
                "text_vector": None,
            }
            files = [
                {
                    "uri": str_path,
                    "mime_type": "text/markdown",
                    "size_bytes": file_path.stat().st_size,
                    "created_at": created.isoformat(),
                }
            ]
            yield SyncResult({"document": document, "block": block, "files": files})
        await save_state(self.name, new_state)

    async def checkpoint(self, state: Dict[str, Any]) -> None:
        await save_state(self.name, state)
