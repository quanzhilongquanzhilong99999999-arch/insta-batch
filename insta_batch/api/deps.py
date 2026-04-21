"""FastAPI dependencies: API key auth, shared singletons (config / pool / factory)."""
from __future__ import annotations

import os
from functools import lru_cache

from fastapi import Header, HTTPException, status

from insta_batch.core import (
    AccountPool,
    ClientFactory,
    Config,
    load_config,
    setup_logging,
)
from insta_batch.core.proxy_provider import build_proxy_provider


def _parse_api_keys() -> set[str]:
    raw = os.getenv("API_KEYS", "").strip()
    if not raw:
        return set()
    return {k.strip() for k in raw.split(",") if k.strip()}


async def require_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> str:
    keys = _parse_api_keys()
    if not keys:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server has no API_KEYS configured",
        )
    if x_api_key not in keys:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
    return x_api_key


@lru_cache(maxsize=1)
def get_config() -> Config:
    cfg = load_config()
    setup_logging(cfg.log_level)
    return cfg


@lru_cache(maxsize=1)
def get_account_pool() -> AccountPool:
    return AccountPool.load()


@lru_cache(maxsize=1)
def get_factory() -> ClientFactory:
    cfg = get_config()
    provider = build_proxy_provider(cfg.proxy)
    return ClientFactory(cfg, proxy_provider=provider)


def reset_singletons() -> None:
    """For tests / hot-reload of accounts.yaml without restart."""
    get_config.cache_clear()
    get_account_pool.cache_clear()
    get_factory.cache_clear()
