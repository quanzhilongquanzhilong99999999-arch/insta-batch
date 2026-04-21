"""/v1/tasks/* — submit batch operations. Returns a job_id; poll /v1/jobs/{id}."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from insta_batch.api.deps import (
    get_account_pool,
    get_factory,
    require_api_key,
)
from insta_batch.api.jobs import get_job_manager
from insta_batch.api.schemas import (
    AccountSelector,
    CommentRequest,
    FollowRequest,
    JobIdResponse,
    LikeRequest,
    MonitorRequest,
    PublishPhotoRequest,
    PublishReelRequest,
    UnfollowRequest,
)
from insta_batch.core.account_pool import Account, AccountPool
from insta_batch.core.client_factory import ClientFactory
from insta_batch.core.config import Config
from insta_batch.tasks.base import BaseTask, TaskStats
from insta_batch.tasks.follow import FollowPayload, FollowTask, UnfollowTask
from insta_batch.tasks.like_comment import (
    CommentPayload,
    CommentTask,
    LikePayload,
    LikeTask,
)
from insta_batch.tasks.monitor import MonitorPayload, MonitorTask
from insta_batch.tasks.publish import (
    PhotoPayload,
    PublishPhotoTask,
    PublishReelTask,
    ReelPayload,
)

router = APIRouter(prefix="/v1/tasks", tags=["tasks"])


# ---------------------------------------------------------------- helpers


def _select_accounts(pool: AccountPool, sel: AccountSelector) -> list[Account]:
    if sel.usernames:
        wanted = set(sel.usernames)
        picked = [a for a in pool.all() if a.username in wanted and a.enabled]
    else:
        picked = pool.active(tags=sel.tags)
    if not picked:
        raise HTTPException(400, detail="No enabled accounts matched the selector")
    return picked


async def _enqueue(
    task_type: str,
    task: BaseTask,
    accounts: list[Account],
    payload,
) -> JobIdResponse:
    async def runner() -> TaskStats:
        return await task.execute(accounts, payload_per_account=payload)

    job_id = await get_job_manager().submit(
        task_type=task_type, total_accounts=len(accounts), runner=runner
    )
    return JobIdResponse(job_id=job_id)


# ---------------------------------------------------------------- routes


@router.post("/follow", response_model=JobIdResponse, status_code=202)
async def submit_follow(
    req: FollowRequest,
    _: str = Depends(require_api_key),
    cfg: Config = Depends(lambda: __import__("insta_batch.api.deps", fromlist=["get_config"]).get_config()),
    pool: AccountPool = Depends(get_account_pool),
    factory: ClientFactory = Depends(get_factory),
) -> JobIdResponse:
    accounts = _select_accounts(pool, req.accounts)
    task = FollowTask(cfg, factory)
    return await _enqueue(
        "follow",
        task,
        accounts,
        FollowPayload(usernames=req.usernames, user_ids=req.user_ids),
    )


@router.post("/unfollow", response_model=JobIdResponse, status_code=202)
async def submit_unfollow(
    req: UnfollowRequest,
    _: str = Depends(require_api_key),
    cfg: Config = Depends(lambda: __import__("insta_batch.api.deps", fromlist=["get_config"]).get_config()),
    pool: AccountPool = Depends(get_account_pool),
    factory: ClientFactory = Depends(get_factory),
) -> JobIdResponse:
    accounts = _select_accounts(pool, req.accounts)
    task = UnfollowTask(cfg, factory)
    return await _enqueue(
        "unfollow",
        task,
        accounts,
        FollowPayload(usernames=req.usernames, user_ids=req.user_ids),
    )


@router.post("/like", response_model=JobIdResponse, status_code=202)
async def submit_like(
    req: LikeRequest,
    _: str = Depends(require_api_key),
    cfg: Config = Depends(lambda: __import__("insta_batch.api.deps", fromlist=["get_config"]).get_config()),
    pool: AccountPool = Depends(get_account_pool),
    factory: ClientFactory = Depends(get_factory),
) -> JobIdResponse:
    accounts = _select_accounts(pool, req.accounts)
    task = LikeTask(cfg, factory)
    return await _enqueue(
        "like",
        task,
        accounts,
        LikePayload(media_ids=req.media_ids, unlike=req.unlike),
    )


@router.post("/comment", response_model=JobIdResponse, status_code=202)
async def submit_comment(
    req: CommentRequest,
    _: str = Depends(require_api_key),
    cfg: Config = Depends(lambda: __import__("insta_batch.api.deps", fromlist=["get_config"]).get_config()),
    pool: AccountPool = Depends(get_account_pool),
    factory: ClientFactory = Depends(get_factory),
) -> JobIdResponse:
    accounts = _select_accounts(pool, req.accounts)
    task = CommentTask(cfg, factory)
    return await _enqueue("comment", task, accounts, CommentPayload(items=req.items))


@router.post("/publish/photo", response_model=JobIdResponse, status_code=202)
async def submit_publish_photo(
    req: PublishPhotoRequest,
    _: str = Depends(require_api_key),
    cfg: Config = Depends(lambda: __import__("insta_batch.api.deps", fromlist=["get_config"]).get_config()),
    pool: AccountPool = Depends(get_account_pool),
    factory: ClientFactory = Depends(get_factory),
) -> JobIdResponse:
    accounts = _select_accounts(pool, req.accounts)
    task = PublishPhotoTask(cfg, factory)
    return await _enqueue(
        "publish_photo",
        task,
        accounts,
        PhotoPayload(image_path=req.image_path, caption=req.caption),
    )


@router.post("/publish/reel", response_model=JobIdResponse, status_code=202)
async def submit_publish_reel(
    req: PublishReelRequest,
    _: str = Depends(require_api_key),
    cfg: Config = Depends(lambda: __import__("insta_batch.api.deps", fromlist=["get_config"]).get_config()),
    pool: AccountPool = Depends(get_account_pool),
    factory: ClientFactory = Depends(get_factory),
) -> JobIdResponse:
    accounts = _select_accounts(pool, req.accounts)
    task = PublishReelTask(cfg, factory)
    return await _enqueue(
        "publish_reel",
        task,
        accounts,
        ReelPayload(
            video_path=req.video_path,
            caption=req.caption,
            thumbnail_path=req.thumbnail_path,
            share_to_feed=req.share_to_feed,
        ),
    )


@router.post("/monitor", response_model=JobIdResponse, status_code=202)
async def submit_monitor(
    req: MonitorRequest,
    _: str = Depends(require_api_key),
    cfg: Config = Depends(lambda: __import__("insta_batch.api.deps", fromlist=["get_config"]).get_config()),
    pool: AccountPool = Depends(get_account_pool),
    factory: ClientFactory = Depends(get_factory),
) -> JobIdResponse:
    accounts = _select_accounts(pool, req.accounts)
    task = MonitorTask(cfg, factory)
    return await _enqueue(
        "monitor",
        task,
        accounts,
        MonitorPayload(usernames=req.usernames, output_file=req.output_file),
    )
