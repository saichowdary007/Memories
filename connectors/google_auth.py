from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, Optional

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

from core.config import settings

TOKEN_PATH = Path.home() / ".config" / "pkb" / "google_token.json"
TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)

GOOGLE_SCOPES = {
    "gmail": [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.modify",
    ],
    "drive": [
        "https://www.googleapis.com/auth/drive.readonly",
        "https://www.googleapis.com/auth/drive.metadata.readonly",
    ],
    "photos": [
        "https://www.googleapis.com/auth/photoslibrary.readonly",
        "https://www.googleapis.com/auth/photoslibrary.sharing",
    ],
    "calendar": [
        "https://www.googleapis.com/auth/calendar.readonly",
    ],
}


def _base_credentials() -> Credentials:
    if not settings.google_client_id or not settings.google_client_secret or not settings.google_refresh_token:
        raise RuntimeError("Google OAuth credentials missing; set GOOGLE_CLIENT_ID/SECRET/REFRESH_TOKEN")
    creds = Credentials(
        None,
        refresh_token=settings.google_refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
    )
    return creds


async def ensure_credentials(namespace: str) -> Credentials:
    scopes = GOOGLE_SCOPES.get(namespace)
    if not scopes:
        raise ValueError(f"Unknown Google namespace: {namespace}")

    def _load() -> Credentials:
        creds: Optional[Credentials] = None
        if TOKEN_PATH.exists():
            data = json.loads(TOKEN_PATH.read_text())
            token = data.get(namespace)
            if token:
                creds = Credentials.from_authorized_user_info(token, scopes)
        if creds and creds.valid:
            return creds
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            _persist(namespace, creds)
            return creds
        base = _base_credentials()
        base = base.with_scopes(scopes)
        base.refresh(Request())
        _persist(namespace, base)
        return base

    return await asyncio.to_thread(_load)


def _persist(namespace: str, creds: Credentials) -> None:
    data: Dict[str, Any] = {}
    if TOKEN_PATH.exists():
        data = json.loads(TOKEN_PATH.read_text())
    data[namespace] = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes,
        "expiry": creds.expiry.isoformat() if creds.expiry else None,
    }
    TOKEN_PATH.write_text(json.dumps(data, indent=2))
