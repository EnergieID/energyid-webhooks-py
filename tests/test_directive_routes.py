"""Tests for the token-scoped directive routes in WebhookClient."""

from unittest.mock import MagicMock

import aiohttp
import pytest

from energyid_webhooks.client_v2 import WebhookClient


def _make_client(**kwargs: object) -> WebhookClient:
    return WebhookClient(
        provisioning_key="key",
        provisioning_secret="secret",
        device_id="device",
        device_name="name",
        session=MagicMock(),
        **kwargs,  # type: ignore[arg-type]
    )


def test_hooks_base_url_defaults_to_production_host() -> None:
    """The directive base is the production Hooks host by default."""
    client = _make_client()
    assert client.hooks_base_url == "https://hooks.energyid.eu"


def test_hooks_base_url_follows_hello_override() -> None:
    """Overriding hello_url moves the directive routes to the same host."""
    client = _make_client(hello_url="https://example.test/prefix/hello")
    assert client.hooks_base_url == "https://example.test/prefix"


class _FakeResponse:
    def __init__(self, status: int, payload: object) -> None:
        self.status = status
        self._payload = payload

    async def __aenter__(self) -> "_FakeResponse":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    def raise_for_status(self) -> None:
        if self.status >= 400:
            raise aiohttp.ClientResponseError(
                request_info=MagicMock(), history=(), status=self.status
            )

    async def json(self) -> object:
        return self._payload


@pytest.mark.asyncio
async def test_device_api_json_uses_hooks_host() -> None:
    """Directive fetches go to the Hooks host, not the record-scoped API."""
    client = _make_client()
    client.api_access_token = "token"
    urls: list[str] = []

    def fake_get(url: str, **kwargs: object) -> _FakeResponse:
        urls.append(url)
        return _FakeResponse(200, [])

    client.session.get = fake_get  # type: ignore[assignment]

    assert await client._get_device_api_json("directives") == []
    assert urls == ["https://hooks.energyid.eu/directives"]


@pytest.mark.asyncio
async def test_missing_route_is_not_masked() -> None:
    """A 404 propagates; there is no legacy-route fallback anymore."""
    client = _make_client()
    client.api_access_token = "token"

    def fake_get(url: str, **kwargs: object) -> _FakeResponse:
        return _FakeResponse(404, None)

    client.session.get = fake_get  # type: ignore[assignment]

    with pytest.raises(aiohttp.ClientResponseError):
        await client._get_device_api_json("directives")
