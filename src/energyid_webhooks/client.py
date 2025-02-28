"""Clients for the EnergyID Webhooks API (V1)."""

from abc import ABC
from typing import Any

import aiohttp
import requests
import warnings
from .metercatalog import MeterCatalog
from .payload import WebhookPayload
from .webhookpolicy import WebhookPolicy

warnings.warn(
    "The V1 WebhookClient is deprecated. Please use the new WebhookClient from "
    "energyid_webhooks import WebhookClient for V2 API support with device "
    "provisioning and authentication.",
    DeprecationWarning,
    stacklevel=2,
)


class BaseClient(ABC):
    """Base client for the EnergyID Webhooks API."""

    meter_catalog_url = "https://api.energyid.eu/api/v1/catalogs/meters"

    def __init__(
        self,
        webhook_url: str,
        session: requests.Session | aiohttp.ClientSession | None = None,
    ) -> None:
        self.webhook_url = webhook_url
        self.session = session

        self._meter_catalog: MeterCatalog | None = None
        self._webhook_policy: WebhookPolicy | None = None


class WebhookClient(BaseClient):
    """Client for the EnergyID Webhooks API."""

    def __init__(
        self, webhook_url: str, session: requests.Session | None = None
    ) -> None:
        self.session = session if session is not None else requests.Session()
        super().__init__(webhook_url=webhook_url, session=self.session)

    @property
    def policy(self) -> WebhookPolicy:
        """Get the webhook policy."""
        if self._webhook_policy is None:
            self._webhook_policy = self.get_policy()
        return self._webhook_policy

    def get_policy(self) -> WebhookPolicy:
        """Get the webhook policy."""
        if not isinstance(self.session, requests.Session):
            raise RuntimeError("Session not initialized")
        request = self.session.get(url=self.webhook_url)
        request.raise_for_status()
        return WebhookPolicy(request.json())

    def post(self, data: dict[str, Any]) -> None:
        """Post data to the webhook."""
        if not isinstance(self.session, requests.Session):
            raise RuntimeError("Session not initialized")
        request = self.session.post(url=self.webhook_url, json=data)
        request.raise_for_status()

    @property
    def meter_catalog(self) -> MeterCatalog:
        """Get the meter catalog."""
        if self._meter_catalog is None:
            self._meter_catalog = self.get_meter_catalog()
        return self._meter_catalog

    def get_meter_catalog(self) -> MeterCatalog:
        """Get the meter catalog."""
        if not isinstance(self.session, requests.Session):
            raise RuntimeError("Session not initialized")
        request = self.session.get(url=self.meter_catalog_url)
        request.raise_for_status()
        return MeterCatalog(request.json())

    def post_payload(self, payload: WebhookPayload) -> None:
        """Post a webhook payload."""
        self.post(payload.to_dict())


class WebhookClientAsync(BaseClient):
    """Async client for the EnergyID Webhooks API."""

    def __init__(
        self, webhook_url: str, session: aiohttp.ClientSession | None = None
    ) -> None:
        self.session = session if session is not None else aiohttp.ClientSession()
        super().__init__(webhook_url=webhook_url, session=self.session)

    @property
    async def policy(self) -> WebhookPolicy:
        """Get the webhook policy."""
        if self._webhook_policy is None:
            self._webhook_policy = await self.get_policy()
        return self._webhook_policy

    async def get_policy(self) -> WebhookPolicy:
        """Get the webhook policy."""
        if not isinstance(self.session, aiohttp.ClientSession):
            raise RuntimeError("Session not initialized")
        async with self.session.get(url=self.webhook_url) as request:
            request.raise_for_status()
            return WebhookPolicy(await request.json())

    async def post(self, data: dict[str, Any]) -> None:
        """Post data to the webhook."""
        if not isinstance(self.session, aiohttp.ClientSession):
            raise RuntimeError("Session not initialized")
        async with self.session.post(url=self.webhook_url, json=data) as request:
            request.raise_for_status()

    async def get_meter_catalog(self) -> MeterCatalog:
        """Get the meter catalog."""
        if not isinstance(self.session, aiohttp.ClientSession):
            raise RuntimeError("Session not initialized")
        async with self.session.get(url=self.meter_catalog_url) as request:
            request.raise_for_status()
            data = await request.json()
            return MeterCatalog(data)

    @property
    async def meter_catalog(self) -> MeterCatalog:
        """Get the meter catalog."""
        if self._meter_catalog is None:
            self._meter_catalog = await self.get_meter_catalog()
        return self._meter_catalog

    async def post_payload(self, payload: WebhookPayload) -> None:
        """Post a webhook payload."""
        await self.post(payload.to_dict())
