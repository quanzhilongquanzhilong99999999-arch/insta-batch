"""Unified configuration loader: YAML + .env.

Loads `config/settings.yaml` for structural settings and a `.env` file
(via python-dotenv) for secrets (proxy API keys, etc.).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SETTINGS_PATH = PROJECT_ROOT / "config" / "settings.yaml"
DEFAULT_ACCOUNTS_PATH = PROJECT_ROOT / "config" / "accounts.yaml"
SESSIONS_DIR = PROJECT_ROOT / "sessions"
LOGS_DIR = PROJECT_ROOT / "logs"
DATA_DIR = PROJECT_ROOT / "data"


@dataclass
class ConcurrencySettings:
    max_parallel_accounts: int = 5
    per_action_delay_min: float = 2.0
    per_action_delay_max: float = 6.0


@dataclass
class RetrySettings:
    network_error_retry_limit: int = 3
    network_error_retry_delay: float = 1.5
    change_proxies: bool = True
    proxy_change_limit: int = 5


@dataclass
class ProxySettings:
    enabled: bool = True
    # How to fetch proxies: "api" | "file" | "none"
    source: str = "api"
    # For source=api:
    api_url: str = ""
    api_token_env: str = "PROXY_API_TOKEN"
    api_cache_seconds: int = 60
    # For source=file:
    file_path: str = "config/proxies.txt"


@dataclass
class DeviceSettings:
    # "random" or one of: SAMSUNG_A16, SAMSUNG_S23, SAMSUNG_A54, PIXEL_8, REDMI_NOTE_13_PRO
    preset: str = "random"
    locale: str = "en_US"
    timezone: str = "America/New_York"


@dataclass
class Config:
    concurrency: ConcurrencySettings = field(default_factory=ConcurrencySettings)
    retry: RetrySettings = field(default_factory=RetrySettings)
    proxy: ProxySettings = field(default_factory=ProxySettings)
    device: DeviceSettings = field(default_factory=DeviceSettings)
    log_level: str = "INFO"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Config":
        return cls(
            concurrency=ConcurrencySettings(**(data.get("concurrency") or {})),
            retry=RetrySettings(**(data.get("retry") or {})),
            proxy=ProxySettings(**(data.get("proxy") or {})),
            device=DeviceSettings(**(data.get("device") or {})),
            log_level=data.get("log_level", "INFO"),
        )


def load_config(path: Path | str | None = None) -> Config:
    """Load .env first, then settings.yaml. Returns a Config instance."""
    load_dotenv(PROJECT_ROOT / ".env", override=False)

    settings_path = Path(path) if path else DEFAULT_SETTINGS_PATH
    if not settings_path.exists():
        return Config()

    with settings_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return Config.from_dict(data)


def env(name: str, default: str | None = None) -> str | None:
    return os.getenv(name, default)
