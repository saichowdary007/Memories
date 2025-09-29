from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from apps.api.middleware import get_current_user
from apps.api.models import IngestRequest, TokenPayload
from apps.api.rate_limit import limiter
from core.cache import valkey_client

router = APIRouter(prefix="/ingest", tags=["ingest"])

QUEUE_NAME = "ingest:documents"


@router.post("", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("30/minute")
async def ingest_document(payload: IngestRequest, _: TokenPayload = Depends(get_current_user)) -> dict[str, str]:
    job = payload.model_dump()
    await valkey_client.enqueue(QUEUE_NAME, job)
    return {"status": "queued", "doc_id": payload.doc_id}
