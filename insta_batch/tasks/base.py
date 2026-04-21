"""BaseTask — concurrency, retry, session restore, statistics.

Subclasses implement `run_for_account(client, account, **payload)` and call
`execute(accounts, payload_per_account)` on the instance. BaseTask takes care of:

- bounded concurrency (Semaphore)
- session restore via Account.load_state(), save on exit
- per-account try/except so one bad account doesn't kill the batch
- human-like jitter between actions (the task body can also call jittered_sleep)
- structured stats (ok / failed / skipped) returned to caller
"""
from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from insta_wizard import MobileClient

from insta_batch.core.account_pool import Account
from insta_batch.core.client_factory import ClientFactory
from insta_batch.core.config import Config
from insta_batch.core.logger import get_logger


log = get_logger(__name__)


@dataclass
class TaskResult:
    account: str
    ok: bool
    detail: str = ""
    data: Any = None


@dataclass
class TaskStats:
    ok: int = 0
    failed: int = 0
    skipped: int = 0
    results: list[TaskResult] = field(default_factory=list)

    def add(self, r: TaskResult) -> None:
        self.results.append(r)
        if r.ok:
            self.ok += 1
        else:
            self.failed += 1

    def summary(self) -> str:
        return f"ok={self.ok} failed={self.failed} skipped={self.skipped}"


class BaseTask(ABC):
    name: str = "base"

    def __init__(self, config: Config, factory: ClientFactory):
        self._config = config
        self._factory = factory
        self._sem = asyncio.Semaphore(config.concurrency.max_parallel_accounts)

    @abstractmethod
    async def run_for_account(
        self, client: MobileClient, account: Account, payload: Any
    ) -> TaskResult:
        """Subclass hook. Must return TaskResult. Raises are caught upstream."""

    async def _run_one(self, account: Account, payload: Any) -> TaskResult:
        async with self._sem:
            client = self._factory.build(account)
            try:
                async with client:
                    state = account.load_state()
                    if state:
                        client.load_state(state)
                        try:
                            await client.account.get_current_user()
                        except Exception as e:
                            log.info(
                                "Session expired for %s (%s) — re-login",
                                account.username,
                                type(e).__name__,
                            )
                            account.drop_state()
                            await client.login(account.username, account.password)
                    else:
                        await client.login(account.username, account.password)

                    account.save_state(client.dump_state())

                    return await self.run_for_account(client, account, payload)
            except Exception as e:
                log.exception("[%s] task %s failed: %s", account.username, self.name, e)
                return TaskResult(
                    account=account.username, ok=False, detail=f"{type(e).__name__}: {e}"
                )

    async def execute(
        self,
        accounts: list[Account],
        payload_per_account: dict[str, Any] | Any | None = None,
    ) -> TaskStats:
        """Run the task across accounts.

        - payload_per_account=None → each account gets None
        - payload_per_account=dict → keyed by username (missing keys → skipped)
        - payload_per_account=<any> → shared across all accounts
        """
        stats = TaskStats()
        tasks: list[asyncio.Task] = []

        for acc in accounts:
            if isinstance(payload_per_account, dict):
                if acc.username not in payload_per_account:
                    stats.skipped += 1
                    continue
                payload = payload_per_account[acc.username]
            else:
                payload = payload_per_account

            tasks.append(asyncio.create_task(self._run_one(acc, payload)))

        for coro in asyncio.as_completed(tasks):
            r = await coro
            stats.add(r)
            tag = "OK " if r.ok else "ERR"
            log.info("[%s] %s %s: %s", self.name, tag, r.account, r.detail or "done")

        log.info("[%s] DONE — %s", self.name, stats.summary())
        return stats
