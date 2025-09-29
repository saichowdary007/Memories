# Deployment Guide (macOS + Apple Silicon)

## Prerequisites
- macOS Sonoma or newer, Apple Silicon (M-series) with ≥16 GB RAM.
- [Homebrew](https://brew.sh/) or equivalent package manager.
- Docker Desktop or Colima (recommended for lower overhead):
  ```bash
  brew install colima
  colima start --arch arm64 --memory 12 --vm-type=vz --cpu 6
  ```
- Python 3.11 (via `pyenv`, Homebrew, or system Python) for local tooling/tests.
- OCR prerequisites (host, optional but recommended): `brew install poppler tesseract`
- [Ollama](https://ollama.ai) installed natively (`brew install ollama`). Pull required models on the host:
  ```bash
  ollama pull qwen2.5:7b-instruct-q4_K_M
  ```

## Environment Configuration
1. Duplicate `.env.example` to `.env` and populate:
   - `NEO4J_PASSWORD`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `JWT_SECRET_KEY` (strong secrets).
   - OAuth credentials: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN`, `GOOGLE_REDIRECT_URI`.
   - Connector tokens: `SLACK_BOT_TOKEN`, `NOTION_INTERNAL_INTEGRATION_TOKEN`, IMAP credentials.
   - Paths: `OBSIDIAN_VAULT_PATH`, `CHROME_HISTORY_PATH`, `FIREFOX_PROFILE_PATH`, `LOCAL_WATCH_PATHS`.
2. Optional: export `.env` variables into your shell to run scripts outside Docker.

## Bootstrapping
```bash
make install      # optional virtualenv for lint/test tooling
make up           # docker compose (alias for `docker compose up` via Makefile)
```

Monitor container health:
```bash
docker compose ps
make logs         # tails api + worker logs
```

Confirm health endpoint:
```bash
curl -H "Authorization: Bearer <token>" http://localhost:8000/health
```

## Worker Resources
- Worker container is capped at 3 GB RAM; remaining memory stays on host for Ollama models.
- `apps/workers/system/memory.py` enforces a 1.5 GB free-memory floor; adjust `SETTINGS__BACKPRESSURE_FREE_MEM_BYTES` if necessary.

## Model Preparation
- Embedding, reranker, OCR, and Whisper models download on first use and are cached under `~/.cache/pkb`. Ensure sufficient disk space (~8 GB).
- To prewarm models execute:
  ```bash
  docker compose exec worker python - <<'PY'
  from apps.workers.embeddings.text import text_embedding_service
  import asyncio
  asyncio.run(text_embedding_service.embed(["warmup"]))
  PY
  ```

## Nightly Backups
- Backups are written to `./backups/<timestamp>/` on the host (mounted into worker container).
- Customize schedule in `apps/workers/orchestrator.py` or disable via removing the cron job.

## Upgrading
1. Pull latest code.
2. Regenerate dependencies: `make install`.
3. Rebuild containers: `docker compose build --no-cache`.
4. Run migrations if Neo4j schema changes (update `db/neo4j_bootstrap.cypher`).

## Resource Tuning
- Neo4j heap/page cache: adjust `NEO4J_dbms_memory_*` env vars in `docker-compose.yml` if workload increases.
- LanceDB cache: configure via `SETTINGS__LANCEDB_URI` path on fast storage.
- Valkey memory policy currently `allkeys-lru` with 1 GB limit; modify command in compose file to suit workload.

## Troubleshooting
- Check `docs/TROUBLESHOOTING.md` for common issues.
- Validate connectors offline using integration tests: `pytest tests/integration/test_connectors.py -k gmail`.
