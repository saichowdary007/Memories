import asyncio
import base64
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import pytest

from connectors.browser import BrowserHistoryConnector
from connectors.calendar import GoogleCalendarConnector
from connectors.drive import DriveConnector
from connectors.gmail import GmailConnector
from connectors.imap import GenericIMAPConnector
from connectors.local_fs import LocalFilesystemConnector
from connectors.notion import NotionConnector
from connectors.obsidian import ObsidianConnector
from connectors.photos import GooglePhotosConnector
from connectors.slack import SlackConnector
from connectors.takeout import GoogleTakeoutConnector


@pytest.mark.asyncio
async def test_gmail_connector(monkeypatch, tmp_path):
    async def load_state(name: str) -> Dict[str, Any]:
        return {}

    async def save_state(name: str, state: Dict[str, Any]) -> None:
        return None

    class AttachmentStub:
        def get(self, userId: str, messageId: str, id: str):
            class Request:
                def execute(self_inner):
                    return {"data": base64.urlsafe_b64encode(b"attachment").decode("utf-8")}

            return Request()

    class MessagesStub:
        def list(self, userId: str, maxResults: int, q: str):
            class Request:
                def execute(self_inner):
                    return {"messages": [{"id": "msg-1"}]}

            return Request()

        def get(self, userId: str, id: str, format: str):
            class Request:
                def execute(self_inner):
                    return {
                        "id": id,
                        "threadId": "thread-1",
                        "historyId": "2",
                        "payload": {
                            "headers": [
                                {"name": "Subject", "value": "Welcome"},
                                {"name": "From", "value": "Alice <alice@example.com>"},
                                {"name": "To", "value": "Bob <bob@example.com>"},
                                {"name": "Date", "value": datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")},
                            ],
                            "parts": [
                                {
                                    "mimeType": "text/plain",
                                    "body": {"data": base64.urlsafe_b64encode(b"Hello Bob").decode("utf-8")},
                                },
                                {
                                    "mimeType": "application/pdf",
                                    "filename": "file.pdf",
                                    "body": {"attachmentId": "att-1"},
                                },
                            ],
                            "snippet": "Hello",
                        },
                    }

            return Request()

        def attachments(self):
            return AttachmentStub()

    class UsersStub:
        def __init__(self) -> None:
            self._messages = MessagesStub()

        def messages(self):
            return self._messages

        def history(self):
            class HistoryStub:
                def list(self, **kwargs):
                    class Request:
                        def execute(self_inner):
                            return {"history": []}

                    return Request()

            return HistoryStub()

    class ServiceStub:
        def users(self):
            return UsersStub()

    async def stub_service(self):
        return ServiceStub()

    monkeypatch.setattr("connectors.gmail.load_state", load_state)
    monkeypatch.setattr("connectors.gmail.save_state", save_state)
    monkeypatch.setattr(GmailConnector, "_service", stub_service)
    connector = GmailConnector()

    results = []
    async for item in connector.sync():
        results.append(item)
    assert results
    first = results[0]
    assert first["document"]["source"] == "gmail"


@pytest.mark.asyncio
async def test_drive_connector(monkeypatch, tmp_path):
    async def load_state(name: str) -> Dict[str, Any]:
        return {"start_page_token": "1"}

    async def save_state(name: str, state: Dict[str, Any]) -> None:
        return None

    class FilesStub:
        def export_media(self, fileId: str, mimeType: str):
            class Request:
                def execute(self_inner):
                    return None

            return Request()

        def get_media(self, fileId: str, supportsAllDrives: bool):
            class Request:
                def __init__(self):
                    self._chunks = [b"data"]

                def next_chunk(self_inner):
                    if self_inner._chunks:
                        data = self_inner._chunks.pop()
                        return type("Status", (), {"progress": 1.0})(), True
                    return None, True

            return Request()

        def get(self, fileId: str, fields: str, supportsAllDrives: bool):
            class Request:
                def execute(self_inner):
                    return {
                        "id": fileId,
                        "name": "Doc",
                        "mimeType": "text/plain",
                        "modifiedTime": datetime.now(timezone.utc).isoformat(),
                        "createdTime": datetime.now(timezone.utc).isoformat(),
                        "version": "1",
                        "owners": [{"emailAddress": "owner@example.com"}],
                    }

            return Request()

    class ChangesStub:
        def list(self, **kwargs):
            class Request:
                def execute(self_inner):
                    return {
                        "changes": [
                            {
                                "fileId": "file-1",
                                "file": {"trashed": False, "id": "file-1"},
                            }
                        ]
                    }

            return Request()

        def getStartPageToken(self):
            class Request:
                def execute(self_inner):
                    return {"startPageToken": "1"}

            return Request()

    class ServiceStub:
        def files(self):
            return FilesStub()

        def changes(self):
            return ChangesStub()

    async def stub_service(self):
        return ServiceStub()

    monkeypatch.setattr("connectors.drive.load_state", load_state)
    monkeypatch.setattr("connectors.drive.save_state", save_state)
    monkeypatch.setattr(DriveConnector, "_service", stub_service)

    connector = DriveConnector()
    results = []
    async for item in connector.sync():
        results.append(item)
    assert results
    assert results[0]["document"]["source"] == "google_drive"


@pytest.mark.asyncio
async def test_calendar_connector(monkeypatch):
    async def load_state(name: str) -> Dict[str, Any]:
        return {}

    async def save_state(name: str, state: Dict[str, Any]) -> None:
        return None

    class EventsStub:
        def list(self, **kwargs):
            class Request:
                def execute(self_inner):
                    return {
                        "items": [
                            {
                                "id": "evt-1",
                                "summary": "Standup",
                                "start": {"dateTime": datetime.now(timezone.utc).isoformat()},
                                "end": {"dateTime": datetime.now(timezone.utc).isoformat()},
                                "attendees": [{"email": "alice@example.com"}],
                                "etag": "etag",
                                "created": datetime.now(timezone.utc).isoformat(),
                            }
                        ]
                    }

            return Request()

    class ServiceStub:
        def events(self):
            return EventsStub()

    async def stub_service(self):
        return ServiceStub()

    monkeypatch.setattr("connectors.calendar.load_state", load_state)
    monkeypatch.setattr("connectors.calendar.save_state", save_state)
    monkeypatch.setattr(GoogleCalendarConnector, "_service", stub_service)

    connector = GoogleCalendarConnector()
    results = []
    async for item in connector.sync():
        results.append(item)
    assert results
    assert results[0]["document"]["source"] == "google_calendar"


@pytest.mark.asyncio
async def test_slack_connector(monkeypatch):
    from core.config import settings

    monkeypatch.setattr(settings, "slack_bot_token", "xoxb-test")

    class AsyncWebStub:
        async def conversations_list(self, limit: int):
            return {"channels": [{"id": "C01"}]}

        async def conversations_history(self, channel: str, cursor: str | None, limit: int, inclusive: bool):
            return {
                "messages": [
                    {"ts": "1.0", "text": "Hello", "files": []}
                ]
            }

    monkeypatch.setattr("connectors.slack.AsyncWebClient", lambda token: AsyncWebStub())

    async def load_state(name: str) -> Dict[str, Any]:
        return {}

    async def save_state(name: str, state: Dict[str, Any]) -> None:
        return None

    monkeypatch.setattr("connectors.slack.load_state", load_state)
    monkeypatch.setattr("connectors.slack.save_state", save_state)

    connector = SlackConnector()
    results = []
    async for item in connector.sync():
        results.append(item)
    assert results
    assert results[0]["document"]["source"] == "slack"


@pytest.mark.asyncio
async def test_notion_connector(monkeypatch):
    from core.config import settings

    monkeypatch.setattr(settings, "notion_internal_integration_token", "secret")

    class AsyncNotionStub:
        async def search(self, **kwargs):
            return {
                "results": [
                    {
                        "id": "page-1",
                        "last_edited_time": datetime.now(timezone.utc).isoformat(),
                    }
                ],
                "has_more": False,
            }

        async def pages(self, **kwargs):  # type: ignore[override]
            return self

        async def retrieve(self, page_id: str):
            return {
                "id": page_id,
                "created_time": datetime.now(timezone.utc).isoformat(),
                "last_edited_time": datetime.now(timezone.utc).isoformat(),
                "properties": {
                    "title": {"title": [{"plain_text": "Notion Page"}]}
                },
            }

        async def blocks(self, **kwargs):  # type: ignore[override]
            return self

        async def children(self, **kwargs):  # type: ignore[override]
            return self

        async def list(self, block_id: str, page_size: int):
            return {
                "results": [
                    {
                        "paragraph": {
                            "rich_text": [{"plain_text": "Paragraph"}]
                        }
                    }
                ]
            }

    monkeypatch.setattr("connectors.notion.AsyncClient", lambda auth: AsyncNotionStub())
    async def load_state(name: str) -> Dict[str, Any]:
        return {}

    async def save_state(name: str, state: Dict[str, Any]) -> None:
        return None

    monkeypatch.setattr("connectors.notion.load_state", load_state)
    monkeypatch.setattr("connectors.notion.save_state", save_state)

    connector = NotionConnector()
    results = []
    async for item in connector.sync():
        results.append(item)
    assert results
    assert results[0]["document"]["source"] == "notion"


@pytest.mark.asyncio
async def test_obsidian_connector(monkeypatch, tmp_path):
    from core.config import settings

    vault = tmp_path / "vault"
    vault.mkdir()
    note = vault / "note.md"
    note.write_text("# Note", encoding="utf-8")

    monkeypatch.setattr(settings, "obsidian_vault_path", str(vault))
    async def load_state(name: str) -> Dict[str, Any]:
        return {"files": {}}

    async def save_state(name: str, state: Dict[str, Any]) -> None:
        return None

    monkeypatch.setattr("connectors.obsidian.load_state", load_state)
    monkeypatch.setattr("connectors.obsidian.save_state", save_state)
    connector = ObsidianConnector()

    results = []
    async for item in connector.sync():
        results.append(item)
    assert results
    assert results[0]["document"]["source"] == "obsidian"


@pytest.mark.asyncio
async def test_browser_connector(monkeypatch, tmp_path):
    chrome_db = tmp_path / "History"
    chrome_db.write_bytes(b"")

    def copy2(src, dst):
        Path(dst).write_bytes(b"")

    monkeypatch.setattr("connectors.browser.shutil.copy2", copy2)
    monkeypatch.setattr("connectors.browser.sqlite3.connect", lambda path: _sqlite_stub())

    connector = BrowserHistoryConnector()
    monkeypatch.setattr(connector, "_chrome_path", chrome_db)
    monkeypatch.setattr(connector, "_firefox_profile_dir", tmp_path)

    results = []
    async for item in connector.sync():
        results.append(item)
    assert isinstance(results, list)


class _sqlite_stub:
    def __init__(self):
        self.cursor_obj = _cursor_stub()

    def cursor(self):
        return self.cursor_obj

    def close(self):
        return None


class _cursor_stub:
    def execute(self, query):
        self._data = [("https://example.com", "Example", 13217451500000000)]

    def fetchall(self):
        return self._data


@pytest.mark.asyncio
async def test_local_fs_connector(monkeypatch, tmp_path):
    from core.config import settings

    file_path = tmp_path / "doc.txt"
    file_path.write_text("content", encoding="utf-8")
    monkeypatch.setattr(settings, "local_watch_paths", [str(tmp_path)])
    async def load_state(name: str) -> Dict[str, Any]:
        return {"files": {}}

    async def save_state(name: str, state: Dict[str, Any]) -> None:
        return None

    monkeypatch.setattr("connectors.local_fs.load_state", load_state)
    monkeypatch.setattr("connectors.local_fs.save_state", save_state)

    connector = LocalFilesystemConnector()
    results = []
    async for item in connector.sync():
        results.append(item)
    assert results


@pytest.mark.asyncio
async def test_takeout_connector(monkeypatch, tmp_path):
    from core.config import settings

    takeout_dir = tmp_path / "Takeout"
    takeout_dir.mkdir()
    sample = takeout_dir / "sample.json"
    sample.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(settings, "google_takeout_path", str(takeout_dir))
    async def load_state(name: str) -> Dict[str, Any]:
        return {"hashes": {}}

    async def save_state(name: str, state: Dict[str, Any]) -> None:
        return None

    monkeypatch.setattr("connectors.takeout.load_state", load_state)
    monkeypatch.setattr("connectors.takeout.save_state", save_state)

    connector = GoogleTakeoutConnector()
    results = []
    async for item in connector.sync():
        results.append(item)
    assert results


@pytest.mark.asyncio
async def test_photos_connector(monkeypatch):
    async def load_state(name: str) -> Dict[str, Any]:
        return {}

    async def save_state(name: str, state: Dict[str, Any]) -> None:
        return None

    class MediaItemsStub:
        def list(self, pageSize: int, pageToken: str | None = None):
            class Request:
                def execute(self_inner):
                    return {
                        "mediaItems": [
                            {
                                "id": "img-1",
                                "filename": "photo.jpg",
                                "baseUrl": "https://example.com/photo",
                                "mimeType": "image/jpeg",
                                "mediaMetadata": {"creationTime": datetime.now(timezone.utc).isoformat()},
                            }
                        ]
                    }

            return Request()

    class ServiceStub:
        def mediaItems(self):
            return MediaItemsStub()

    async def stub_service(self):
        return ServiceStub()

    async def download_stub(self, client, base_url, filename, mime_type):
        path = Path.cwd() / filename
        path.write_bytes(b"binary")
        return str(path)

    monkeypatch.setattr("connectors.photos.load_state", load_state)
    monkeypatch.setattr("connectors.photos.save_state", save_state)
    monkeypatch.setattr(GooglePhotosConnector, "_service", stub_service)
    monkeypatch.setattr(GooglePhotosConnector, "_download_media", download_stub)

    connector = GooglePhotosConnector()
    results = []
    async for item in connector.sync():
        results.append(item)
    assert results


@pytest.mark.asyncio
async def test_generic_imap_connector(monkeypatch):
    from core.config import settings

    monkeypatch.setattr(settings, "generic_imap_host", "imap.example.com")
    monkeypatch.setattr(settings, "generic_imap_username", "user")
    monkeypatch.setattr(settings, "generic_imap_password", "pass")

    class ClientStub:
        async def wait_hello_from_server(self):
            return None

        async def login(self, username: str, password: str):
            return None

        async def select(self, mailbox: str):
            return None

        async def uid(self, command: str, *args):
            if command == "SEARCH":
                return "OK", [b"1"]
            if command == "FETCH":
                return "OK", [(None, b"From: Alice\nTo: Bob\nSubject: Test\n\nBody")]
            return "NO", []

        async def logout(self):
            return None

    monkeypatch.setattr("connectors.imap.aioimaplib.IMAP4_SSL", lambda host, port: ClientStub())
    async def load_state(name: str) -> Dict[str, Any]:
        return {"last_uid": 0}

    async def save_state(name: str, state: Dict[str, Any]) -> None:
        return None

    monkeypatch.setattr("connectors.imap.load_state", load_state)
    monkeypatch.setattr("connectors.imap.save_state", save_state)

    connector = GenericIMAPConnector()
    results = []
    async for item in connector.sync():
        results.append(item)
    assert results
