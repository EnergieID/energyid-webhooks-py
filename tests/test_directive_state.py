"""Tests for reading a directive schedule at a moment."""

import datetime as dt

import pytest

from energyid_webhooks import DirectiveData, DirectiveSignal, DirectiveState

START = dt.datetime(2026, 11, 12, 12, 0, tzinfo=dt.UTC)
SLOT = dt.timedelta(minutes=15)


def _point(slot: int, signal: str) -> DirectiveSignal:
    """Return a point that starts a number of slots after START."""
    return DirectiveSignal(
        timestamp=START + slot * SLOT, signal=signal, color=None, raw_value=None
    )


def _schedule(*points: DirectiveSignal, interval: str = "PT15M") -> DirectiveData:
    return DirectiveData(
        title="Energy planner", description=None, interval=interval, data=points
    )


def test_next_change_skips_slots_with_the_same_signal() -> None:
    """The next change is the first slot whose signal differs."""
    first, second, third = _point(0, "low"), _point(1, "low"), _point(2, "high")
    schedule = _schedule(first, second, third, _point(3, "low"))

    assert schedule.state_at(START + dt.timedelta(minutes=5)) == DirectiveState(
        current=first, next_change=third.timestamp, next_signal=third
    )


def test_a_slot_starts_at_its_timestamp() -> None:
    """At a boundary the slot starting there is active, not the one ending."""
    later = _point(1, "high")
    schedule = _schedule(_point(0, "low"), later)

    assert schedule.signal_at(later.timestamp) == later


def test_before_the_first_slot() -> None:
    """Before the schedule starts there is no signal, and the start is a change."""
    first = _point(0, "low")
    schedule = _schedule(first)

    assert schedule.state_at(START - dt.timedelta(minutes=1)) == DirectiveState(
        current=None, next_change=START, next_signal=first
    )


def test_active_last_slot_reports_its_end() -> None:
    """The end of the last slot is a change to no signal."""
    only = _point(0, "high")
    schedule = _schedule(only)

    assert schedule.state_at(START + dt.timedelta(minutes=5)) == DirectiveState(
        current=only, next_change=START + SLOT, next_signal=None
    )


def test_gap_between_slots_is_a_change() -> None:
    """A gap between two slots with the same signal has no signal."""
    first, last = _point(0, "high"), _point(2, "high")
    schedule = _schedule(first, last)

    state = schedule.state_at(START + dt.timedelta(minutes=5))
    assert state == DirectiveState(
        current=first, next_change=START + SLOT, next_signal=None
    )
    assert state.next_change is not None
    assert schedule.state_at(state.next_change) == DirectiveState(
        current=None, next_change=last.timestamp, next_signal=last
    )


def test_after_the_last_slot() -> None:
    """After the schedule ends there is no signal and no change."""
    schedule = _schedule(_point(0, "high"))

    assert schedule.state_at(START + SLOT) == DirectiveState(None, None, None)


def test_empty_schedule() -> None:
    """A schedule without points has no signal and no change."""
    assert _schedule().state_at(START) == DirectiveState(None, None, None)


def test_interval_without_fixed_length_lasts_until_the_next_point() -> None:
    """A month has no fixed length, so a point lasts until the next one."""
    first, last = _point(0, "low"), _point(4, "high")
    schedule = _schedule(first, last, interval="P1M")

    assert schedule.state_at(START + 3 * SLOT) == DirectiveState(
        current=first, next_change=last.timestamp, next_signal=last
    )
    assert schedule.state_at(START + 100 * SLOT) == DirectiveState(
        current=last, next_change=None, next_signal=None
    )


def test_points_in_another_time_zone() -> None:
    """Points in the record's local time compare by instant with a UTC moment."""
    brussels = dt.timezone(dt.timedelta(hours=1))
    local = DirectiveSignal(
        timestamp=dt.datetime(2026, 11, 12, 13, 0, tzinfo=brussels),
        signal="high",
        color=None,
        raw_value=None,
    )
    schedule = _schedule(local)

    assert schedule.signal_at(START) == local
    assert schedule.state_at(START).next_change == START + SLOT


