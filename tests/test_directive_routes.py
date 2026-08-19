"""Tests for the directive route selection in WebhookClient."""

from unittest.mock import MagicMock

import aiohttp
import pytest

from energyid_webhooks.client_v2 import WebhookClient


def _not_found() -> aiohttp.ClientResponseError:
    return aiohttp.ClientResponseError(
        request_info=MagicMock(), history=(), status=404, message="Not Found"
    )


def _client_with_routes(routes: dict[str, object]) -> tuple[WebhookClient, list[str]]:
    """Return a client whose API layer serves the given path->payload map."""
    client = WebhookClient.__new__(WebhookClient)
    client._directives_use_legacy_routes = None
    calls: list[str] = []

    async def fake_get(path: str, **kwargs: object) -> object:
        calls.append(path)
        if path not in routes:
            raise _not_found()
        return routes[path]

    client._get_device_api_json = fake_get  # type: ignore[method-assign]
    return client, calls


@pytest.mark.asyncio
async def test_token_scoped_route_preferred() -> None:
    """The recordless route is used and pinned when the backend serves it."""
    client, calls = _client_with_routes({"directives": []})

    assert (
        await client._get_directive_json("directives", "records/EA-1/directives") == []
    )
    assert client._directives_use_legacy_routes is False

    await client._get_directive_json("directives", "records/EA-1/directives")
    assert calls == ["directives", "directives"]


@pytest.mark.asyncio
async def test_fallback_to_legacy_route() -> None:
    """A 404 on the recordless route falls back to the legacy route and pins it."""
    client, calls = _client_with_routes({"records/EA-1/directives": ["legacy"]})

    assert await client._get_directive_json(
        "directives", "records/EA-1/directives"
    ) == ["legacy"]
    assert client._directives_use_legacy_routes is True

    await client._get_directive_json("directives", "records/EA-1/directives")
    assert calls == [
        "directives",
        "records/EA-1/directives",
        "records/EA-1/directives",
    ]


@pytest.mark.asyncio
async def test_non_routing_errors_propagate() -> None:
    """Errors other than a missing route are not masked by the fallback."""
    client = WebhookClient.__new__(WebhookClient)
    client._directives_use_legacy_routes = None

    async def fake_get(path: str, **kwargs: object) -> object:
        raise aiohttp.ClientResponseError(
            request_info=MagicMock(), history=(), status=500, message="boom"
        )

    client._get_device_api_json = fake_get  # type: ignore[method-assign]

    with pytest.raises(aiohttp.ClientResponseError):
        await client._get_directive_json("directives", "records/EA-1/directives")
    assert client._directives_use_legacy_routes is None
