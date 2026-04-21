"""Batch publish — each enabled account posts the same photo.

For per-account content, pass a dict {username: PhotoPayload(...)} instead.
"""
from __future__ import annotations

import asyncio

from _common import bootstrap

from insta_batch.tasks.publish import PhotoPayload, PublishPhotoTask


PAYLOAD = PhotoPayload(
    image_path="data/sample.jpg",
    caption="Hello from insta-batch",
)


async def main() -> None:
    cfg, pool, factory = bootstrap()
    task = PublishPhotoTask(cfg, factory)
    await task.execute(pool.active(), payload_per_account=PAYLOAD)


if __name__ == "__main__":
    asyncio.run(main())
