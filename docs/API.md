# API Reference

All endpoints require JWT authentication via the `Authorization: Bearer <token>` header. Issue tokens using your identity provider and configure `SETTINGS__JWT_SECRET_KEY`/`SETTINGS__JWT_ALGORITHM` accordingly.

Base URL: `http://localhost:8000`

## `POST /ask`
- **Description**: Executes the full retrieval + generation pipeline and returns an answer with citations.
- **Body**
  ```json
  {
    "query": "What emails did I receive about Project Alpha?",
    "top_k": 10,
    "include_sources": true
  }
  ```
- **Response**
  ```json
  {
    "answer": "You received two emails about Project Alpha...",
    "citations": [
      {
        "source_uri": "minio://pkb-artifacts/gmail/...",
        "snippet": "Project Alpha kickoff",
        "score": 0.92
      }
    ],
    "latency_ms": 1340
  }
  ```

## `POST /ingest`
- **Description**: Queues an external document bundle for ingestion (worker processes asynchronously).
- **Body**
  ```json
  {
    "doc_id": "custom:doc-1",
    "title": "Strategy Deck",
    "source": "manual",
    "created_at": "2024-09-12T09:00:00Z",
    "valid_from": "2024-09-12T09:00:00Z",
    "files": [
      {
        "uri": "file:///Users/me/Documents/strategy.pdf",
        "mime_type": "application/pdf",
        "sha256": "...",
        "size_bytes": 12345
      }
    ]
  }
  ```
- **Response** `202 Accepted`
  ```json
  {"status": "queued", "doc_id": "custom:doc-1"}
  ```

## `GET /entities`
- **Description**: Full-text search over entity nodes (Person, Organization, Project, Place).
- **Query params**: `q` (string, min length 2)
- **Response**
  ```json
  {
    "query": "Project Alpha",
    "hits": [
      {
        "label": "Project",
        "score": 0.88,
        "properties": {
          "project_id": "project:...",
          "project_name": "Project Alpha"
        }
      }
    ]
  }
  ```

## `GET /health`
- **Description**: Reports subsystem health (Neo4j, Valkey, MinIO, LanceDB, memory guard). No auth required.
- **Response**
  ```json
  {
    "status": "pass",
    "timestamp": "2024-09-12T12:00:00+00:00",
    "dependencies": [
      {"name": "neo4j", "status": "pass", "latency_ms": 15},
      {"name": "memory", "status": "pass", "details": "free=..."}
    ]
  }
  ```

## Rate Limits
- Default: 60 requests/minute per IP (`SETTINGS__RATE_LIMIT`). Connector endpoints share the same limiter.
- Responses exceeding limit return HTTP 429 with JSON `{"detail": "Rate limit exceeded"}`.

## Metrics
- `GET /metrics` exposes Prometheus metrics (`pkb_request_count`, `pkb_request_latency_ms`, `pkb_health_status`).

## Authentication
- JWT tokens must include a `sub` claim (subject) and expiration; `apps/api/middleware/auth.py` validates signature and expiry.
- Use `create_access_token(subject)` helper from backend for integration testing.

## Error Handling
- FastAPI exception handlers return JSON with `{"detail": "..."}`.
- Validation errors leverage FastAPI/Pydantic standard responses (422).

## Web UI
- `ui/gradio_app.py` wraps `/ask` and `/entities` endpoints. Launch via `python -m ui.gradio_app` and provide a valid JWT token when prompted.
