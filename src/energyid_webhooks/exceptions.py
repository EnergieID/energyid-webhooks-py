"""Exceptions raised by the EnergyID webhook clients."""

from __future__ import annotations

from aiohttp import ClientResponseError


class EnergyIDAuthenticationError(ClientResponseError):
    """EnergyID refused to sign the device in with its provisioning credentials.

    Raised for a 401 (invalid provisioning key or secret) or a 403 (the record
    the device is linked to is closed) from the provisioning endpoint.
    """
