# Troubleshooting

## Containers fail to start
- **Port conflicts**: ensure 8000, 9000, 9001, 9090, 6379, 7474, 7687 are free. Adjust `docker-compose.yml` if necessary.
- **Neo4j authentication errors**: verify `NEO4J_PASSWORD` matches value in `.env` and the `NEO4J_AUTH` variable in compose.

## `/health` shows degraded components
| Component | Resolution |
|-----------|------------|
| `neo4j` fail | Check container logs `docker compose logs neo4j`, ensure memory settings suffice. Run `cypher-shell -u neo4j -p $NEO4J_PASSWORD "RETURN 1"`. |
| `valkey` fail | Ensure container running and accessible (`redis-cli -h localhost -p 6379 ping`). |
| `minio` fail | Confirm credentials, bucket existence (`mc alias set local http://localhost:9000 <access> <secret>`). |
| `lancedb` fail | Verify `/data/lancedb` volume mounted. |
| `memory` warn | Increase free memory or lower workload; adjust `SETTINGS__BACKPRESSURE_FREE_MEM_BYTES`.

## Connectors not ingesting
- Check worker logs: `make logs`. Look for exceptions labeled `connector.<name>`.
- Confirm OAuth tokens/scopes; re-create refresh token if `invalid_grant` occurs.
- For Gmail/IMAP, verify IMAP enabled and app password used when necessary.
- Browser connector requires browser closed (Chrome locks History DB). Close Chrome/Firefox before ingestion window.

## Ollama / LLM issues
- Ensure Ollama service running on host (`ollama serve` or background service).
- Verify `curl http://localhost:11434/api/tags` lists `qwen2.5:7b-instruct-q4_K_M`.
- Large prompts may exceed context; adjust `num_ctx` in `apps/api/services/llm.py` if required.

## OCR/Whisper performance problems
- OCR relies on `poppler-utils` and `tesseract`; installed via Dockerfile. If errors persist, reinstall image (`docker compose build worker`).
- Whisper transcription is CPU-based; heavy workloads may need schedule adjustments or audio batching.

## Backup/Restore failures
- Ensure `./backups` directory writable on host.
- `scripts/backup.py` depends on active services; run while containers are up.
- Restore clears Neo4j/Valkey data; confirm you want to overwrite before running `make restore`.

## Gradio UI authentication
- Generate JWT via FastAPI auth endpoint or integrate with your identity provider. Paste token into the UI token box before chatting.

## Testing
- Run the full suite with `make test`.
- If connectors tests hang, ensure no real network calls occur; they rely on stubbed services and should complete in seconds.

## Getting help
- Enable debug logging by setting `SETTINGS__LOG_LEVEL=DEBUG` in `.env` and restarting.
- Inspect structured logs under `./logs` for correlation IDs matching API responses.
