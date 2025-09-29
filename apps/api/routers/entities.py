from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from apps.api.middleware import get_current_user
from apps.api.models import EntityHit, EntitySearchResponse, TokenPayload
from apps.api.rate_limit import limiter
from core.graph import graph_service

router = APIRouter(prefix="/entities", tags=["entities"])


@router.get("", response_model=EntitySearchResponse)
@limiter.limit("120/minute")
async def search_entities(q: str = Query(..., min_length=2), _: TokenPayload = Depends(get_current_user)) -> EntitySearchResponse:
    results = await graph_service.entity_search(q, limit=25)
    hits: list[EntityHit] = []
    for record in results:
        node = record.get("node")
        if node is None:
            continue
        properties = dict(node)
        hits.append(
            EntityHit(
                label=next(iter(node.labels), "Entity"),
                score=record.get("score", 0.0),
                properties={k: str(v) for k, v in properties.items()},
            )
        )
    return EntitySearchResponse(query=q, hits=hits)
