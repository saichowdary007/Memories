from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

registry = CollectorRegistry()
REQUEST_COUNT = Counter("pkb_request_count", "Total API requests", ["method", "endpoint"], registry=registry)
REQUEST_LATENCY = Histogram("pkb_request_latency_ms", "Request latency in milliseconds", ["endpoint"], registry=registry)
HEALTH_STATUS = Gauge("pkb_health_status", "Overall system health", registry=registry)
