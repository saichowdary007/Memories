# Personal Knowledge Brain

A local-first, privacy-preserving knowledge operating system for macOS (Apple Silicon) that unifies email, files, notes, calendars, chat, and browser activity into a single graph-powered memory. The stack couples FastAPI, Neo4j, LanceDB, Valkey, MinIO, and Ollama to deliver hybrid search, temporal reasoning, and multimodal understanding without sending telemetry off-device.

## Features
- **Hybrid retrieval** combining LanceDB vector search, Neo4j BM25 full‑text, and graph traversals, reranked with BGE reranker and diversified with MMR.
- **Multimodal ingestion** for text, PDFs (with OCR), images (SigLIP + pHash), and audio (Whisper-Large-V3-Turbo transcription).
- **Entity graph** capturing documents, people, events, places, and projects with temporal validity windows and near-duplicate detection (SHA256, SimHash, pHash).
- **Connectors** for Gmail, Google Drive, Photos, Calendar, Slack, Notion, Obsidian, Chrome/Firefox history, generic IMAP, Google Takeout archives, and monitored local folders with incremental sync.
- **Local UI** via Gradio chat with source citations plus REST API secured by JWT and rate limiting.
- **Operations** including Prometheus metrics, structured JSON logging, nightly backups (Neo4j dump, LanceDB snapshot, MinIO export, Valkey snapshot), and restoration tooling.

## Prerequisites
- macOS 14+ on Apple Silicon with at least 16 GB RAM and [Colima](https://github.com/abiosoft/colima) or Docker Desktop.
- [Ollama](https://ollama.ai) installed with the `qwen2.5:7b-instruct-q4_K_M` model pulled on the host.
- Python 3.11+, `make`, and `docker compose` available in `$PATH`.
- Google OAuth credentials (client ID/secret/refresh token), Slack bot token, Notion integration token, and IMAP credentials as needed.

## Quick Start
1. **Clone and configure**
   ```bash
   cp .env.example .env
   # populate secrets (NEO4J_PASSWORD, MINIO_SECRET_KEY, JWT_SECRET_KEY, OAuth tokens, etc.)
   ```
2. **Install dependencies (optional local tooling)**
   ```bash
   make install
   ```
3. **Launch services**
   ```bash
   docker compose --env-file .env up -d --build
   ```
4. **Seed demo content**
   ```bash
   make seed
   ```
5. **Open UI**
   ```bash
   python -m ui.gradio_app
   ```
   Enter a JWT obtained from `/auth/token` (or your own issuer) to start chatting.

## Services
| Component | Purpose | Port |
|-----------|---------|------|
| FastAPI (`pkb_api`) | REST API, metrics, auth | 8000 / 9001 |
| Worker (`pkb_worker`) | Connector orchestration, ingestion, backup | – |
| Neo4j | Graph storage (2 GB heap) | 7687 / 7474 |
| LanceDB | Embedded vector store (mounted under `/data/lancedb`) | – |
| Valkey | Redis-compatible cache + work queue | 6379 |
| MinIO | Object storage for binaries | 9000 / 9002 |
| Prometheus | Metrics scraping | 9090 |

## Commands
| Task | Command |
|------|---------|
| Build & start | `docker compose --env-file .env up -d --build` |
| Tail logs | `make logs` |
| Run tests | `make test` |
| Format & lint | `make format` / `make lint` |
| Type-check | `make mypy` |
| Seed sample data | `make seed` |
| Backup | `make backup` |
| Restore latest backup | `make restore` |

## Testing
- **Unit tests** (`tests/unit`) cover query planning, retrieval orchestration, and document processing.
- **Integration tests** (`tests/integration`) validate each connector against stubbed upstream APIs and local fixtures.
- Coverage is collected via `pytest --cov` (see `Makefile` target `make coverage`).

## Connectors
Connector configuration lives in `.env`; see [`docs/CONNECTORS.md`](docs/CONNECTORS.md) for scopes, tokens, and incremental sync strategy per provider.

## Backups & Restore
Nightly cron in the worker container runs `scripts/backup.sh`, producing timestamped archives under `./backups/`. Contents include:
- Neo4j node and relationship JSON export.
- LanceDB table snapshot (`lancedb.zip`).
- MinIO bucket dump.
- Valkey keyspace snapshot.

Restore from the latest backup via `make restore` or `python -m scripts.restore <timestamp>`.

## Security & Privacy
- JWT-secured API with configurable secret/expiry and rate limiting (SlowAPI) per endpoint.
- Structured JSON logging with correlation IDs; PII excluded from logs.
- No telemetry – all processing (LLM, embeddings, OCR) remains on-device.
- Face recognition is not implemented and remains disabled by design.

## Documentation
Additional guides are available under `docs/`:
- [`ARCHITECTURE.md`](docs/ARCHITECTURE.md) – system overview and data flow
- [`CONNECTORS.md`](docs/CONNECTORS.md) – connector configuration and OAuth scopes
- [`DEPLOYMENT.md`](docs/DEPLOYMENT.md) – local/macOS deployment tips
- [`TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) – diagnostics and recovery steps
- [`API.md`](docs/API.md) – endpoint reference and authentication notes

## License
MIT. See `LICENSE` (add if required).
