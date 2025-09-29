from __future__ import annotations

import asyncio
import base64
import email
from datetime import datetime, timezone
from email.message import Message
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

from aioimaplib import aioimaplib

from connectors.base import BaseConnector, SyncResult
from connectors.state_store import load_state, save_state
from core.config import settings

CACHE_DIR = Path.home() / ".cache" / "pkb" / "imap"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


class GenericIMAPConnector(BaseConnector):
    name = "generic_imap"

    def __init__(self) -> None:
        if not settings.generic_imap_host or not settings.generic_imap_username or not settings.generic_imap_password:
            raise RuntimeError("Generic IMAP credentials not configured")
        self._host = settings.generic_imap_host
        self._port = settings.generic_imap_port
        self._username = settings.generic_imap_username
        self._password = settings.generic_imap_password

    async def sync(self) -> AsyncIterator[SyncResult]:  # type: ignore[override]
        state = await load_state(self.name)
        last_uid = state.get("last_uid", 0)

        client = aioimaplib.IMAP4_SSL(self._host, self._port)
        await client.wait_hello_from_server()
        await client.login(self._username, self._password)
        await client.select("INBOX")

        search_query = f"UID {last_uid + 1}:*" if last_uid else "ALL"
        status, data = await client.uid("SEARCH", None, search_query)
        if status != "OK":
            await client.logout()
            return
        uids = [int(uid) for uid in data[0].split()] if data and data[0] else []
        uids.sort()
        newest_uid = last_uid
        for uid in uids:
            status, message_data = await client.uid("FETCH", str(uid), "(RFC822)")
            if status != "OK" or not message_data:
                continue
            raw_email = message_data[0][1]
            message: Message = email.message_from_bytes(raw_email)
            subject = email.header.decode_header(message.get("Subject", ""))
            subject_str = " ".join(
                fragment.decode(encoding or "utf-8", errors="ignore") if isinstance(fragment, bytes) else fragment
                for fragment, encoding in subject
            )
            sender = email.utils.parseaddr(message.get("From", ""))[1]
            recipients = [addr for _, addr in email.utils.getaddresses(message.get_all("To", []))]
            sent = email.utils.parsedate_to_datetime(message.get("Date")) or datetime.now(timezone.utc)
            text_parts: List[str] = []
            attachments: List[Dict[str, Any]] = []
            for part in message.walk():
                content_type = part.get_content_type()
                disposition = part.get("Content-Disposition", "")
                if part.is_multipart():
                    continue
                if "attachment" in disposition:
                    filename = part.get_filename() or f"attachment-{uid}"
                    payload = part.get_payload(decode=True)
                    if payload:
                        file_path = CACHE_DIR / filename
                        file_path.write_bytes(payload)
                        attachments.append(
                            {
                                "uri": str(file_path),
                                "mime_type": content_type,
                                "size_bytes": len(payload),
                                "created_at": sent.isoformat(),
                            }
                        )
                else:
                    payload_bytes = part.get_payload(decode=True)
                    payload_text = payload_bytes.decode(part.get_content_charset() or "utf-8", errors="ignore") if payload_bytes else ""
                    text_parts.append(payload_text)
            text_content = "\n".join(text_parts)
            doc_id = f"imap:{uid}"
            document = {
                "doc_id": doc_id,
                "version": str(uid),
                "title": subject_str or "IMAP Message",
                "source": "imap",
                "created_at": sent.isoformat(),
                "valid_from": sent.isoformat(),
                "valid_to": None,
                "system_from": datetime.now(timezone.utc).isoformat(),
                "system_to": None,
            }
            email_node = {
                "message_id": doc_id,
                "thread_id": None,
                "subject": subject_str,
                "sent_at": sent.isoformat(),
                "sender": sender,
                "recipients": recipients,
                "cc_list": [],
                "bcc_list": [],
                "snippet": text_content[:200],
                "text_vector": None,
            }
            files = attachments
            files.append(
                {
                    "uri": self._write_body(doc_id, text_content),
                    "mime_type": "text/plain",
                    "size_bytes": len(text_content.encode("utf-8")),
                    "created_at": sent.isoformat(),
                }
            )
            newest_uid = max(newest_uid, uid)
            yield SyncResult({"document": document, "email": email_node, "files": files})
        if newest_uid > last_uid:
            await save_state(self.name, {"last_uid": newest_uid})
        await client.logout()

    async def checkpoint(self, state: Dict[str, Any]) -> None:
        await save_state(self.name, state)

    def _write_body(self, doc_id: str, content: str) -> str:
        file_path = CACHE_DIR / f"{doc_id}.txt"
        file_path.write_text(content, encoding="utf-8")
        return str(file_path)
