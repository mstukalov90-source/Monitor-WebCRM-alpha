"""Daily restore of delayed CRM tasks at 00:01 Europe/Moscow
and analise/pre_analise reset at 07:00 Europe/Moscow.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.config import crm_task_store_config
from app.crm.store import MOSCOW_TZ, restore_due_delayed_tasks
from app.crm.tasks_area import (
    ANALISE_RESET_HOUR,
    clear_stale_analise_locks,
    clear_stale_pre_analise_locks,
)
from app.db import get_connection

logger = logging.getLogger(__name__)


def _seconds_until_next_moscow_0001() -> float:
    now = datetime.now(MOSCOW_TZ)
    target = now.replace(hour=0, minute=1, second=0, microsecond=0)
    if now >= target:
        target = target + timedelta(days=1)
    return max(1.0, (target - now).total_seconds())


def _seconds_until_next_moscow_analise_reset() -> float:
    now = datetime.now(MOSCOW_TZ)
    target = now.replace(hour=ANALISE_RESET_HOUR, minute=0, second=0, microsecond=0)
    if now >= target:
        target = target + timedelta(days=1)
    return max(1.0, (target - now).total_seconds())


def run_restore_due_delayed_tasks() -> int:
    store_cfg = crm_task_store_config()
    with get_connection() as conn:
        keys = restore_due_delayed_tasks(conn, store_cfg)
    return len(keys)


def run_clear_stale_analise_locks() -> int:
    with get_connection() as conn:
        cleared = clear_stale_analise_locks(conn)
        cleared += clear_stale_pre_analise_locks(conn)
    return cleared


async def delayed_tasks_restore_loop(stop: asyncio.Event) -> None:
    while not stop.is_set():
        delay = _seconds_until_next_moscow_0001()
        logger.info(
            "Next delayed-tasks restore in %.0f s (00:01 %s)",
            delay,
            MOSCOW_TZ.key if isinstance(MOSCOW_TZ, ZoneInfo) else "Europe/Moscow",
        )
        try:
            await asyncio.wait_for(stop.wait(), timeout=delay)
            break
        except asyncio.TimeoutError:
            pass
        try:
            restored = await asyncio.to_thread(run_restore_due_delayed_tasks)
            logger.info("Delayed-tasks restore finished: %s task(s)", restored)
        except Exception:
            logger.exception("Delayed-tasks restore failed")


async def analise_reset_loop(stop: asyncio.Event) -> None:
    while not stop.is_set():
        delay = _seconds_until_next_moscow_analise_reset()
        logger.info(
            "Next analise/pre_analise reset in %.0f s (%02d:00 %s)",
            delay,
            ANALISE_RESET_HOUR,
            MOSCOW_TZ.key if isinstance(MOSCOW_TZ, ZoneInfo) else "Europe/Moscow",
        )
        try:
            await asyncio.wait_for(stop.wait(), timeout=delay)
            break
        except asyncio.TimeoutError:
            pass
        try:
            cleared = await asyncio.to_thread(run_clear_stale_analise_locks)
            logger.info("Analise/pre_analise reset finished: %s order(s)", cleared)
        except Exception:
            logger.exception("Analise/pre_analise reset failed")
