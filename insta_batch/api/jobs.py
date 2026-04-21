"""In-memory Job manager: wraps a BaseTask.execute() coroutine in asyncio.Task,
tracks status/progress, allows cancellation, exposes a snapshot view.

Single-process. Restart loses state — fine for MVP; replace with SQLite/Redis
when you need persistence.
"""
from __future__ import annotations

import asyncio
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Awaitable, Callable

from insta_batch.api.schemas import (
    JobProgress,
    JobResultEntry,
    JobStatusLit,
    JobView,
)
from insta_batch.core.logger import get_logger
from insta_batch.tasks.base import TaskStats


log = get_logger(__name__)


@dataclass
class Job:
    job_id: str
    task_type: str
    status: JobStatusLit = "pending"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    finished_at: datetime | None = None
    stats: TaskStats | None = None
    error: str | None = None
    asyncio_task: asyncio.Task | None = None
    total_accounts: int = 0

    def snapshot(self) -> JobView:
        progress = JobProgress(total=self.total_accounts)
        results: list[JobResultEntry] = []
        if self.stats is not None:
            progress.ok = self.stats.ok
            progress.failed = self.stats.failed
            progress.skipped = self.stats.skipped
            results = [
                JobResultEntry(account=r.account, ok=r.ok, detail=r.detail)
                for r in self.stats.results
            ]
        return JobView(
            job_id=self.job_id,
            task_type=self.task_type,
            status=self.status,
            created_at=self.created_at,
            started_at=self.started_at,
            finished_at=self.finished_at,
            progress=progress,
            results=results,
            error=self.error,
        )


class JobManager:
    """Bounded LRU — keeps the last `max_jobs` jobs in memory."""

    def __init__(self, max_jobs: int = 500):
        self._jobs: OrderedDict[str, Job] = OrderedDict()
        self._max = max_jobs

    def _trim(self) -> None:
        while len(self._jobs) > self._max:
            jid, job = self._jobs.popitem(last=False)
            if job.status in ("pending", "running"):
                # Don't evict live jobs — put back at the front.
                self._jobs[jid] = job
                self._jobs.move_to_end(jid, last=False)
                break

    def submit(
        self,
        task_type: str,
        total_accounts: int,
        runner: Callable[["Job"], Awaitable[TaskStats]],
    ) -> Job:
        job = Job(job_id=uuid.uuid4().hex, task_type=task_type, total_accounts=total_accounts)
        self._jobs[job.job_id] = job
        self._trim()

        async def _wrap() -> None:
            job.status = "running"
            job.started_at = datetime.now(timezone.utc)
            try:
                job.stats = await runner(job)
                job.status = "completed"
            except asyncio.CancelledError:
                job.status = "canceled"
                raise
            except Exception as e:
                job.status = "failed"
                job.error = f"{type(e).__name__}: {e}"
                log.exception("Job %s failed: %s", job.job_id, e)
            finally:
                job.finished_at = datetime.now(timezone.utc)

        job.asyncio_task = asyncio.create_task(_wrap(), name=f"job:{job.job_id}")
        log.info("Submitted job %s (%s) over %d accounts", job.job_id, task_type, total_accounts)
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def list(self, limit: int = 50) -> list[Job]:
        items = list(self._jobs.values())
        items.sort(key=lambda j: j.created_at, reverse=True)
        return items[:limit]

    def cancel(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job is None or job.asyncio_task is None:
            return False
        if job.status not in ("pending", "running"):
            return False
        job.asyncio_task.cancel()
        return True

    def active_count(self) -> int:
        return sum(1 for j in self._jobs.values() if j.status in ("pending", "running"))


_manager: JobManager | None = None


def get_job_manager() -> JobManager:
    global _manager
    if _manager is None:
        _manager = JobManager()
    return _manager
