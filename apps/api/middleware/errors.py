from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request, exc: HTTPException):  # type: ignore[override]
        logger.warning("HTTP error", extra={"status": exc.status_code, "detail": exc.detail})
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request, exc: Exception):  # type: ignore[override]
        logger.exception("Unhandled server error")
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})
