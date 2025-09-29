from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List, Optional

from notion_client import AsyncClient

from connectors.base import BaseConnector, SyncResult
from connectors.state_store import load_state, save_state
from core.config import settings


class NotionConnector(BaseConnector):
    name = "notion"

    def __init__(self) -> None:
        if not settings.notion_internal_integration_token:
            raise RuntimeError("NOTION_INTERNAL_INTEGRATION_TOKEN not configured")
        self._client = AsyncClient(auth=settings.notion_internal_integration_token)

    async def sync(self) -> AsyncIterator[SyncResult]:  # type: ignore[override]
        state = await load_state(self.name)
        last_edited = state.get("last_edited")
        cursor: Optional[str] = None
        new_last: Optional[str] = last_edited

        while True:
            response = await self._client.search(
                **{
                    "start_cursor": cursor,
                    "sort": {"direction": "ascending", "timestamp": "last_edited_time"},
                    "filter": {"value": "page", "property": "object"},
                    "page_size": 100,
                }
            )
            for result in response.get("results", []):
                page_id = result["id"]
                last_time = result.get("last_edited_time")
                if last_edited and last_time <= last_edited:
                    continue
                properties = await self._client.pages.retrieve(page_id=page_id)
                content = await self._client.blocks.children.list(block_id=page_id, page_size=100)
                text_fragments: List[str] = []
                for block in content.get("results", []):
                    rich_text = block.get("paragraph", {}).get("rich_text") or block.get("heading_1", {}).get("rich_text")
                    if not rich_text:
                        continue
                    for fragment in rich_text:
                        text_fragments.append(fragment.get("plain_text", ""))
                doc_title = self._extract_title(properties)
                last_edit_dt = datetime.fromisoformat(last_time.replace("Z", "+00:00")) if last_time else datetime.now(timezone.utc)
                doc_id = f"notion:{page_id}"
                document = {
                    "doc_id": doc_id,
                    "version": properties.get("last_edited_time"),
                    "title": doc_title,
                    "source": "notion",
                    "created_at": properties.get("created_time"),
                    "valid_from": properties.get("created_time"),
                    "valid_to": None,
                    "system_from": datetime.now(timezone.utc).isoformat(),
                    "system_to": None,
                }
                block = {
                    "block_id": doc_id,
                    "block_type": "notion_page",
                    "bounding_box": None,
                    "text_content": "\n".join(text_fragments),
                    "text_vector": None,
                }
                yield SyncResult({"document": document, "block": block})
                if not new_last or last_time > new_last:
                    new_last = last_time
            cursor = response.get("next_cursor")
            if not response.get("has_more"):
                break
        if new_last:
            await save_state(self.name, {"last_edited": new_last})

    async def checkpoint(self, state: Dict[str, Any]) -> None:
        await save_state(self.name, state)

    def _extract_title(self, properties: Dict[str, Any]) -> str:
        title_prop = properties.get("properties", {}).get("title")
        if not title_prop:
            return "Untitled"
        rich_text = title_prop.get("title", [])
        if not rich_text:
            return "Untitled"
        return "".join(fragment.get("plain_text", "") for fragment in rich_text)
