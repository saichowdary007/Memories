from __future__ import annotations

from pathlib import Path
from typing import Optional

from charset_normalizer import from_bytes


def extract_text_from_file(path: Path, mime_type: str) -> Optional[str]:
    if mime_type.startswith("text/"):
        return _read_text(path)
    if mime_type in {"application/json", "application/xml", "application/xhtml+xml"}:
        return _read_text(path)
    if path.suffix.lower() in {".md", ".txt", ".csv"}:
        return _read_text(path)
    return None


def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    result = from_bytes(raw).best()
    if result is None:
        return raw.decode("utf-8", errors="ignore")
    return str(result)
