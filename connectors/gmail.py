from __future__ import annotations

import asyncio
import base64
import email
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from connectors.base import BaseConnector, SyncResult
from connectors.google_auth import ensure_credentials
from connectors.state_store import load_state, save_state

CACHE_DIR = Path.home() / ".cache" / "pkb" / "gmail"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _decode_payload(message_part: Dict[str, Any]) -> str:
    body = message_part.get("body", {})
    data = body.get("data")
    if not data:
        return ""
    decoded = base64.urlsafe_b64decode(data.encode("utf-8"))
    return decoded.decode("utf-8", errors="ignore")


def _parse_message(payload: Dict[str, Any]) -> Dict[str, Any]:
    headers = payload.get("headers", [])
    header_lookup = {header["name"].lower(): header["value"] for header in headers}
    subject = header_lookup.get("subject", "(no subject)")
    sender = email.utils.parseaddr(header_lookup.get("from", ""))[1]
    recipients = [addr for _, addr in email.utils.getaddresses([header_lookup.get("to", "")])]
    cc = [addr for _, addr in email.utils.getaddresses([header_lookup.get("cc", "")])]
    bcc = [addr for _, addr in email.utils.getaddresses([header_lookup.get("bcc", "")])]
    snippet = payload.get("snippet", "")

    text_parts: List[str] = []
    attachments: List[Dict[str, Any]] = []

    def walk_parts(part: Dict[str, Any]) -> None:
        mime_type = part.get("mimeType", "")
        filename = part.get("filename")
        body = part.get("body", {})
        if mime_type.startswith("multipart"):
            for child in part.get("parts", []) or []:
                walk_parts(child)
        elif filename and body.get("attachmentId"):
            attachments.append({"filename": filename, "mime_type": mime_type, "attachmentId": body["attachmentId"]})
        else:
            text_parts.append(_decode_payload(part))

    walk_parts(payload)
    text_content = "\n".join(filter(None, text_parts))

    timestamp_header = header_lookup.get("date")
    if timestamp_header:
        parsed_date = email.utils.parsedate_to_datetime(timestamp_header)
    else:
        parsed_date = datetime.now(timezone.utc)

    return {
        "subject": subject,
        "sender": sender,
        "recipients": recipients,
        "cc": cc,
        "bcc": bcc,
        "snippet": snippet,
        "text": text_content,
        "timestamp": parsed_date,
        "attachments": attachments,
    }


class GmailConnector(BaseConnector):
    name = "gmail"

    def __init__(self, user_id: str = "me") -> None:
        self._user_id = user_id

    async def _service(self):
        creds = await ensure_credentials("gmail")

        def _build():
            return build("gmail", "v1", credentials=creds, cache_discovery=False)

        return await asyncio.to_thread(_build)

    async def sync(self) -> AsyncIterator[SyncResult]:  # type: ignore[override]
        service = await self._service()
        state = await load_state(self.name)
        history_id = state.get("history_id")
        newest_history_id: Optional[int] = None

        message_ids: List[str] = []
        try:
            if history_id:
                page_token: Optional[str] = None
                while True:
                    request = service.users().history().list(
                        userId=self._user_id,
                        startHistoryId=history_id,
                        historyTypes=["messageAdded"],
                        pageToken=page_token,
                    )
                    response = await asyncio.to_thread(request.execute)
                    histories = response.get("history", [])
                    for history_item in histories:
                        newest_history_id = max(newest_history_id or 0, int(history_item.get("id", 0)))
                        for message in history_item.get("messagesAdded", []):
                            message_ids.append(message["message"]["id"])
                    page_token = response.get("nextPageToken")
                    if not page_token:
                        break
                if not message_ids:
                    return
            else:
                request = service.users().messages().list(userId=self._user_id, maxResults=50, q="-category:{promotions social updates forums}")
                response = await asyncio.to_thread(request.execute)
                for message in response.get("messages", []):
                    message_ids.append(message["id"])
        except HttpError as exc:
            if exc.resp.status == 404:
                history_id = None
            else:
                raise

        for msg_id in message_ids:
            payload = await self._fetch_message(service, msg_id)
            if payload is None:
                continue
            parsed = _parse_message(payload)
            attachments = await self._download_attachments(service, msg_id, parsed["attachments"])
            doc_id = f"gmail:{msg_id}"
            timestamp = parsed["timestamp"]
            document = {
                "doc_id": doc_id,
                "version": payload.get("historyId"),
                "title": parsed["subject"],
                "source": "gmail",
                "created_at": timestamp.isoformat(),
                "valid_from": timestamp.isoformat(),
                "valid_to": None,
                "system_from": datetime.now(timezone.utc).isoformat(),
                "system_to": None,
            }
            email_node = {
                "message_id": doc_id,
                "thread_id": payload.get("threadId"),
                "subject": parsed["subject"],
                "sent_at": timestamp.isoformat(),
                "sender": parsed["sender"],
                "recipients": parsed["recipients"],
                "cc_list": parsed["cc"],
                "bcc_list": parsed["bcc"],
                "snippet": parsed["snippet"],
                "text_vector": None,
            }
            files: List[Dict[str, Any]] = attachments
            files.append(
                {
                    "uri": self._write_email_to_disk(doc_id, parsed["text"]),
                    "mime_type": "text/plain",
                    "size_bytes": len(parsed["text"].encode("utf-8")),
                    "created_at": timestamp.isoformat(),
                }
            )
            people = list({parsed["sender"], *parsed["recipients"], *parsed["cc"], *parsed["bcc"]} - {""})
            yield SyncResult(
                {
                    "document": document,
                    "email": email_node,
                    "files": files,
                    "entities": {"people": people},
                }
            )

        if newest_history_id:
            await save_state(self.name, {"history_id": newest_history_id})
        elif message_ids:
            first_payload = await self._fetch_message(service, message_ids[-1])
            if first_payload and first_payload.get("historyId"):
                await save_state(self.name, {"history_id": int(first_payload["historyId"])})

    async def checkpoint(self, state: Dict[str, Any]) -> None:
        await save_state(self.name, state)

    async def _fetch_message(self, service, message_id: str) -> Optional[Dict[str, Any]]:
        request = service.users().messages().get(userId=self._user_id, id=message_id, format="full")
        try:
            response = await asyncio.to_thread(request.execute)
            return response
        except HttpError as exc:
            if exc.resp.status == 404:
                return None
            raise

    async def _download_attachments(self, service, message_id: str, attachments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        stored: List[Dict[str, Any]] = []
        for attachment in attachments:
            attachment_id = attachment["attachmentId"]
            request = service.users().messages().attachments().get(userId=self._user_id, messageId=message_id, id=attachment_id)
            response = await asyncio.to_thread(request.execute)
            data = response.get("data")
            if not data:
                continue
            binary = base64.urlsafe_b64decode(data.encode("utf-8"))
            file_path = CACHE_DIR / f"{message_id}-{attachment['filename']}"
            file_path.write_bytes(binary)
            stored.append(
                {
                    "uri": str(file_path),
                    "mime_type": attachment["mime_type"],
                    "size_bytes": len(binary),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            )
        return stored

    def _write_email_to_disk(self, doc_id: str, text: str) -> str:
        file_path = CACHE_DIR / f"{doc_id}.txt"
        file_path.write_text(text, encoding="utf-8")
        return str(file_path)
