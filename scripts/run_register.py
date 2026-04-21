"""Batch account registration — SKELETON.

You MUST provide a concrete `EmailCodeSignupProvider` (or `PhoneSmsCodeProvider`)
that reads the verification code out of your email/SMS receiving service. The
stub below raises NotImplementedError so you're forced to plug in a real one
before running.

NOTE: mass account creation violates Instagram's Terms of Service. Use only
with explicit authorization for your own test infrastructure.
"""
from __future__ import annotations

import asyncio

from _common import bootstrap

from insta_batch.core.account_pool import Account
from insta_batch.tasks.register import RegisterEmailTask, RegisterSpec


class MyEmailProvider:
    """Implement the EmailCodeSignupProvider protocol here.

    See `insta_wizard.common.interfaces` for the exact method signatures.
    Typical implementation: poll an IMAP inbox, parse the latest IG email,
    return the 6-digit code.
    """

    async def get_email(self) -> str:
        raise NotImplementedError("Return the email address to register with.")

    async def get_confirmation_code(self, email: str) -> str:
        raise NotImplementedError("Fetch the verification code from your inbox.")


# Accounts to create — one RegisterSpec per new account.
NEW_ACCOUNTS: list[RegisterSpec] = [
    # RegisterSpec(
    #     username="new_user_001",
    #     password="StrongP@ss1",
    #     first_name="Alice",
    #     birth_day=14, birth_month=6, birth_year=1998,
    #     contact="alice001@inbox.example.com",
    # ),
]


async def main() -> None:
    cfg, pool, factory = bootstrap()

    # Use one real enabled account as a "bootstrap" source of device/proxy,
    # OR configure a synthetic one with enabled=false and reference it here.
    bootstraps = pool.active()
    if not bootstraps:
        raise SystemExit("Need at least one enabled account in accounts.yaml")

    task = RegisterEmailTask(cfg, factory)
    provider = MyEmailProvider()

    for spec in NEW_ACCOUNTS:
        # Rotate which account the registration runs under (for device/proxy diversity).
        carrier: Account = bootstraps[len(spec.username) % len(bootstraps)]
        result = await task._run_one(carrier, (spec, provider))  # noqa: SLF001
        print(result)


if __name__ == "__main__":
    if not NEW_ACCOUNTS:
        raise SystemExit("Populate NEW_ACCOUNTS list and implement MyEmailProvider first.")
    asyncio.run(main())
