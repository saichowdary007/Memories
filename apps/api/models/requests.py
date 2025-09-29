from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(default=10, ge=1, le=50)
    include_sources: bool = Field(default=True)
    filters: Optional[dict[str, str]] = Field(default=None)


class IngestFileDescriptor(BaseModel):
    uri: str
    mime_type: str
    sha256: str
    size_bytes: int


class IngestRequest(BaseModel):
    doc_id: str
    title: str
    source: str
    created_at: datetime
    valid_from: datetime
    valid_to: Optional[datetime] = None
    files: List[IngestFileDescriptor]
