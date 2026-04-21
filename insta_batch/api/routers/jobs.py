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
    return await mgr.list_views(limit=limit)


@router.get("/{job_id}", response_model=JobView)
async def get_job(
    job_id: str,
    _: str = Depends(require_api_key),
) -> JobView:
    mgr = get_job_manager()
    view = await mgr.get_view(job_id)
    if view is None:
        raise HTTPException(404, detail="job not found")
    return view


@router.delete("/{job_id}", response_model=StandardOK)
async def cancel_job(
    job_id: str,
    _: str = Depends(require_api_key),
) -> StandardOK:
    mgr = get_job_manager()
    if not await mgr.cancel(job_id):
        raise HTTPException(
            409,
            detail=(
                "Job not cancellable on this worker. "
                "Either it is already finished, or it was submitted to a different worker "
                "(cross-worker cancel is not supported in this version)."
            ),
        )
    return StandardOK(message="cancel signal sent")
