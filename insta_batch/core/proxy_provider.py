"""ProxyProvider implementations.

Two modes:
- ApiProxyProvider: fetches a rotating list from a remote HTTP API and cycles through it.
- FileProxyProvider: reads a static list from a text file (one proxy per line).
"""
from __future__ import annotations

import asyncio
import random
import time
from pathlib import Path

import httpx
from insta_wizard import ProxyInfo

from insta_batch.core.config import PROJECT_ROOT, ProxySettings, env
from insta_batch.core.logger import get_logger


log = get_logger(__name__)


class ApiProxyProvider:
    """Fetches proxies from an HTTP API and rotates between them.

    Expected API response: plain text (one proxy per line) OR JSON list of strings.
    Each line must be parseable by `ProxyInfo.from_string`.
    """

    def __init__(
        self,
        api_url: str,
        token: str | None = None,
        cache_seconds: int = 60,
    ) -> None:
        self._api_url = api_url
        self._token = token
        self._cache_seconds = cache_seconds
        self._pool: list[ProxyInfo] = []
        self._last_fetch: float = 0.0
        self._lock = asyncio.Lock()

    async def _fetch(self) -> None:
        headers = {"Authorization": f"Bearer {self._token}"} if self._token else {}
        async with httpx.AsyncClient(timeout=15.0) as c:
            r = await c.get(self._api_url, headers=headers)
            r.raise_for_status()
            text = r.text.strip()
            try:
                import json

                items = json.loads(text)
                if not isinstance(items, list):
                    items = [text]
            except (json.JSONDecodeError, ValueError):
                items = [line.strip() for line in text.splitlines() if line.strip()]

        new_pool: list[ProxyInfo] = []
        for s in items:
            try:
                new_pool.append(ProxyInfo.from_string(s))
            except Exception as e:
                log.warning("Skipping malformed proxy %r: %s", s, e)
        self._pool = new_pool
        self._last_fetch = time.monotonic()
        log.info("Refreshed proxy pool: %d proxies", len(self._pool))

    async def provide_new(self) -> ProxyInfo | None:
        async with self._lock:
            if not self._pool or (time.monotonic() - self._last_fetch) > self._cache_seconds:
                try:
                    await self._fetch()
                except Exception as e:
                    log.error("Failed to refresh proxies: %s", e)
            if not self._pool:
                return None
            return random.choice(self._pool)


class FileProxyProvider:
    """Reads proxies from a text file (one per line)."""

    def __init__(self, file_path: str | Path) -> None:
        self._file_path = Path(file_path)
        self._pool: list[ProxyInfo] = []
        self._load()

    def _load(self) -> None:
        if not self._file_path.exists():
            log.warning("Proxy file %s not found", self._file_path)
            return
        with self._file_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                try:
                    self._pool.append(ProxyInfo.from_string(line))
                except Exception as e:
                    log.warning("Skipping malformed proxy %r: %s", line, e)

    async def provide_new(self) -> ProxyInfo | None:
        if not self._pool:
            return None
        return random.choice(self._pool)


def build_proxy_provider(settings: ProxySettings):
    """Factory — returns a provider instance based on settings (or None if disabled)."""
    if not settings.enabled or settings.source == "none":
        return None
    if settings.source == "api":
        token = env(settings.api_token_env)
        if not settings.api_url:
            log.warning("proxy.source='api' but api_url empty — disabling proxy")
            return None
        return ApiProxyProvider(
            api_url=settings.api_url,
            token=token,
            cache_seconds=settings.api_cache_seconds,
        )
    if settings.source == "file":
        path = Path(settings.file_path)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return FileProxyProvider(path)
    raise ValueError(f"Unknown proxy source: {settings.source}")