def test_points_with_different_offsets() -> None:
    """Points with different UTC offsets are ordered and compared by instant."""
    first = _point(0, "low")
    second = DirectiveSignal(
        timestamp=dt.datetime(
            2026, 11, 12, 13, 15, tzinfo=dt.timezone(dt.timedelta(hours=1))
        ),
        signal="high",
        color=None,
        raw_value=None,
    )
    schedule = _schedule(second, first)

    assert schedule.state_at(START + dt.timedelta(minutes=5)) == DirectiveState(
        current=first, next_change=START + SLOT, next_signal=second
    )


def test_overlapping_slots_end_at_the_next_point() -> None:
    """When slots overlap, the later point takes over and runs its full slot."""
    first, second = _point(0, "low"), _point(1, "high")
    schedule = _schedule(first, second, interval="PT1H")

    assert schedule.state_at(START + dt.timedelta(minutes=5)) == DirectiveState(
        current=first, next_change=second.timestamp, next_signal=second
    )
    assert schedule.state_at(START + dt.timedelta(minutes=20)) == DirectiveState(
        current=second,
        next_change=second.timestamp + dt.timedelta(hours=1),
        next_signal=None,
    )


def _local(
    year: int, month: int, day: int, hour: int, offset: int, signal: str
) -> DirectiveSignal:
    """Return a point at a local time with a UTC offset in hours."""
    return DirectiveSignal(
        timestamp=dt.datetime(
            year, month, day, hour, tzinfo=dt.timezone(dt.timedelta(hours=offset))
        ),
        signal=signal,
        color=None,
        raw_value=None,
    )


def test_day_slot_reaches_the_next_local_midnight_when_clocks_go_back() -> None:
    """The 25-hour day when clocks go back has no gap before the next day."""
    first = _local(2026, 10, 24, 0, 2, "high")
    long_day = _local(2026, 10, 25, 0, 2, "high")
    last = _local(2026, 10, 26, 0, 1, "high")
    schedule = _schedule(first, long_day, last, interval="P1D")

    assert schedule.signal_at(_local(2026, 10, 25, 23, 1, "").timestamp) == long_day
    assert schedule.state_at(
        dt.datetime(2026, 10, 25, 12, tzinfo=dt.UTC)
    ) == DirectiveState(
        current=long_day,
        next_change=dt.datetime(2026, 10, 26, 23, tzinfo=dt.UTC),
        next_signal=None,
    )


def test_day_slot_ends_at_the_next_local_midnight_when_clocks_go_forward() -> None:
    """The 23-hour day when clocks go forward hands over at local midnight."""
    first = _local(2026, 3, 28, 0, 1, "low")
    short_day = _local(2026, 3, 29, 0, 1, "high")
    last = _local(2026, 3, 30, 0, 2, "low")
    schedule = _schedule(first, short_day, last, interval="P1D")

    assert schedule.state_at(
        dt.datetime(2026, 3, 29, 12, tzinfo=dt.UTC)
    ) == DirectiveState(current=short_day, next_change=last.timestamp, next_signal=last)


def test_week_slot_follows_the_local_calendar() -> None:
    """A week slot spanning the change of UTC offset reaches the next week."""
    first = _local(2026, 10, 19, 0, 2, "low")
    last = _local(2026, 10, 26, 0, 1, "high")
    schedule = _schedule(first, last, interval="P7D")

    assert schedule.state_at(
        dt.datetime(2026, 10, 25, 12, tzinfo=dt.UTC)
    ) == DirectiveState(current=first, next_change=last.timestamp, next_signal=last)


