"""Follow / unfollow tasks."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from insta_wizard import MobileClient

from insta_batch.core.account_pool import Account
from insta_batch.core.utils import jittered_sleep
from insta_batch.tasks.base import BaseTask, TaskResult


@dataclass
class FollowPayload:
    """Users to follow for *this* account. Pass usernames OR pk ids."""
    usernames: list[str] | None = None
    user_ids: list[str] | None = None


async def _resolve_targets(client: MobileClient, payload: FollowPayload) -> list[str]:
    ids: list[str] = list(payload.user_ids or [])
    for uname in payload.usernames or []:
        user = await client.users.get_info_by_username(uname)
        ids.append(str(user.pk))
    return ids


class FollowTask(BaseTask):
    name = "follow"

    async def run_for_account(
        self, client: MobileClient, account: Account, payload: FollowPayload
    ) -> TaskResult:
        ids = await _resolve_targets(client, payload)
        followed: list[str] = []
        for uid in ids:
            await client.friendships.follow(uid)
            followed.append(uid)
            await jittered_sleep(self._config.concurrency)
        return TaskResult(
            account=account.username,
            ok=True,
            detail=f"followed {len(followed)} users",
            data=followed,
        )


class UnfollowTask(BaseTask):
    name = "unfollow"

    async def run_for_account(
        self, client: MobileClient, account: Account, payload: FollowPayload
    ) -> TaskResult:
        ids = await _resolve_targets(client, payload)
        unfollowed: list[str] = []
        for uid in ids:
            await client.friendships.unfollow(uid)
            unfollowed.append(uid)
            await jittered_sleep(self._config.concurrency)
        return TaskResult(
            account=account.username,
            ok=True,
            detail=f"unfollowed {len(unfollowed)} users",
            data=unfollowed,
        )
