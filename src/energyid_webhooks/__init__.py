"""EnergyID Webhooks API Client."""

from importlib.metadata import PackageNotFoundError, version

from .client import (
    WebhookClient as WebhookClientV1,
    WebhookClientAsync as WebhookClientAsyncV1,
)
from .client_v2 import Sensor, WebhookClient
from .directives import (
    DirectiveData,
    DirectiveResource,
    DirectiveSignal,
    SignalProvider,
)
from .payload import WebhookPayload

try:
    __version__ = version("energyid-webhooks")
except PackageNotFoundError:
    pass  # package is not installed

# Export both, but encourage V2 usage
__all__ = [
    "DirectiveData",
    "DirectiveResource",
    "DirectiveSignal",
    "Sensor",  # V2 sensor class
    "SignalProvider",
    "WebhookClient",  # V2 client is the default
    "WebhookClientAsyncV1",  # V1 async client with clear name
    "WebhookClientV1",  # V1 client with clear name
    "WebhookPayload",  # Used with V1
]
