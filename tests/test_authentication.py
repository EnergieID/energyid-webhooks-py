"""Tests for how WebhookClient reports refused provisioning credentials."""

import asyncio
import datetime as dt
from unittest.mock import MagicMock

import aiohttp
import pytest

from energyid_webhooks import EnergyIDAuthenticationError, WebhookClient


class _FakeResponse:
    def __init__(self, status: int, payload: object = None) -> None:
        self.status = status
        self.reason = "Reason"
        self.request_info = MagicMock()
        self.history = ()
        self.headers: dict[str, str] = {}
        self._payload = payload

    async def __aenter__(self) -> "_FakeResponse":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    def raise_for_status(self) -> None:
        if self.status >= 400:
            raise aiohttp.ClientResponseError(
                self.request_info, self.history, status=self.status
            )

    async def json(self) -> object:
        return self._payload


def _make_client(hello_status: int) -> tuple[WebhookClient, list[str]]:
    """Return a client whose /hello answers with a status, and the URLs it posts to."""
    client = WebhookClient(
        provisioning_key="key",
        provisioning_secret="secret",
        device_id="device",
        device_name="name",
        session=MagicMock(),
    )
    posts: list[str] = []

    def fake_post(url: str, **kwargs: object) -> _FakeResponse:
        posts.append(url)
        return _FakeResponse(hello_status)

    client.session.post = fake_post  # type: ignore[assignment]
    return client, posts


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403])
async def test_refused_credentials_raise_authentication_error(status: int) -> None:
    """A 401 or 403 from /hello is an authentication error with its status."""
    client, _ = _make_client(status)

    with pytest.raises(EnergyIDAuthenticationError) as err:
        await client.authenticate()

    assert err.value.status == status
    # Callers that catch ClientResponseError keep working.
    assert isinstance(err.value, aiohttp.ClientResponseError)


@pytest.mark.asyncio
async def test_server_error_is_not_an_authentication_error() -> None:
    """Other HTTP errors from /hello stay plain response errors."""
    client, _ = _make_client(500)

    with pytest.raises(aiohttp.ClientResponseError) as err:
        await client.authenticate()

    assert not isinstance(err.value, EnergyIDAuthenticationError)
    assert err.value.status == 500


@pytest.mark.asyncio
async def test_refused_reauthentication_after_unauthorized_directive_request() -> None:
    """A rejected token that cannot be renewed surfaces as an authentication error."""
    client, posts = _make_client(401)
    client.is_claimed = True
    client.recordNumber = "EA-1"
    client.api_access_token = "expired"
    client.auth_valid_until = dt.datetime.now(dt.UTC) + dt.timedelta(hours=24)
    client.session.get = lambda url, **kwargs: _FakeResponse(401)  # type: ignore[assignment]

    with pytest.raises(EnergyIDAuthenticationError):
        await client.get_directive_data("directive")

    assert posts == [client.hello_url]


@pytest.mark.asyncio
async def test_refused_credentials_when_listing_directives_without_a_token() -> None:
    """Listing directives signs in first, which can be refused."""
    client, posts = _make_client(401)

    with pytest.raises(EnergyIDAuthenticationError):
        await client.get_directives()

    assert posts == [client.hello_url]


@pytest.mark.asyncio
async def test_refused_credentials_when_renewing_an_expiring_token() -> None:
    """Renewing a token that is about to expire can be refused."""
    client, posts = _make_client(403)
    client.is_claimed = True
    client.recordNumber = "EA-1"
    client.api_access_token = "token"
    client.auth_valid_until = dt.datetime.now(dt.UTC) + dt.timedelta(hours=1)

    with pytest.raises(EnergyIDAuthenticationError):
        await client.get_directive_data("directive")

    assert posts == [client.hello_url]


@pytest.mark.asyncio
async def test_upload_does_not_retry_refused_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Retrying cannot fix refused credentials, so the upload gives up at once."""
    monkeypatch.setattr(asyncio, "sleep", _no_sleep)
    client, posts = _make_client(401)

    with pytest.raises(EnergyIDAuthenticationError):
        await client.send_data({"el": 1.0})

    assert posts == [client.hello_url]


@pytest.mark.asyncio
async def test_upload_retries_other_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Other errors while signing in are still retried."""
    monkeypatch.setattr(asyncio, "sleep", _no_sleep)
    client, posts = _make_client(500)

    with pytest.raises(aiohttp.ClientResponseError):
        await client.send_data({"el": 1.0})

    assert len(posts) == 3


async def _no_sleep(_seconds: float) -> None:
    return None
