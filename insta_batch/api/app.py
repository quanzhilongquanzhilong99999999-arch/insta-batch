"""FastAPI application factory.

Uvicorn entrypoint: `scripts/run_api.py` or
`uvicorn insta_batch.api.app:app --host 0.0.0.0 --port 8000`.

Bootstrap order:
1. load .env (once, inside load_config)
2. warm singletons — this also triggers accounts.yaml parsing so bad YAML
   fails loudly at boot instead of on first request
3. mount routers

Every task route returns 202 Accepted + {job_id}. Clients poll /v1/jobs/{id}.
"""
from __future__ import annotations

from fastapi import Depends, FastAPI

from insta_batch import __version__
from insta_batch.api.deps import (
    get_account_pool,
    get_config,
    require_api_key,
)
from insta_batch.api.jobs import get_job_manager
from insta_batch.api.routers import accounts as accounts_router
from insta_batch.api.routers import jobs as jobs_router
from insta_batch.api.routers import tasks as tasks_router
from insta_batch.api.schemas import HealthResponse
from insta_batch.core.account_pool import AccountPool


def create_app() -> FastAPI:
    app = FastAPI(
        title="insta-batch API",
        version=__version__,
        description=(
            "Async multi-account Instagram automation. All task endpoints "
            "return a job_id immediately; poll /v1/jobs/{job_id} for results. "
            "Authenticate with the `X-API-Key` header."
        ),
    )

    # Warm singletons — raises loudly on bad config at boot.
    get_config()
    get_account_pool()

    @app.get("/", tags=["health"])
    async def root() -> dict:
        return {"service": "insta-batch", "version": __version__, "docs": "/docs"}

    @app.get("/v1/health", response_model=HealthResponse, tags=["health"])
    async def health(
        _: str = Depends(require_api_key),
        pool: AccountPool = Depends(get_account_pool),
    ) -> HealthResponse:
        all_accts = pool.all()
        return HealthResponse(
            version=__version__,
            accounts_total=len(all_accts),
            accounts_enabled=sum(1 for a in all_accts if a.enabled),
            jobs_active=get_job_manager().active_count(),
        )

    app.include_router(accounts_router.router)
    app.include_router(tasks_router.router)
    app.include_router(jobs_router.router)

    return app
