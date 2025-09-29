from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

from core.cache import valkey_client

QUEUE_NAME = "ingest:documents"


def create_sample_files() -> Dict[str, Path]:
    seed_dir = Path("data/seed")
    seed_dir.mkdir(parents=True, exist_ok=True)
    alpha_path = seed_dir / "project_alpha.md"
    alpha_path.write_text(
        """# Project Alpha\n\nKey objectives:\n- Build knowledge graph\n- Integrate Gmail connector\n\nNext steps:\n1. Finish ingestion pipeline\n2. Schedule stakeholder review\n""",
        encoding="utf-8",
    )
    notes_path = seed_dir / "meeting_notes.txt"
    notes_path.write_text(
        """Meeting Notes (2024-09-15)\nAttendees: Alice, Bob\nAction Items:\n- Prepare onboarding doc\n- Finalize connector scopes\n""",
        encoding="utf-8",
    )
    return {"alpha": alpha_path, "notes": notes_path}


async def enqueue_document(path: Path, doc_id: str, title: str, project: str) -> None:
    created = datetime.now(timezone.utc).isoformat()
    payload = {
        "document": {
            "doc_id": doc_id,
            "version": created,
            "title": title,
            "source": "seed",
            "created_at": created,
            "valid_from": created,
            "valid_to": None,
            "system_from": created,
            "system_to": None,
        },
        "files": [
            {
                "uri": str(path),
                "mime_type": "text/markdown" if path.suffix == ".md" else "text/plain",
                "size_bytes": path.stat().st_size,
                "created_at": created,
            }
        ],
        "entities": {
            "projects": [
                {
                    "name": project,
                    "tags": ["seed", "demo"],
                }
            ],
            "people": ["alice@example.com", "bob@example.com"],
        },
    }
    await valkey_client.enqueue(QUEUE_NAME, payload)


async def main() -> None:
    files = create_sample_files()
    await enqueue_document(files["alpha"], "seed:project_alpha", "Project Alpha Overview", "Project Alpha")
    await enqueue_document(files["notes"], "seed:meeting_notes", "Project Alpha – Kickoff Notes", "Project Alpha")
    print("Seed data enqueued")


if __name__ == "__main__":
    asyncio.run(main())
