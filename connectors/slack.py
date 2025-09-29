from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List

from slack_sdk.web.async_client import AsyncWebClient

from connectors.base import BaseConnector, SyncResult
from connectors.state_store import load_state, save_state
from core.config import settings


class SlackConnector(BaseConnector):
    name = "slack"

    def __init__(self) -> None:
        if not settings.slack_bot_token:
            raise RuntimeError("SLACK_BOT_TOKEN environment variable not set")
        self._client = AsyncWebClient(token=settings.slack_bot_token)

    async def sync(self) -> AsyncIterator[SyncResult]:  # type: ignore[override]
        state = await load_state(self.name)
        channels = await self._client.conversations_list(limit=200)
        new_state: Dict[str, Any] = {}
        for channel in channels.get("channels", []):
            channel_id = channel["id"]
            last_ts = state.get(channel_id, {}).get("last_ts")
            history = await self._fetch_history(channel_id, last_ts)
            latest_ts = last_ts
            for message in history:
                ts = float(message["ts"])
                if not latest_ts or ts > float(latest_ts):
                    latest_ts = message["ts"]
                doc_id = f"slack:{channel_id}:{message['ts']}"
                created = datetime.fromtimestamp(ts, tz=timezone.utc)
                text = message.get("text", "")
                files = []
                for file_obj in message.get("files", []) or []:
                    files.append(
                        {
                            "uri": file_obj.get("url_private"),
                            "mime_type": file_obj.get("mimetype", "application/octet-stream"),
                            "size_bytes": file_obj.get("size", 0),
                            "created_at": created.isoformat(),
                        }
                    )
                document = {
                    "doc_id": doc_id,
                    "version": message.get("client_msg_id") or message.get("ts"),
                    "title": text[:80] or "Slack message",
                    "source": "slack",
                    "created_at": created.isoformat(),
                    "valid_from": created.isoformat(),
                    "valid_to": None,
                    "system_from": datetime.now(timezone.utc).isoformat(),
                    "system_to": None,
                }
                block = {
                    "block_id": doc_id,
                    "block_type": "message",
                    "bounding_box": None,
                    "text_content": text,
                    "text_vector": None,
                }
                yield SyncResult({"document": document, "block": block, "files": files})
            if latest_ts:
                new_state[channel_id] = {"last_ts": latest_ts}
        await save_state(self.name, new_state)

    async def checkpoint(self, state: Dict[str, Any]) -> None:
        await save_state(self.name, state)

    async def _fetch_history(self, channel_id: str, last_ts: Any) -> List[Dict[str, Any]]:
        messages: List[Dict[str, Any]] = []
        cursor = None
        while True:
            response = await self._client.conversations_history(channel=channel_id, cursor=cursor, limit=200, inclusive=True)
            for message in response.get("messages", []):
                if last_ts and float(message["ts"]) <= float(last_ts):
                    continue
                messages.append(message)
            cursor = response.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break
        messages.sort(key=lambda item: float(item["ts"]))
        return messages
