from __future__ import annotations

import logging
from typing import Callable

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.responses import JSONResponse, Response

from apps.api.metrics import REQUEST_COUNT, REQUEST_LATENCY, registry
from apps.api.middleware import LoggingMiddleware, register_exception_handlers
from apps.api.rate_limit import limiter
from apps.api.routers import ask_router, entities_router, health_router, ingest_router
from core.config import settings
from core.logging import configure_logging

configure_logging(settings.log_level)
logger = logging.getLogger(__name__)

app = FastAPI(title="Personal Knowledge Brain", version="0.1.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, lambda request, exc: JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"}))


def metrics_middleware(app: FastAPI) -> Callable:
    @app.middleware("http")
    async def _metrics(request: Request, call_next):
        endpoint = request.url.path
        with REQUEST_LATENCY.labels(endpoint).time():
            response = await call_next(request)
        REQUEST_COUNT.labels(request.method, endpoint).inc()
        return response

    return _metrics


app.add_middleware(LoggingMiddleware)
app.add_middleware(SlowAPIMiddleware)
metrics_middleware(app)
register_exception_handlers(app)

app.include_router(health_router)
app.include_router(ask_router)
app.include_router(ingest_router)
app.include_router(entities_router)

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin) for origin in settings.cors_origins],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.get("/metrics")
async def metrics() -> Response:
    data = generate_latest(registry)
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)
