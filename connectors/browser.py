from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Tuple

from connectors.base import BaseConnector, SyncResult
from connectors.state_store import load_state, save_state
from core.config import settings

CHROME_EPOCH = datetime(1601, 1, 1, tzinfo=timezone.utc)


class BrowserHistoryConnector(BaseConnector):
    name = "browser_history"

    def __init__(self) -> None:
        self._chrome_path = Path(settings.chrome_history_path).expanduser()
        self._firefox_profile_dir = Path(settings.firefox_profile_path).expanduser()

    async def sync(self) -> AsyncIterator[SyncResult]:  # type: ignore[override]
        state = await load_state(self.name)
        new_state: Dict[str, Any] = {}

        if self._chrome_path.exists():
            last_ts = state.get("chrome_last_visit")
            chrome_entries, latest = self._read_chrome_history(last_ts)
            for entry in chrome_entries:
                yield self._build_sync_result("chrome", entry)
            if latest:
                new_state["chrome_last_visit"] = latest

        if self._firefox_profile_dir.exists():
            last_ts = state.get("firefox_last_visit")
            firefox_entries, latest = self._read_firefox_history(last_ts)
            for entry in firefox_entries:
                yield self._build_sync_result("firefox", entry)
            if latest:
                new_state["firefox_last_visit"] = latest

        if new_state:
            await save_state(self.name, {**state, **new_state})

    async def checkpoint(self, state: Dict[str, Any]) -> None:
        await save_state(self.name, state)

    def _read_chrome_history(self, last_ts: Any) -> Tuple[List[Dict[str, Any]], Any]:
        temp_copy = self._chrome_path.parent / "History.pkb"
        shutil.copy2(self._chrome_path, temp_copy)
        conn = sqlite3.connect(temp_copy)
        cursor = conn.cursor()
        query = (
            "SELECT urls.url, urls.title, visits.visit_time "
            "FROM urls JOIN visits ON urls.id = visits.url "
            "ORDER BY visits.visit_time DESC LIMIT 500"
        )
        cursor.execute(query)
        entries: List[Dict[str, Any]] = []
        latest = last_ts
        for url, title, visit_time in cursor.fetchall():
            visited_at = CHROME_EPOCH + timedelta(microseconds=visit_time)
            visited_iso = visited_at.isoformat()
            if last_ts and visited_iso <= last_ts:
                continue
            if not latest or visited_iso > latest:
                latest = visited_iso
            entries.append({"url": url, "title": title or url, "visited_at": visited_iso})
        conn.close()
        temp_copy.unlink(missing_ok=True)
        return entries, latest

    def _read_firefox_history(self, last_ts: Any) -> Tuple[List[Dict[str, Any]], Any]:
        profile_db = None
        for path in self._firefox_profile_dir.glob("*.default-release/places.sqlite"):
            profile_db = path
            break
        if profile_db is None:
            return [], last_ts
        temp_copy = profile_db.parent / "places.pkb.sqlite"
        shutil.copy2(profile_db, temp_copy)
        conn = sqlite3.connect(temp_copy)
        cursor = conn.cursor()
        query = "SELECT url, title, last_visit_date FROM moz_places ORDER BY last_visit_date DESC LIMIT 500"
        cursor.execute(query)
        entries: List[Dict[str, Any]] = []
        latest = last_ts
        for url, title, visit_time in cursor.fetchall():
            if visit_time is None:
                continue
            visited_at = datetime.fromtimestamp(visit_time / 1_000_000, tz=timezone.utc)
            visited_iso = visited_at.isoformat()
            if last_ts and visited_iso <= last_ts:
                continue
            if not latest or visited_iso > latest:
                latest = visited_iso
            entries.append({"url": url, "title": title or url, "visited_at": visited_iso})
        conn.close()
        temp_copy.unlink(missing_ok=True)
        return entries, latest

    def _build_sync_result(self, browser: str, entry: Dict[str, Any]) -> SyncResult:
        doc_id = f"{browser}:{hash(entry['url'])}"
        document = {
            "doc_id": doc_id,
            "version": entry["visited_at"],
            "title": entry["title"],
            "source": f"{browser}_history",
            "created_at": entry["visited_at"],
            "valid_from": entry["visited_at"],
            "valid_to": None,
            "system_from": datetime.now(timezone.utc).isoformat(),
            "system_to": None,
        }
        block = {
            "block_id": doc_id,
            "block_type": "web_history",
            "bounding_box": None,
            "text_content": entry["url"],
            "text_vector": None,
        }
        return SyncResult({"document": document, "block": block})
