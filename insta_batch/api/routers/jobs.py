"""/v1/jobs — inspect, list, cancel."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from insta_batch.api.deps import require_api_key
from insta_batch.api.jobs import get_job_manager
from insta_batch.api.schemas import JobView, StandardOK


router = APIRouter(prefix="/v1/jobs", tags=["jobs"])


@router.get("", response_model=list[JobView])
async def list_jobs(
    limit: int = Query(50, ge=1, le=500),
    _: str = Depends(require_api_key),
) -> list[JobView]:
    mgr = get_job_manager()
    return [j.snapshot() for j in mgr.list(limit=limit)]


@router.get("/{job_id}", response_model=JobView)
async def get_job(
    job_id: str,
    _: str = Depends(require_api_key),
) -> JobView:
    mgr = get_job_manager()
    job = mgr.get(job_id)
    if job is None:
        raise HTTPException(404, detail="job not found")
    return job.snapshot()


@router.delete("/{job_id}", response_model=StandardOK)
async def cancel_job(
    job_id: str,
    _: str = Depends(require_api_key),
) -> StandardOK:
    mgr = get_job_manager()
    if not mgr.cancel(job_id):
        raise HTTPException(409, detail="job not cancellable (missing or already finished)")
    return StandardOK(message="cancel signal sent")
