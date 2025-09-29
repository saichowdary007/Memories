from __future__ import annotations

from typing import Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from core.config import settings


def configure_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=settings.cron_timezone)
    return scheduler


def add_nightly_job(scheduler: AsyncIOScheduler, func: Callable[[], None]) -> None:
    scheduler.add_job(func, CronTrigger(hour=3, minute=0), id="nightly_backup", replace_existing=True)
