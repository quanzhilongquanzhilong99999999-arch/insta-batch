"""Account monitor — verify liveness and snapshot target profiles to data/monitor.jsonl."""
from __future__ import annotations

import asyncio

from _common import bootstrap

from insta_batch.tasks.monitor import MonitorPayload, MonitorTask


# Profiles to snapshot (each monitoring account scrapes this same list).
TARGETS = ["instagram", "natgeo"]


async def main() -> None:
    cfg, pool, factory = bootstrap()
    task = MonitorTask(cfg, factory)
    payload = MonitorPayload(usernames=TARGETS, output_file="monitor.jsonl")
    await task.execute(pool.active(), payload_per_account=payload)


if __name__ == "__main__":
    asyncio.run(main())
