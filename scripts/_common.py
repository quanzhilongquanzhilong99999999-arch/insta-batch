"""Shared bootstrap helpers for scripts in this folder."""
from __future__ import annotations

import sys
from pathlib import Path

# Allow `python scripts/xxx.py` invocation without editable install.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from insta_batch.core import (  # noqa: E402
    AccountPool,
    ClientFactory,
    Config,
    load_config,
    setup_logging,
)
from insta_batch.core.proxy_provider import build_proxy_provider  # noqa: E402


def bootstrap() -> tuple[Config, AccountPool, ClientFactory]:
    cfg = load_config()
    setup_logging(cfg.log_level)
    pool = AccountPool.load()
    proxy_provider = build_proxy_provider(cfg.proxy)
    factory = ClientFactory(cfg, proxy_provider=proxy_provider)
    return cfg, pool, factory
