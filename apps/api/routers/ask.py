from __future__ import annotations

import time
from typing import List

from fastapi import APIRouter, Depends, Request

from apps.api.middleware import get_current_user
from apps.api.models import AnswerCitation, AskRequest, AskResponse, TokenPayload
from apps.api.rate_limit import limiter
from apps.api.services import LLMService, RetrievalOrchestrator

router = APIRouter(prefix="/ask", tags=["ask"])

retrieval_service = RetrievalOrchestrator()
llm_service = LLMService()


@router.post("", response_model=AskResponse)
@limiter.limit("60/minute")
async def ask_endpoint(request: Request, payload: AskRequest, _: TokenPayload = Depends(get_current_user)) -> AskResponse:
    start = time.perf_counter()
    documents = await retrieval_service.retrieve(payload.query, top_k=payload.top_k)
    answer_text = await llm_service.generate(payload.query, [doc.__dict__ for doc in documents], stream=False)
    citations: List[AnswerCitation] = [
        AnswerCitation(source_uri=doc.uri, snippet=doc.text[:200], score=doc.score)
        for doc in documents
    ]
    latency_ms = int((time.perf_counter() - start) * 1000)
    return AskResponse(answer=answer_text, citations=citations, latency_ms=latency_ms)
