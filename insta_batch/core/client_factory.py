"""Builds a fully-configured MobileClient for a given Account.

Responsibilities:
- Pick / materialize the device fingerprint (per-account override or global preset)
- Build TransportSettings (retry + proxy rotation)
- Attach a sticky proxy if the account has one, else let the ProxyProvider rotate
- Restore cached session state if present
"""
from __future__ import annotations

from insta_wizard import (
    AndroidDeviceInfo,
    MobileClient,
    ProxyInfo,
    TransportSettings,
)
from insta_wizard.mobile.models.android_device_info import AndroidPreset

from insta_batch.core.account_pool import Account
from insta_batch.core.config import Config
from insta_batch.core.logger import get_logger


log = get_logger(__name__)


def _build_device(preset_name: str, locale: str, tz: str) -> AndroidDeviceInfo:
    if preset_name == "random":
        return AndroidDeviceInfo.random()
    try:
        preset = AndroidPreset[preset_name]
    except KeyError:
        log.warning("Unknown device preset %r, falling back to random", preset_name)
        return AndroidDeviceInfo.random()
    return AndroidDeviceInfo.from_preset(preset, locale=locale, timezone=tz)


class ClientFactory:
    def __init__(self, config: Config, proxy_provider=None):
        self._config = config
        self._proxy_provider = proxy_provider

    def _transport_settings(self) -> TransportSettings:
        r = self._config.retry
        return TransportSettings(
            network_error_retry_limit=r.network_error_retry_limit,
            network_error_retry_delay=r.network_error_retry_delay,
            change_proxies=r.change_proxies and self._proxy_provider is not None,
            proxy_change_limit=r.proxy_change_limit,
            proxy_provider=self._proxy_provider,
        )

    def build(self, account: Account) -> MobileClient:
        """Create a MobileClient configured for this account. Caller must use
        it as an async context manager (`async with factory.build(acc) as c:`).

        The client's session state is *not* auto-loaded here — the Task layer
        decides whether to load state or perform a fresh login, because that's
        where retry-on-session-expired belongs.
        """
        d = self._config.device
        device = _build_device(account.device_preset or d.preset, d.locale, d.timezone)

        proxy: ProxyInfo | None = None
        if account.proxy:
            proxy = ProxyInfo.from_string(account.proxy)

        return MobileClient(
            device=device,
            proxy=proxy,
            transport_settings=self._transport_settings(),
        )
