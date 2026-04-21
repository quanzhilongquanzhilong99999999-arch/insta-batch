"""Account status monitor / basic profile scraper."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from insta_wizard import MobileClient

from insta_batch.core.account_pool import Account
from insta_batch.core.config import DATA_DIR
from insta_batch.tasks.base import BaseTask, TaskResult


@dataclass
class MonitorPayload:
    # Usernames to scrape for each running account; if None, only self-profile is pulled.
    usernames: list[str] | None = None
    output_file: str = "monitor.jsonl"


@dataclass
class ProfileSnapshot:
    checked_at: str
    checked_by: str
    username: str
    pk: str
    full_name: str
    follower_count: int
    following_count: int
    media_count: int
    is_private: bool
    is_verified: bool


class MonitorTask(BaseTask):
    """Verifies the account is alive (get_current_user) and optionally snapshots
    a list of target usernames' public counters. Appends JSONL to data/."""

    name = "monitor"

    async def run_for_account(
        self, client: MobileClient, account: Account, payload: MonitorPayload
    ) -> TaskResult:
        me = await client.account.get_current_user()
        snapshots: list[ProfileSnapshot] = []
        now = datetime.now(timezone.utc).isoformat()

        targets = payload.usernames or [me.username]
        for uname in targets:
            try:
                u = await client.users.get_info_by_username(uname)
                snapshots.append(
                    ProfileSnapshot(
                        checked_at=now,
                        checked_by=account.username,
                        username=u.username,
                        pk=str(u.pk),
                        full_name=u.full_name or "",
                        follower_count=int(u.follower_count or 0),
                        following_count=int(u.following_count or 0),
                        media_count=int(u.media_count or 0),
                        is_private=bool(u.is_private),
                        is_verified=bool(u.is_verified),
                    )
                )
            except Exception as e:
                snapshots.append(
                    ProfileSnapshot(
                        checked_at=now,
                        checked_by=account.username,
                        username=uname,
                        pk="",
                        full_name=f"ERROR: {type(e).__name__}: {e}",
                        follower_count=0,
                        following_count=0,
                        media_count=0,
                        is_private=False,
                        is_verified=False,
                    )
                )

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        out = Path(payload.output_file)
        if not out.is_absolute():
            out = DATA_DIR / out
        with out.open("a", encoding="utf-8") as f:
            for s in snapshots:
                f.write(json.dumps(asdict(s), ensure_ascii=False) + "\n")

        return TaskResult(
            account=account.username,
            ok=True,
            detail=f"snapshots={len(snapshots)} file={out.name}",
            data=[asdict(s) for s in snapshots],
        )
