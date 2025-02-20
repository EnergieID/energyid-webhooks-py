"""EnergyID Webhooks API Client."""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("energyid-webhooks")
except PackageNotFoundError:
    pass  # package is not installed

from .client import WebhookClient, WebhookClientAsync

__all__ = ["WebhookClient", "WebhookClientAsync", "WebhookPayload"]
from .payload import WebhookPayload
