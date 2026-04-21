"""Like / unlike / comment tasks."""
from __future__ import annotations

from dataclasses import dataclass

from insta_wizard import MobileClient

from insta_batch.core.account_pool import Account
from insta_batch.core.utils import jittered_sleep
from insta_batch.tasks.base import BaseTask, TaskResult


@dataclass
class LikePayload:
    media_ids: list[str]
    unlike: bool = False


@dataclass
class CommentPayload:
    # [(media_id, comment_text), ...]
    items: list[tuple[str, str]]


class LikeTask(BaseTask):
    name = "like"

    async def run_for_account(
        self, client: MobileClient, account: Account, payload: LikePayload
    ) -> TaskResult:
        done: list[str] = []
        for mid in payload.media_ids:
            if payload.unlike:
                await client.media.unlike(mid)
            else:
                await client.media.like(mid)
            done.append(mid)
            await jittered_sleep(self._config.concurrency)
        action = "unliked" if payload.unlike else "liked"
        return TaskResult(
            account=account.username,
            ok=True,
            detail=f"{action} {len(done)} media",
            data=done,
        )


class CommentTask(BaseTask):
    name = "comment"

    async def run_for_account(
        self, client: MobileClient, account: Account, payload: CommentPayload
    ) -> TaskResult:
        done: list[str] = []
        for media_id, text in payload.items:
            c = await client.media.add_comment(media_id, text)
            done.append(str(c.pk))
            await jittered_sleep(self._config.concurrency)
        return TaskResult(
            account=account.username,
            ok=True,
            detail=f"posted {len(done)} comments",
            data=done,
        )
