"""/v1/accounts — list, reload, per-account inspection."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from insta_batch.api.deps import get_account_pool, reset_singletons, require_api_key
from insta_batch.api.schemas import AccountView, StandardOK
from insta_batch.core.account_pool import AccountPool


router = APIRouter(prefix="/v1/accounts", tags=["accounts"])


def _view(pool: AccountPool) -> list[AccountView]:
    return [
        AccountView(
            username=a.username,
            enabled=a.enabled,
            tags=a.tags,
            has_session=a.session_path.exists(),
            device_preset=a.device_preset,
            proxy_set=bool(a.proxy),
        )
        for a in pool.all()
    ]


@router.get("", response_model=list[AccountView])
async def list_accounts(
    _: str = Depends(require_api_key),
    pool: AccountPool = Depends(get_account_pool),
) -> list[AccountView]:
    return _view(pool)


@router.get("/{username}", response_model=AccountView)
async def get_account(
    username: str,
    _: str = Depends(require_api_key),
    pool: AccountPool = Depends(get_account_pool),
) -> AccountView:
    for a in pool.all():
        if a.username == username:
            return _view(pool)[pool.all().index(a)]
    raise HTTPException(404, detail=f"account {username!r} not found")


@router.post("/reload", response_model=StandardOK)
async def reload_accounts(_: str = Depends(require_api_key)) -> StandardOK:
    """Reload config/accounts.yaml and settings.yaml from disk without restarting."""
    reset_singletons()
    # Touch the pool so any parse error surfaces now
    from insta_batch.api.deps import get_account_pool as _get

    _get()
    return StandardOK(message="config reloaded")
