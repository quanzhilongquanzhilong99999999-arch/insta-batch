"""Publish photo / reel tasks."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from insta_wizard import MobileClient

from insta_batch.core.account_pool import Account
from insta_batch.tasks.base import BaseTask, TaskResult


@dataclass
class PhotoPayload:
    image_path: str
    caption: str = ""


@dataclass
class ReelPayload:
    video_path: str
    caption: str = ""
    thumbnail_path: str | None = None
    share_to_feed: bool = True


class PublishPhotoTask(BaseTask):
    name = "publish_photo"

    async def run_for_account(
        self, client: MobileClient, account: Account, payload: PhotoPayload
    ) -> TaskResult:
        data = Path(payload.image_path).read_bytes()
        media = await client.media.publish_photo(data, caption=payload.caption)
        return TaskResult(
            account=account.username,
            ok=True,
            detail=f"photo pk={media.pk}",
            data=str(media.pk),
        )


class PublishReelTask(BaseTask):
    name = "publish_reel"

    async def run_for_account(
        self, client: MobileClient, account: Account, payload: ReelPayload
    ) -> TaskResult:
        video = Path(payload.video_path).read_bytes()
        thumb = Path(payload.thumbnail_path).read_bytes() if payload.thumbnail_path else None
        media = await client.media.publish_reel(
            video=video,
            caption=payload.caption,
            thumbnail=thumb,
            share_to_feed=payload.share_to_feed,
        )
        return TaskResult(
            account=account.username,
            ok=True,
            detail=f"reel pk={media.pk}",
            data=str(media.pk),
        )
