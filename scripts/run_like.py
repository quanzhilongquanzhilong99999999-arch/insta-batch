"""Batch like — each enabled account likes a shared list of media IDs."""
from __future__ import annotations

import asyncio

from _common import bootstrap

from insta_batch.tasks.like_comment import LikePayload, LikeTask


# Replace with real media_id strings (e.g. "3400123456789012345_17841400000000000").
MEDIA_IDS = ["MEDIA_ID_1", "MEDIA_ID_2"]


async def main() -> None:
    cfg, pool, factory = bootstrap()
    task = LikeTask(cfg, factory)
    payload = LikePayload(media_ids=MEDIA_IDS, unlike=False)
    await task.execute(pool.active(), payload_per_account=payload)


if __name__ == "__main__":
    asyncio.run(main())
