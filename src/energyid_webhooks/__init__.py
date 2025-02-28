"""EnergyID Webhooks API Client."""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("energyid-webhooks")
except PackageNotFoundError:
    pass  # package is not installed

# V1 clients (legacy)
from .client import WebhookClient as WebhookClientV1
from .client import WebhookClientAsync as WebhookClientAsyncV1
from .payload import WebhookPayload

# V2 client (new)
from .client_v2 import WebhookClient, Sensor

# Export both, but encourage V2 usage
__all__ = [
    "WebhookClient",  # V2 client is the default
    "Sensor",  # V2 sensor class
    "WebhookClientV1",  # V1 client with clear name
    "WebhookClientAsyncV1",  # V1 async client with clear name
    "WebhookPayload",  # Used with V1
]