def test_day_slot_does_not_bridge_more_than_a_clock_change() -> None:
    """An offset jump larger than a clock change leaves the gap in place."""
    first = _local(2026, 11, 12, 0, 5, "high")
    last = _local(2026, 11, 13, 0, -5, "high")
    schedule = _schedule(first, last, interval="P1D")

    assert schedule.signal_at(dt.datetime(2026, 11, 12, 20, tzinfo=dt.UTC)) is None


def test_far_future_point_never_ends() -> None:
    """A slot that would end past the last representable date never ends."""
    first = _point(0, "low")
    far = DirectiveSignal(
        timestamp=dt.datetime(9999, 12, 31, 12, tzinfo=dt.UTC),
        signal="high",
        color=None,
        raw_value=None,
    )
    schedule = _schedule(first, far, interval="P1D")

    assert schedule.signal_at(START + dt.timedelta(hours=1)) == first
    assert schedule.state_at(START + dt.timedelta(hours=1)) == DirectiveState(
        current=first, next_change=START + dt.timedelta(days=1), next_signal=None
    )
    assert schedule.signal_at(far.timestamp + dt.timedelta(hours=1)) == far


def test_hour_slot_does_not_follow_the_local_calendar() -> None:
    """Shorter slots are exact durations, so a missing hour stays a gap."""
    before = _local(2026, 10, 25, 1, 2, "high")
    after = _local(2026, 10, 25, 2, 1, "high")
    schedule = _schedule(before, after, interval="PT1H")

    assert schedule.signal_at(dt.datetime(2026, 10, 25, 0, 30, tzinfo=dt.UTC)) is None


def test_points_are_kept_in_time_order() -> None:
    """Points are sorted whether they come from the API or the constructor."""
    first, second = _point(0, "low"), _point(1, "high")

    assert _schedule(second, first).data == (first, second)

    parsed = DirectiveData.from_dict(
        {
            "title": "Energy planner",
            "interval": "PT15M",
            "data": [
                {"timestamp": "2026-11-12T12:15:00Z", "signal": "high"},
                {"timestamp": "2026-11-12T12:00:00Z", "signal": "low"},
            ],
        }
    )
    assert [point.signal for point in parsed.data] == ["low", "high"]
    assert parsed.signal_at(START + dt.timedelta(minutes=20)) == parsed.data[1]


@pytest.mark.parametrize(
    ("interval", "expected"),
    [
        ("PT5M", dt.timedelta(minutes=5)),
        ("PT15M", dt.timedelta(minutes=15)),
        ("PT1H", dt.timedelta(hours=1)),
        ("PT1H30M", dt.timedelta(hours=1, minutes=30)),
        ("PT1.5S", dt.timedelta(seconds=1.5)),
        ("PT0.25H", dt.timedelta(minutes=15)),
        ("P1D", dt.timedelta(days=1)),
        ("P14D", dt.timedelta(days=14)),
        ("P1W", dt.timedelta(weeks=1)),
        ("P1DT12H", dt.timedelta(days=1, hours=12)),
        ("P1M", None),
        ("P1Y", None),
        ("PT0M", None),
        ("P", None),
        ("PT", None),
        ("pt15m", None),
        ("PT15M ", None),
        ("P1000000000D", None),
        ("", None),
        ("15 minutes", None),
    ],
)
def test_slot_length(interval: str, expected: dt.timedelta | None) -> None:
    """Only ISO 8601 durations with a fixed, non-zero length give a slot length."""
    assert _schedule(interval=interval).slot_length == expected


def test_naive_moment_is_rejected() -> None:
    """A moment without a time zone cannot be placed on the schedule."""
    schedule = _schedule(_point(0, "low"))
    naive = dt.datetime(2026, 11, 12, 12, 5)

    with pytest.raises(ValueError, match="timezone-aware"):
        schedule.signal_at(naive)
    with pytest.raises(ValueError, match="timezone-aware"):
        schedule.state_at(naive)
