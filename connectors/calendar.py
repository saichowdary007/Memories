from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator, Dict, List, Optional

from googleapiclient.discovery import build

from connectors.base import BaseConnector, SyncResult
from connectors.google_auth import ensure_credentials
from connectors.state_store import load_state, save_state


class GoogleCalendarConnector(BaseConnector):
    name = "google_calendar"

    async def _service(self):
        creds = await ensure_credentials("calendar")

        def _build():
            return build("calendar", "v3", credentials=creds, cache_discovery=False)

        return await asyncio.to_thread(_build)

    async def sync(self) -> AsyncIterator[SyncResult]:  # type: ignore[override]
        service = await self._service()
        state = await load_state(self.name)
        sync_token = state.get("sync_token")
        time_min = datetime.now(timezone.utc) - timedelta(days=180)

        request_kwargs: Dict[str, Any] = {
            "calendarId": "primary",
            "maxResults": 2500,
            "singleEvents": True,
            "orderBy": "startTime",
        }
        if sync_token:
            request_kwargs["syncToken"] = sync_token
        else:
            request_kwargs["timeMin"] = time_min.isoformat()

        while True:
            request = service.events().list(**request_kwargs)
            response = await asyncio.to_thread(request.execute)
            events = response.get("items", [])
            for event in events:
                if event.get("status") == "cancelled":
                    continue
                doc_id = f"calendar:{event['id']}"
                start = event.get("start", {}).get("dateTime") or event.get("start", {}).get("date")
                end = event.get("end", {}).get("dateTime") or event.get("end", {}).get("date")
                start_iso = self._normalize_time(start)
                end_iso = self._normalize_time(end)
                document = {
                    "doc_id": doc_id,
                    "version": event.get("etag"),
                    "title": event.get("summary", "(no title)"),
                    "source": "google_calendar",
                    "created_at": event.get("created", datetime.now(timezone.utc).isoformat()),
                    "valid_from": start_iso,
                    "valid_to": end_iso,
                    "system_from": datetime.now(timezone.utc).isoformat(),
                    "system_to": None,
                }
                attendees = [attendee.get("email") for attendee in event.get("attendees", []) if attendee.get("email")]
                event_node = {
                    "event_id": doc_id,
                    "title": event.get("summary", ""),
                    "start_time": start_iso,
                    "end_time": end_iso,
                    "location": event.get("location"),
                }
                yield SyncResult({"document": document, "event": event_node, "entities": {"people": attendees}})
            page_token = response.get("nextPageToken")
            if not page_token:
                new_token = response.get("nextSyncToken")
                if new_token:
                    await save_state(self.name, {"sync_token": new_token})
                break
            request_kwargs["pageToken"] = page_token

    async def checkpoint(self, state: Dict[str, Any]) -> None:
        await save_state(self.name, state)

    def _normalize_time(self, value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        if len(value) == 10:
            dt_obj = datetime.fromisoformat(value)
            return dt_obj.replace(tzinfo=timezone.utc).isoformat()
        if value.endswith("Z"):
            return value.replace("Z", "+00:00")
        return value
