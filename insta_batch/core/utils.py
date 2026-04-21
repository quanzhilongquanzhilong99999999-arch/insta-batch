"""Misc helpers."""
from __future__ import annotations

import asyncio
import random

from insta_batch.core.config import ConcurrencySettings


async def jittered_sleep(settings: ConcurrencySettings) -> None:
    """Sleep a random duration inside [min, max] — humanizes batch action cadence."""
    t = random.uniform(settings.per_action_delay_min, settings.per_action_delay_max)
    await asyncio.sleep(t)


def chunked(items: list, n: int) -> list[list]:
    """Split `items` into chunks of size <= n."""
    return [items[i : i + n] for i in range(0, len(items), n)]
