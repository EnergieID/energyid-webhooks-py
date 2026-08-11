"""Typed models for EnergyID directive resources and schedules."""

from __future__ import annotations

from dataclasses import dataclass
import datetime as dt
from typing import Any


@dataclass(frozen=True)
class SignalProvider:
    """Provider metadata for a directive."""

    id: str
    display_name: str
    logo_url: str | None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SignalProvider:
        """Create provider metadata from an API response."""
        return cls(
            id=str(data["id"]),
            display_name=str(data["displayName"]),
            logo_url=data.get("logoUrl"),
        )


@dataclass(frozen=True)
class DirectiveResource:
    """An available directive."""

    id: str
    title: str
    description: str | None
    properties: tuple[str, ...]
    signal_provider: SignalProvider

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DirectiveResource:
        """Create a directive resource from an API response."""
        return cls(
            id=str(data["id"]),
            title=str(data["title"]),
            description=data.get("description"),
            properties=tuple(data.get("properties", ())),
            signal_provider=SignalProvider.from_dict(data["signalProvider"]),
        )


@dataclass(frozen=True)
class DirectiveSignal:
    """One timestamped directive value."""

    timestamp: dt.datetime
    signal: str
    color: str | None
    raw_value: float | None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DirectiveSignal:
        """Create a signal point from an API response."""
        timestamp = str(data["timestamp"])
        if timestamp.endswith("Z"):
            timestamp = f"{timestamp[:-1]}+00:00"
        return cls(
            timestamp=dt.datetime.fromisoformat(timestamp),
            signal=str(data["signal"]),
            color=data.get("color"),
            raw_value=data.get("rawValue"),
        )


@dataclass(frozen=True)
class DirectiveData:
    """A directive schedule returned by EnergyID."""

    title: str
    description: str | None
    interval: str
    data: tuple[DirectiveSignal, ...]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DirectiveData:
        """Create directive data from an API response."""
        return cls(
            title=str(data["title"]),
            description=data.get("description"),
            interval=str(data["interval"]),
            data=tuple(DirectiveSignal.from_dict(point) for point in data["data"]),
        )
