"""Batch follow — each enabled account follows a shared list of target usernames.

Edit TARGETS below (or load from a file) and run:

    python scripts/run_follow.py
"""
from __future__ import annotations

import asyncio

from _common import bootstrap

from insta_batch.tasks.follow import FollowPayload, FollowTask


# Example: every account follows these usernames. Swap for per-account mapping
# by passing a dict {username: FollowPayload(...)} to task.execute().
TARGETS = FollowPayload(usernames=["instagram", "natgeo"])


async def main() -> None:
    cfg, pool, factory = bootstrap()
    task = FollowTask(cfg, factory)
    await task.execute(pool.active(), payload_per_account=TARGETS)


if __name__ == "__main__":
    asyncio.run(main())
