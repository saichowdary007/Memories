from __future__ import annotations

import json
import logging
import sys
import uuid
from contextvars import ContextVar
from typing import Any, Dict

from pythonjsonlogger import jsonlogger

request_id_ctx_var: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIDFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx_var.get()
        return True


def configure_logging(level: str = "INFO") -> None:
    log_handler = logging.StreamHandler(sys.stdout)
    formatter = jsonlogger.JsonFormatter("%(asctime)s %(name)s %(levelname)s %(request_id)s %(message)s")
    log_handler.setFormatter(formatter)
    log_handler.addFilter(RequestIDFilter())

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers.clear()
    root_logger.addHandler(log_handler)


def set_request_id(value: str | None = None) -> str:
    request_id = value or str(uuid.uuid4())
    request_id_ctx_var.set(request_id)
    return request_id


def log_event(logger: logging.Logger, event: str, **fields: Any) -> None:
    logger.info(json.dumps({"event": event, **fields}))


configure_logging()
