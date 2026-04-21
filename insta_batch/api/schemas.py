"""Pydantic request / response models for the HTTP API."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


# ---------- account selection (reused across task requests) ----------

class AccountSelector(BaseModel):
    """Which accounts to run the task on. Mutually additive — all matching
    accounts are selected. If nothing is specified, every enabled account runs."""

    usernames: list[str] | None = Field(
        default=None,
        description="Explicit account usernames. Takes precedence over tags.",
    )
    tags: list[str] | None = Field(
        default=None,
        description="Select accounts whose `tags` list intersects these.",
    )


# ---------- task payloads ----------

class FollowRequest(BaseModel):
    accounts: AccountSelector = Field(default_factory=AccountSelector)
    usernames: list[str] | None = None
    user_ids: list[str] | None = None


class UnfollowRequest(FollowRequest):
    pass


class LikeRequest(BaseModel):
    accounts: AccountSelector = Field(default_factory=AccountSelector)
    media_ids: list[str]
    unlike: bool = False


class CommentRequest(BaseModel):
    accounts: AccountSelector = Field(default_factory=AccountSelector)
    items: list[tuple[str, str]] = Field(
        description="[[media_id, comment_text], ...]"
    )


class PublishPhotoRequest(BaseModel):
    accounts: AccountSelector = Field(default_factory=AccountSelector)
    image_path: str = Field(description="Path on the server, relative to project root allowed")
    caption: str = ""


class PublishReelRequest(BaseModel):
    accounts: AccountSelector = Field(default_factory=AccountSelector)
    video_path: str
    caption: str = ""
    thumbnail_path: str | None = None
    share_to_feed: bool = True


class MonitorRequest(BaseModel):
    accounts: AccountSelector = Field(default_factory=AccountSelector)
    usernames: list[str] | None = Field(
        default=None,
        description="Target usernames to snapshot. None = snapshot the running account itself.",
    )
    output_file: str = "monitor.jsonl"


# ---------- job lifecycle ----------

JobStatusLit = Literal["pending", "running", "completed", "failed", "canceled"]


class JobProgress(BaseModel):
    total: int = 0
    ok: int = 0
    failed: int = 0
    skipped: int = 0


class JobIdResponse(BaseModel):
    job_id: str


class JobResultEntry(BaseModel):
    account: str
    ok: bool
    detail: str = ""


class JobView(BaseModel):
    job_id: str
    task_type: str
    status: JobStatusLit
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    progress: JobProgress = Field(default_factory=JobProgress)
    results: list[JobResultEntry] = Field(default_factory=list)
    error: str | None = None


# ---------- accounts ----------

class AccountView(BaseModel):
    username: str
    enabled: bool
    tags: list[str] = Field(default_factory=list)
    has_session: bool
    device_preset: str | None = None
    proxy_set: bool = False


# ---------- misc ----------

class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    version: str
    accounts_total: int
    accounts_enabled: int
    jobs_active: int


class ErrorResponse(BaseModel):
    detail: str


class StandardOK(BaseModel):
    ok: bool = True
    message: str = ""
