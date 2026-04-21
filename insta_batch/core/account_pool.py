"""Account model + pool with session persistence.

An `Account` holds credentials + device seed + cached session state.
`AccountPool` loads accounts from `config/accounts.yaml`, lazily saves/restores
per-account session JSON files under `sessions/`, and marks accounts as
disabled when they hit hard errors (banned / checkpoint-stuck / etc).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from insta_batch.core.config import (
    DEFAULT_ACCOUNTS_PATH,
    SESSIONS_DIR,
)
from insta_batch.core.logger import get_logger


log = get_logger(__name__)


@dataclass
class Account:
    username: str
    password: str
    # Per-account fingerprint seed — so the same account always presents the
    # same device profile across runs.
    device_preset: str | None = None  # overrides global default if set
    # Optional per-account sticky proxy (else pool assigns dynamically)
    proxy: str | None = None
    # Optional contact info used for registration / recovery
    email: str | None = None
    phone: str | None = None
    # Runtime flags
    enabled: bool = True
    tags: list[str] = field(default_factory=list)

    @property
    def session_path(self) -> Path:
        return SESSIONS_DIR / f"{self.username}.json"

    def load_state(self) -> dict | None:
        if not self.session_path.exists():
            return None
        try:
            return json.loads(self.session_path.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning("Failed to read session for %s: %s", self.username, e)
            return None

    def save_state(self, state: dict) -> None:
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        self.session_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def drop_state(self) -> None:
        if self.session_path.exists():
            self.session_path.unlink()


class AccountPool:
    def __init__(self, accounts: list[Account]):
        self._accounts = accounts

    @classmethod
    def load(cls, path: Path | str | None = None) -> "AccountPool":
        p = Path(path) if path else DEFAULT_ACCOUNTS_PATH
        if not p.exists():
            raise FileNotFoundError(
                f"Accounts file not found: {p}\n"
                f"Copy config/accounts.yaml.example to config/accounts.yaml and fill it in."
            )
        with p.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

        items = raw.get("accounts", [])
        accounts = [Account(**item) for item in items]
        log.info("Loaded %d accounts from %s", len(accounts), p)
        return cls(accounts)

    def active(self, tags: list[str] | None = None) -> list[Account]:
        result = [a for a in self._accounts if a.enabled]
        if tags:
            tagset = set(tags)
            result = [a for a in result if tagset.intersection(a.tags)]
        return result

    def all(self) -> list[Account]:
        return list(self._accounts)

    def disable(self, username: str, reason: str) -> None:
        for a in self._accounts:
            if a.username == username:
                a.enabled = False
                log.warning("Disabled account %s: %s", username, reason)
                return
