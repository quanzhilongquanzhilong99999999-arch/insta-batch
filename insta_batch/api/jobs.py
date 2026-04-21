"""JobManager: per-worker coordinator between the JobStore and asyncio tasks.

- Store writes are centralized here so subclasses of BaseTask don't need to
  know anything about persistence.
- asyncio.Task handles live only on the worker that submitted the job —
  used for local cancellation. Cross-worker cancel signals a `cancel_requested`
  flag in the record; the owning worker picks it up and cancels.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone
from typing import Awaitable, Callable

from insta_batch.api.jobs_store import (
    JobRecord,
    JobStore,
    MemoryJobStore,
    RedisJobStore,
    build_store,
    _now_iso,
)
from insta_batch.api.schemas import JobView
from insta_batch.core.logger import get_logger
from insta_batch.tasks.base import TaskStats


log = get_logger(__name__)


class JobManager:
    def __init__(self, store: JobStore | None = None):
        self._store: JobStore = store or build_store(os.getenv("REDIS_URL"))
        self._local_tasks: dict[str, asyncio.Task] = {}
        log.info("JobManager using %s", type(self._store).__name__)

    async def submit(
        self,
        task_type: str,
        total_accounts: int,
        runner: Callable[[], Awaitable[TaskStats]],
    ) -> str:
        job_id = uuid.uuid4().hex
        record = JobRecord.new(job_id, task_type, total_accounts)
        await self._store.save(record)

        async def _wrap() -> None:
            record.status = "running"
            record.started_at = _now_iso()
            await self._store.save(record)
            try:
                stats = await runner()
                record.ok = stats.ok
                record.failed = stats.failed
                record.skipped = stats.skipped
                record.results = [
                    {"account": r.account, "ok": r.ok, "detail": r.detail}
                    for r in stats.results
                ]
                record.status = "completed"
            except asyncio.CancelledError:
                record.status = "canceled"
                raise
            except Exception as e:
                record.status = "failed"
                record.error = f"{type(e).__name__}: {e}"
                log.exception("Job %s failed: %s", job_id, e)
            finally:
                record.finished_at = _now_iso()
                await self._store.save(record)
                self._local_tasks.pop(job_id, None)

        self._local_tasks[job_id] = asyncio.create_task(_wrap(), name=f"job:{job_id}")
        log.info("Submitted job %s (%s) over %d accounts", job_id, task_type, total_accounts)
        return job_id

    async def get_view(self, job_id: str) -> JobView | None:
        rec = await self._store.get(job_id)
        return rec.view() if rec else None

    async def list_views(self, limit: int = 50) -> list[JobView]:
        return [r.view() for r in await self._store.list(limit=limit)]

    async def cancel(self, job_id: str) -> bool:
        """Cancel if this worker owns the asyncio.Task. Cross-worker cancel
        is not yet supported — returns False so the caller can surface that."""
        task = self._local_tasks.get(job_id)
        if task is None or task.done():
            return False
        task.cancel()
        return True

    async def active_count(self) -> int:
        return await self._store.active_count()


_manager: JobManager | None = None


def get_job_manager() -> JobManager:
    global _manager
    if _manager is None:
        _manager = JobManager()
    return _manager


def reset_job_manager() -> None:
    """For tests."""
    global _manager
    _manager = None
