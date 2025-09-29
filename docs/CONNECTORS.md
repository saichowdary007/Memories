# Connector Configuration

Each connector runs inside the worker container, maintains incremental state in Valkey (`connector:<name>:state`), and yields normalized ingestion payloads. Populate the corresponding environment variables in `.env` before enabling a connector.

## Google APIs (Gmail, Drive, Photos, Calendar)
- **OAuth scopes**
  - Gmail: `https://www.googleapis.com/auth/gmail.readonly`, `https://www.googleapis.com/auth/gmail.modify`
  - Drive: `https://www.googleapis.com/auth/drive.readonly`, `https://www.googleapis.com/auth/drive.metadata.readonly`
  - Photos: `https://www.googleapis.com/auth/photoslibrary.readonly`, `https://www.googleapis.com/auth/photoslibrary.sharing`
  - Calendar: `https://www.googleapis.com/auth/calendar.readonly`
- **Credentials**: set `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN`, `GOOGLE_PROJECT_ID`, and `GOOGLE_REDIRECT_URI`.
- **State**
  - Gmail tracks the latest `historyId` (delta sync via `users.history.list`). Attachments are fetched via `users.messages.attachments.get` and cached on disk before upload to MinIO.
  - Drive relies on the v3 Changes API with `startPageToken`; native Google Docs are exported to PDF/CSV before ingestion.
  - Photos stores the newest `mediaMetadata.creationTime` and only imports newer media; EXIF GPS metadata is captured when available.
  - Calendar persists `nextSyncToken` from `events.list` to fetch incremental updates.

## Slack
- Required scopes: `conversations.history`, `files:read` (via the bot token).
- Environment: `SLACK_BOT_TOKEN` (and optionally `SLACK_APP_TOKEN` for Socket Mode, though polling is used).
- Connector caches the latest message timestamp per channel to avoid reprocessing.

## Notion
- Create an internal integration and share the relevant pages/databases.
- Environment: `NOTION_INTERNAL_INTEGRATION_TOKEN`.
- Incremental updates rely on `last_edited_time`; rich text blocks are flattened into document blocks for embedding.

## Obsidian
- Configure `OBSIDIAN_VAULT_PATH` to point at the local vault.
- Connector hashes file paths and modified timestamps to ingest only changed markdown notes.

## Browser History
- Chrome history path (`CHROME_HISTORY_PATH`) and Firefox profile directory (`FIREFOX_PROFILE_PATH`) are copied to a temporary SQLite database, parsed, and ingested as `web_history` blocks.
- The connector tracks the latest visit timestamp per browser.

## Generic IMAP
- Environment: `GENERIC_IMAP_HOST`, `GENERIC_IMAP_PORT`, `GENERIC_IMAP_USERNAME`, `GENERIC_IMAP_PASSWORD`.
- Incremental sync uses the highest processed UID; messages and attachments mirror the Gmail ingestion flow.

## Google Takeout
- Point `GOOGLE_TAKEOUT_PATH` to an extracted Takeout archive folder.
- The connector hashes JSON payloads (`hashes` map) to detect updates and ingests structured JSON snapshots for long-term reference.

## Local Filesystem
- Provide comma-separated directories via `LOCAL_WATCH_PATHS` (default `~/Documents`).
- The connector hashes files (SHA256) and ingests text content for supported MIME types; changes are detected via modification times.

## Connector Scheduling
- Default intervals (minutes): Gmail 5, Drive 10, Calendar 10, Photos 30, Slack 5, Notion 10, Obsidian 10, Browser 30, IMAP 10, Takeout 1440 (daily), Local filesystem 15.
- Schedules can be adjusted in `apps/workers/orchestrator.py`.

## Error Handling
- Connectors retry transient failures with exponential backoff (via `httpx` standard retry behaviour and explicit exception handling).
- Each connector persists state in Valkey, so restarts safely resume incremental syncs.

Refer to `tests/integration/test_connectors.py` for end-to-end stubs illustrating expected payload structures.
