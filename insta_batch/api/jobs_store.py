"""Job persistence backends.

Two implementations of the same small contract:

    save(job), get(job_id), list(limit), active_count()

- `MemoryJobStore` — process-local dict. Fine for single-worker dev.
- `RedisJobStore` — shared across workers / processes. State survives
  restart and different uvicorn workers see the same jobs.

Job is a plain dataclass serialized as JSON. The `asyncio.Task` handle
is NOT stored here — it lives only in the JobManager of the worker that
submitted the job (used for local cancellation).
"""
from __future__ import annotations

import json
from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Protocol

from insta_batch.api.schemas import (
    JobProgress,
    JobResultEntry,
    JobStatusLit,
    JobView,
)


# ---- job record ----------------------------------------------------------

@dataclass
class JobRecord:
    job_id: str
    task_type: str
    status: JobStatusLit
    created_at: str                       # ISO-8601 UTC
    started_at: str | None = None
    finished_at: str | None = None
    total_accounts: int = 0
    ok: int = 0
    failed: int = 0
    skipped: int = 0
    results: list[dict] = field(default_factory=list)   # [{account, ok, detail}]
    error: str | None = None

    @classmethod
    def new(cls, job_id: str, task_type: str, total_accounts: int) -> "JobRecord":
        return cls(
            job_id=job_id,
            task_type=task_type,
            status="pending",
            created_at=_now_iso(),
            total_accounts=total_accounts,
        )

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, s: str) -> "JobRecord":
        return cls(**json.loads(s))

    def view(self) -> JobView:
        return JobView(
            job_id=self.job_id,
            task_type=self.task_type,
            status=self.status,
            created_at=datetime.fromisoformat(self.created_at),
            started_at=datetime.fromisoformat(self.started_at) if self.started_at else None,
            finished_at=datetime.fromisoformat(self.finished_at) if self.finished_at else None,
            progress=JobProgress(
                total=self.total_accounts, ok=self.ok, failed=self.failed, skipped=self.skipped
            ),
            results=[JobResultEntry(**r) for r in self.results],
            error=self.error,
        )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---- contract ------------------------------------------------------------

class JobStore(Protocol):
    async def save(self, job: JobRecord) -> None: ...
    async def get(self, job_id: str) -> JobRecord | None: ...
    async def list(self, limit: int = 50) -> list[JobRecord]: ...
    async def active_count(self) -> int: ...


# ---- in-memory -----------------------------------------------------------

class MemoryJobStore:
    def __init__(self, max_jobs: int = 500):
        self._jobs: OrderedDict[str, JobRecord] = OrderedDict()
        self._max = max_jobs

    async def save(self, job: JobRecord) -> None:
        self._jobs[job.job_id] = job
        self._jobs.move_to_end(job.job_id)
        while len(self._jobs) > self._max:
            oldest_id, oldest = next(iter(self._jobs.items()))
            if oldest.status in ("pending", "running"):
                break
            self._jobs.pop(oldest_id)

    async def get(self, job_id: str) -> JobRecord | None:
        return self._jobs.get(job_id)

    async def list(self, limit: int = 50) -> list[JobRecord]:
        items = list(self._jobs.values())
        items.sort(key=lambda r: r.created_at, reverse=True)
        return items[:limit]

    async def active_count(self) -> int:
        return sum(1 for j in self._jobs.values() if j.status in ("pending", "running"))


# ---- redis ---------------------------------------------------------------

class RedisJobStore:
    """Shared store backed by Redis.

    Keys (all namespaced under `insta_batch:`):
      - `insta_batch:job:<id>` → JSON, TTL = ttl_seconds
      - `insta_batch:jobs:index` → sorted set, score=unix-ts, member=job_id
    """

    def __init__(self, url: str, ttl_seconds: int = 7 * 24 * 3600):
        from redis.asyncio import Redis

        self._redis: Redis = Redis.from_url(url, decode_responses=True)
        self._ttl = ttl_seconds
        self._prefix = "insta_batch"

    def _k(self, suffix: str) -> str:
        return f"{self._prefix}:{suffix}"

    async def save(self, job: JobRecord) -> None:
        key = self._k(f"job:{job.job_id}")
        score = datetime.fromisoformat(job.created_at).timestamp()
        pipe = self._redis.pipeline(transaction=False)
        pipe.set(key, job.to_json(), ex=self._ttl)
        pipe.zadd(self._k("jobs:index"), {job.job_id: score})
        await pipe.execute()

    async def get(self, job_id: str) -> JobRecord | None:
        s = await self._redis.get(self._k(f"job:{job_id}"))
        if s is None:
            return None
        return JobRecord.from_json(s)

    async def list(self, limit: int = 50) -> list[JobRecord]:
        ids = await self._redis.zrevrange(self._k("jobs:index"), 0, limit - 1)
        if not ids:
            return []
        keys = [self._k(f"job:{jid}") for jid in ids]
        values = await self._redis.mget(keys)
        out: list[JobRecord] = []
        for jid, v in zip(ids, values):
            if v is None:
                # expired — evict from index
                await self._redis.zrem(self._k("jobs:index"), jid)
                continue
            out.append(JobRecord.from_json(v))
        return out

    async def active_count(self) -> int:
        # Scan the index instead of a separate active-set to avoid drift;
        # index is bounded by max_jobs and expiry.
        ids = await self._redis.zrevrange(self._k("jobs:index"), 0, 499)
        if not ids:
            return 0
        keys = [self._k(f"job:{jid}") for jid in ids]
        values = await self._redis.mget(keys)
        count = 0
        for v in values:
            if v is None:
                continue
            try:
                rec = JobRecord.from_json(v)
                if rec.status in ("pending", "running"):
                    count += 1
            except Exception:
                continue
        return count


# ---- factory -------------------------------------------------------------

def build_store(redis_url: str | None) -> JobStore:
    if redis_url:
        return RedisJobStore(redis_url)
    return MemoryJobStore()
