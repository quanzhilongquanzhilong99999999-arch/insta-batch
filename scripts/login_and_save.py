"""First-time login across all enabled accounts — saves sessions for later reuse.

Run once after editing config/accounts.yaml:

    python scripts/login_and_save.py

Subsequent task runs will load the session file and skip re-authentication
unless it has expired.
"""
from __future__ import annotations

import asyncio

from _common import bootstrap

from insta_batch.core.logger import get_logger
from insta_batch.tasks.base import BaseTask, TaskResult
from insta_wizard import MobileClient
from insta_batch.core.account_pool import Account


log = get_logger(__name__)


class _LoginOnlyTask(BaseTask):
    name = "login_only"

    async def run_for_account(
        self, client: MobileClient, account: Account, payload
    ) -> TaskResult:
        me = await client.account.get_current_user()
        return TaskResult(
            account=account.username, ok=True, detail=f"logged in as @{me.username}"
        )


async def main() -> None:
    cfg, pool, factory = bootstrap()
    task = _LoginOnlyTask(cfg, factory)
    await task.execute(pool.active())


if __name__ == "__main__":
    asyncio.run(main())
