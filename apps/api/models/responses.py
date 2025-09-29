from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class AnswerCitation(BaseModel):
    source_uri: str
    snippet: str
    score: float


class AskResponse(BaseModel):
    answer: str
    citations: List[AnswerCitation]
    reasoning: Optional[str] = None
    latency_ms: int


class HealthDependency(BaseModel):
    name: str
    status: str
    latency_ms: int
    details: Optional[str] = None


class HealthStatus(BaseModel):
    status: str
    timestamp: datetime
    dependencies: List[HealthDependency]


class EntityHit(BaseModel):
    label: str
    score: float
    properties: dict[str, str]


class EntitySearchResponse(BaseModel):
    query: str
    hits: List[EntityHit]
