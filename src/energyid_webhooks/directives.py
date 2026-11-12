"""Typed models for EnergyID directive resources and schedules."""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
import datetime as dt
import re
from typing import Any

# The largest daylight saving shift in use; larger offset jumps are real gaps.
_CLOCK_CHANGE = dt.timedelta(hours=1)
_NUMBER = r"\d+(?:\.\d+)?"
# Months and years have no fixed length, so they are not accepted as a slot length.
_DURATION = re.compile(
    rf"P(?:(?P<weeks>{_NUMBER})W)?(?:(?P<days>{_NUMBER})D)?"
    rf"(?:T(?=\d)(?:(?P<hours>{_NUMBER})H)?(?:(?P<minutes>{_NUMBER})M)?"
    rf"(?:(?P<seconds>{_NUMBER})S)?)?"
)


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
class DirectiveState:
    """The signal of a directive at one moment and when it changes next."""

    current: DirectiveSignal | None
    next_change: dt.datetime | None
    next_signal: DirectiveSignal | None


@dataclass(frozen=True)
class DirectiveData:
    """A directive schedule returned by EnergyID.

    Each point starts a slot that lasts one interval, or until the next point
    when the interval has no fixed length (the last point then never ends).
    Day and week slots follow the local calendar: when the clocks change, a
    slot still reaches the next point if that point starts at the same local
    time. Moments outside every slot have no signal.
    """

    title: str
    description: str | None
    interval: str
    data: tuple[DirectiveSignal, ...]

    def __post_init__(self) -> None:
        """Keep the points in time order."""
        object.__setattr__(self, "data", tuple(sorted(self.data, key=_point_timestamp)))

    @property
    def slot_length(self) -> dt.timedelta | None:
        """Return the length of a slot, or None when the interval has no fixed length."""
        return _parse_interval(self.interval)[0]

    def signal_at(self, moment: dt.datetime) -> DirectiveSignal | None:
        """Return the point whose slot covers a moment, or None outside every slot."""
        _require_aware(moment)
        return self._signal_at(moment, self._slot_ends())

    def state_at(self, moment: dt.datetime) -> DirectiveState:
        """Return the signal at a moment and the first change of the signal after it.

        A change is the first slot boundary where the signal value differs, so
        slots that repeat the current signal are skipped. The end of the last
        slot is a change to no signal.
        """
        _require_aware(moment)
        ends = self._slot_ends()
        current = self._signal_at(moment, ends)
        boundaries = {point.timestamp for point in self.data}
        boundaries.update(end for end in ends if end is not None)
        for boundary in sorted(
            boundary for boundary in boundaries if boundary > moment
        ):
            signal = self._signal_at(boundary, ends)
            if _signal_value(signal) != _signal_value(current):
                return DirectiveState(current, boundary, signal)
        return DirectiveState(current, None, None)

    def _slot_ends(self) -> list[dt.datetime | None]:
        """Return when the slot of each point ends, or None when it never expires."""
        slot_length, local_days = _parse_interval(self.interval)
        if slot_length is None:
            return [None] * len(self.data)
        ends: list[dt.datetime | None] = []
        for point, following in zip(self.data, (*self.data[1:], None)):
            try:
                end = point.timestamp + slot_length
            except OverflowError:
                ends.append(None)
                continue
            if (
                local_days
                and following is not None
                and _wall_clock(following) - _wall_clock(point) == slot_length
                and following.timestamp - end <= _CLOCK_CHANGE
            ):
                end = max(end, following.timestamp)
            ends.append(end)
        return ends

    def _signal_at(
        self, moment: dt.datetime, ends: list[dt.datetime | None]
    ) -> DirectiveSignal | None:
        index = bisect_right(self.data, moment, key=_point_timestamp)
        if not index:
            return None
        end = ends[index - 1]
        if end is not None and moment >= end:
            return None
        return self.data[index - 1]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DirectiveData:
        """Create directive data from an API response."""
        return cls(
            title=str(data["title"]),
            description=data.get("description"),
            interval=str(data["interval"]),
            data=tuple(DirectiveSignal.from_dict(point) for point in data["data"]),
        )


def _parse_interval(interval: str) -> tuple[dt.timedelta | None, bool]:
    """Return the slot length of an interval and whether it counts whole days or weeks."""
    match = _DURATION.fullmatch(interval)
    if match is None:
        return None, False
    parts = {
        unit: float(amount)
        for unit, amount in match.groupdict().items()
        if amount is not None
    }
    try:
        length = dt.timedelta(**parts)
    except OverflowError:
        return None, False
    if not length:
        return None, False
    return length, parts.keys() <= {"weeks", "days"}


def _point_timestamp(point: DirectiveSignal) -> dt.datetime:
    return point.timestamp


def _wall_clock(point: DirectiveSignal) -> dt.datetime:
    return point.timestamp.replace(tzinfo=None)


def _signal_value(point: DirectiveSignal | None) -> str | None:
    return point.signal if point is not None else None


def _require_aware(moment: dt.datetime) -> None:
    if moment.utcoffset() is None:
        raise ValueError("moment must be timezone-aware")
