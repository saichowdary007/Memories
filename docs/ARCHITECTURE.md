# Architecture Overview

Personal Knowledge Brain (PKB) is composed of four layers that run entirely on the local machine:

1. **Data ingestion** via asynchronous connectors (Gmail, Drive, Photos, Calendar, Slack, Notion, Obsidian, browser history, generic IMAP, Google Takeout, local filesystem). Each connector emits normalized payloads into a Valkey-backed work queue.
2. **Processing pipeline** orchestrated by `apps.workers.orchestrator`. Payloads are deduplicated (SHA256/SimHash/pHash), stored in MinIO, graphified in Neo4j, and embedded with LanceDB for vector retrieval. OCR (pdf2image + Tesseract) and Whisper transcription supply text for non-text media.
3. **Retrieval layer** implemented in `apps.api.services.retrieval`. Queries run through the planner (intent + entity extraction), dense search (LanceDB), BM25 full-text (Neo4j full-text indexes), and graph traversals. Results are reranked (BGE-reranker-v2-m3), diversified with MMR (λ=0.7), cached in Valkey, and passed to Qwen-2.5 via Ollama for grounded answer generation.
4. **Experience layer** consisting of FastAPI routes (`/ask`, `/entities`, `/ingest`, `/health`) and a Gradio UI. All requests require JWT auth and are rate-limited (SlowAPI). Metrics are exported to Prometheus and logs are structured JSON.

```
   ┌────────────────────────────────────────────────────────┐
   │                    Experience Layer                    │
   │  Gradio UI  ──>  FastAPI  ──>  Retrieval Orchestrator  │
   └────────────────────────────────────────────────────────┘
                      ▲                      │
                      │                      ▼
   ┌────────────────────────────────────────────────────────┐
   │                 Processing & Storage                   │
   │  Valkey queue  →  DocumentProcessor  →  Neo4j graph    │
   │                                  ╲→  LanceDB vectors   │
   │                                  ╲→  MinIO objects     │
   └────────────────────────────────────────────────────────┘
                      ▲
                      │
   ┌────────────────────────────────────────────────────────┐
   │                       Connectors                       │
   │  Gmail · Drive · Photos · Calendar · Slack · Notion · … │
   └────────────────────────────────────────────────────────┘
```

### Key Services
| Service | Responsibility |
|---------|----------------|
| Neo4j 5.x | Primary knowledge graph (documents, entities, relationships, temporal validity) |
| LanceDB | High-performance vector store for text/image embeddings |
| Valkey | Cache, work queue, connector state, dedupe index |
| MinIO | Binary/object storage for original artifacts |
| Ollama + Qwen 2.5 | Local LLM used for answer synthesis with citation constraints |

### Data Flow
1. **Ingestion**: connectors fetch deltas (historyId, syncToken, change feeds) and enqueue normalized payloads.
2. **Processing**: `DocumentProcessor` downloads references, runs OCR/transcription, computes embeddings, writes to MinIO/Neo4j/LanceDB, and establishes entity relationships.
3. **Query**: `QueryPlanner` classifies intent + entities, `RetrievalOrchestrator` executes hybrid retrieval, caches responses, and `LLMService` generates citation-rich answers.
4. **Operations**: nightly backup consolidates Neo4j JSON dump, LanceDB snapshot, MinIO object export, and Valkey snapshot; health checks expose subsystem status at `/health` and metrics at `/metrics`.

### Memory Management
- Shared `ModelManager` ensures exclusive loading of heavy models (BGE-M3, SigLIP, Whisper, reranker).
- `MemoryGuard` monitors macOS virtual memory and MPS usage, applying backpressure and adaptive batch sizing when free memory < 1.5 GB.

### Security & Privacy
- JWT auth wraps all API calls; Gradio UI requires manual token entry.
- No outbound telemetry—connectors only talk to upstream APIs explicitly authorized by the user.
- Structured logging with correlation IDs; PII never emitted.
