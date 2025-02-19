"""Clients for the EnergyID Webhooks API."""

from abc import ABC

import aiohttp
import requests

from .metercatalog import MeterCatalog
from .payload import WebhookPayload
from .webhookpolicy import WebhookPolicy


class BaseClient(ABC):  # pylint: disable=too-few-public-methods
    """Base client for the EnergyID Webhooks API."""

    meter_catalog_url = "https://api.energyid.eu/api/v1/catalogs/meters"

    def __init__(
        self,
        webhook_url: str,
        session: requests.Session | aiohttp.ClientSession | None = None,
    ) -> None:
        self.webhook_url = webhook_url
        self.session = session

        self._meter_catalog = None
        self._webhook_policy = None


class WebhookClient(BaseClient):
    """Client for the EnergyID Webhooks API."""

    def __init__(
        self, webhook_url: str, session: requests.Session | None = None
    ) -> None:
        session = session if session is not None else requests.Session()
        super().__init__(webhook_url=webhook_url, session=session)

    @property
    def policy(self) -> dict:
        """Get the webhook policy."""
        if self._webhook_policy is None:
            self._webhook_policy = self.get_policy()
        return self._webhook_policy

    def get_policy(self) -> WebhookPolicy:
        """Get the webhook policy."""
        request = self.session.get(url=self.webhook_url)
        request.raise_for_status()
        self._webhook_policy = WebhookPolicy(request.json())
        return self._webhook_policy

    def post(self, data: dict) -> None:
        """Post data to the webhook."""
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
        request = self.session.get(url=self.meter_catalog_url)
        request.raise_for_status()
        return MeterCatalog(request.json())

    def post_payload(self, payload: WebhookPayload):
        """Post a webhook payload."""
        self.post(payload.to_dict())


class WebhookClientAsync(BaseClient):
    """Async client for the EnergyID Webhooks API."""

    def __init__(
        self, webhook_url: str, session: aiohttp.ClientSession | None = None
    ) -> None:
        session = session if session is not None else aiohttp.ClientSession()
        super().__init__(webhook_url=webhook_url, session=session)

    @property
    async def policy(self) -> dict:
        """Get the webhook policy."""
        if self._webhook_policy is None:
            self._webhook_policy = await self.get_policy()
        return self._webhook_policy

    async def get_policy(self) -> WebhookPolicy:
        """Get the webhook policy."""
        async with self.session.get(url=self.webhook_url) as request:
            request.raise_for_status()
            self._webhook_policy = WebhookPolicy(await request.json())
            return self._webhook_policy

    async def post(self, data: dict) -> None:
        """Post data to the webhook."""
        async with self.session.post(url=self.webhook_url, json=data) as request:
            request.raise_for_status()
            return

    async def get_meter_catalog(self) -> MeterCatalog:
        """Get the meter catalog."""
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

    async def post_payload(self, payload: WebhookPayload):
        """Post a webhook payload."""
        await self.post(payload.to_dict())
