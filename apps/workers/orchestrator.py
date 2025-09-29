from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from apps.workers.processors.document_processor import DocumentProcessor
from connectors import (
    BrowserHistoryConnector,
    DriveConnector,
    GenericIMAPConnector,
    GmailConnector,
    GoogleCalendarConnector,
    GooglePhotosConnector,
    GoogleTakeoutConnector,
    LocalFilesystemConnector,
    NotionConnector,
    ObsidianConnector,
    SlackConnector,
)
from connectors.base import BaseConnector
from core.cache import valkey_client
from core.config import settings
from core.logging import configure_logging

logger = logging.getLogger("pkb.worker")
configure_logging(settings.log_level)

QUEUE_NAME = "ingest:documents"


class WorkerOrchestrator:
    def __init__(self) -> None:
        self._processor = DocumentProcessor()
        self._scheduler = AsyncIOScheduler(timezone=settings.cron_timezone)
        self._connectors: list[BaseConnector] = []
        self._init_connectors()

    def _init_connectors(self) -> None:
        try:
            self._connectors.append(GmailConnector())
        except Exception as exc:
            logger.warning("Skipping Gmail connector", exc_info=exc)
        try:
            self._connectors.append(DriveConnector())
        except Exception as exc:
            logger.warning("Skipping Drive connector", exc_info=exc)
        try:
            self._connectors.append(GooglePhotosConnector())
        except Exception as exc:
            logger.warning("Skipping Photos connector", exc_info=exc)
        try:
            self._connectors.append(GoogleCalendarConnector())
        except Exception as exc:
            logger.warning("Skipping Calendar connector", exc_info=exc)
        try:
            self._connectors.append(SlackConnector())
        except Exception as exc:
            logger.warning("Skipping Slack connector", exc_info=exc)
        try:
            self._connectors.append(NotionConnector())
        except Exception as exc:
            logger.warning("Skipping Notion connector", exc_info=exc)
        try:
            self._connectors.append(ObsidianConnector())
        except Exception as exc:
            logger.warning("Skipping Obsidian connector", exc_info=exc)
        try:
            self._connectors.append(BrowserHistoryConnector())
        except Exception as exc:
            logger.warning("Skipping Browser connector", exc_info=exc)
        try:
            self._connectors.append(GenericIMAPConnector())
        except Exception as exc:
            logger.warning("Skipping generic IMAP connector", exc_info=exc)
        try:
            self._connectors.append(GoogleTakeoutConnector())
        except Exception as exc:
            logger.warning("Skipping Google Takeout connector", exc_info=exc)
        try:
            self._connectors.append(LocalFilesystemConnector())
        except Exception as exc:
            logger.warning("Skipping Local filesystem connector", exc_info=exc)

    async def start(self) -> None:
        self._schedule_connectors()
        self._schedule_backups()
        self._scheduler.start()
        for connector in self._connectors:
            asyncio.create_task(self._run_connector(connector))
        await self._run_forever()

    def _schedule_connectors(self) -> None:
        for connector in self._connectors:
            interval_minutes = 10
            if isinstance(connector, GmailConnector):
                interval_minutes = 5
            if isinstance(connector, GooglePhotosConnector):
                interval_minutes = 30
            if isinstance(connector, GoogleTakeoutConnector):
                interval_minutes = 1440
            self._scheduler.add_job(
                self._run_connector,
                "interval",
                minutes=interval_minutes,
                args=[connector],
                max_instances=1,
                id=f"connector:{connector.name}",
                replace_existing=True,
            )

    def _schedule_backups(self) -> None:
        self._scheduler.add_job(
            self._nightly_backup,
            CronTrigger(hour=3, minute=0),
            id="nightly_backup",
            replace_existing=True,
        )

    async def _nightly_backup(self) -> None:
        logger.info("Running nightly backup job")
        process = await asyncio.create_subprocess_exec("bash", "scripts/backup.sh")
        await process.wait()

    async def _run_connector(self, connector: BaseConnector) -> None:
        logger.info("Running connector", extra={"connector": connector.name})
        async for payload in connector.sync():
            await valkey_client.enqueue(QUEUE_NAME, payload)

    async def _queue_worker(self) -> None:
        while True:
            job = await valkey_client.dequeue(QUEUE_NAME, timeout=5)
            if not job:
                await asyncio.sleep(1)
                continue
            try:
                await self._processor.process(job)
            except Exception:
                logger.exception("Failed to process ingestion job", extra={"doc_id": job.get("document", {}).get("doc_id")})

    async def _run_forever(self) -> None:
        consumer = asyncio.create_task(self._queue_worker())
        try:
            await consumer
        except asyncio.CancelledError:
            consumer.cancel()
            raise


def main() -> None:
    orchestrator = WorkerOrchestrator()
    asyncio.run(orchestrator.start())


if __name__ == "__main__":
    main()
