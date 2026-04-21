"""Account registration tasks.

Instagram requires a verification code delivered via email or SMS. You plug in
a concrete provider that implements insta-wizard's `EmailCodeSignupProvider` or
`PhoneSmsCodeProvider` protocol — usually backed by a third-party OTP service
(e.g. 5sim / smshub / a mailbox IMAP reader).

The Task does NOT spin up a session afterwards — it only returns the new
credentials so your caller can persist them to accounts.yaml and then run
`scripts/login_and_save.py` on the batch.

NOTE: mass account creation is against Instagram's ToS. Use only with explicit
authorization for your own testing infrastructure.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from insta_wizard import MobileClient

from insta_batch.core.account_pool import Account
from insta_batch.tasks.base import BaseTask, TaskResult


@dataclass
class RegisterSpec:
    username: str
    password: str
    first_name: str
    birth_day: int
    birth_month: int
    birth_year: int
    # Email or phone number depending on task variant
    contact: str


class RegisterEmailTask(BaseTask):
    """Payload: (RegisterSpec, EmailCodeSignupProvider).

    The account context this task runs under is only used as a source of
    device/proxy — no login happens first. Typically you run this task against
    a special 'bootstrap' account entry with `enabled: false` to avoid
    accidental cross-contamination with real sessions.
    """

    name = "register_email"

    async def run_for_account(
        self, client: MobileClient, account: Account, payload: tuple[RegisterSpec, Any]
    ) -> TaskResult:
        spec, provider = payload
        result = await client.registration.register_account_email(
            username=spec.username,
            password=spec.password,
            first_name=spec.first_name,
            day=spec.birth_day,
            month=spec.birth_month,
            year=spec.birth_year,
            email_code_provider=provider,
        )
        return TaskResult(
            account=account.username,
            ok=True,
            detail=f"registered {spec.username}",
            data={"username": spec.username, "result": repr(result)},
        )

    # Override _run_one to skip login — we don't want to log in as "account"
    # before registering a fresh one.
    async def _run_one(self, account: Account, payload: Any) -> TaskResult:
        async with self._sem:
            client = self._factory.build(account)
            try:
                async with client:
                    return await self.run_for_account(client, account, payload)
            except Exception as e:
                return TaskResult(
                    account=account.username, ok=False, detail=f"{type(e).__name__}: {e}"
                )


class RegisterSmsTask(RegisterEmailTask):
    name = "register_sms"

    async def run_for_account(
        self, client: MobileClient, account: Account, payload: tuple[RegisterSpec, Any]
    ) -> TaskResult:
        spec, provider = payload
        result = await client.registration.register_account_sms(
            username=spec.username,
            password=spec.password,
            first_name=spec.first_name,
            day=spec.birth_day,
            month=spec.birth_month,
            year=spec.birth_year,
            phone_code_provider=provider,
        )
        return TaskResult(
            account=account.username,
            ok=True,
            detail=f"registered {spec.username}",
            data={"username": spec.username, "result": repr(result)},
        )
