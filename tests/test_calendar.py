"""Tests for the Parcel Aggregator combined deliveries calendar."""

from datetime import UTC, date, datetime
from unittest.mock import MagicMock

from custom_components.parcel_aggregator.calendar import ParcelAggregatorCalendar


def _make_coordinator(parcels: list[dict]) -> MagicMock:
    coordinator = MagicMock()
    coordinator.data = {"incoming": {"parcels": parcels}}
    return coordinator


def _parcel(
    carrier: str,
    barcode: str,
    planned_from: str | None = None,
    planned_to: str | None = None,
    pickup: bool = False,
    pickup_point: str | None = None,
) -> dict:
    return {
        "carrier": carrier,
        "barcode": barcode,
        "sender": "Example Sender",
        "status": "out_for_delivery",
        "planned_from": planned_from,
        "planned_to": planned_to,
        "pickup": pickup,
        "pickup_point": pickup_point,
        "url": "https://track/123",
    }


def _calendar(parcels: list[dict]) -> ParcelAggregatorCalendar:
    return ParcelAggregatorCalendar(_make_coordinator(parcels))


def test_event_returns_earliest_and_prefixes_carrier():
    cal = _calendar(
        [
            _parcel("DPD", "LATE", planned_from="2099-01-02T10:00:00Z"),
            _parcel("DHL", "SOON", planned_from="2099-01-01T10:00:00Z"),
        ]
    )
    event = cal.event
    assert event is not None
    assert event.uid == "DHL_SOON"
    assert event.summary == "DHL: Example Sender"


def test_event_none_when_no_planned_parcels():
    cal = _calendar([_parcel("DHL", "NOPLAN")])
    assert cal.event is None


def test_moment_gets_one_hour_duration():
    cal = _calendar([_parcel("DHL", "A", planned_from="2099-01-01T10:00:00Z")])
    events = cal._events()
    assert len(events) == 1
    assert events[0].end == datetime(2099, 1, 1, 11, 0, tzinfo=UTC)


def test_interval_uses_window():
    cal = _calendar(
        [
            _parcel(
                "DHL",
                "A",
                planned_from="2099-01-01T10:00:00Z",
                planned_to="2099-01-01T12:00:00Z",
            )
        ]
    )
    assert cal._events()[0].end == datetime(2099, 1, 1, 12, 0, tzinfo=UTC)


def test_pickup_parcel_sets_location():
    cal = _calendar(
        [
            _parcel(
                "PostNL",
                "A",
                planned_from="2099-01-01T10:00:00Z",
                pickup=True,
                pickup_point="PostNL Punt",
            )
        ]
    )
    assert cal._events()[0].location == "PostNL Punt"


def test_events_merge_multiple_carriers():
    cal = _calendar(
        [
            _parcel("DHL", "A", planned_from="2099-01-01T10:00:00Z"),
            _parcel("DPD", "B", planned_from="2099-01-03T10:00:00Z"),
            _parcel("PostNL", "C", planned_from="2099-01-02T10:00:00Z"),
        ]
    )
    assert {e.uid for e in cal._events()} == {"DHL_A", "DPD_B", "PostNL_C"}


async def test_get_events_filters_by_range():
    cal = _calendar(
        [
            _parcel("DHL", "PAST", planned_from="2000-01-01T10:00:00Z"),
            _parcel("DPD", "FUTURE", planned_from="2099-01-01T10:00:00Z"),
        ]
    )
    start = datetime(2098, 1, 1, tzinfo=UTC)
    end = datetime(2100, 1, 1, tzinfo=UTC)
    events = await cal.async_get_events(MagicMock(), start, end)
    assert {e.uid for e in events} == {"DPD_FUTURE"}


def test_whole_day_window_is_an_all_day_event():
    event = _calendar(
        [
            _parcel(
                "DHL",
                "A",
                planned_from="2099-01-01T00:00:00+01:00",
                planned_to="2099-01-01T23:59:59+01:00",
            )
        ]
    )._events()[0]
    assert (event.start, event.end) == (date(2099, 1, 1), date(2099, 1, 2))
    assert event.all_day


def test_window_over_whole_days_is_one_all_day_event():
    event = _calendar(
        [
            _parcel(
                "DHL",
                "A",
                planned_from="2099-01-01T00:00:00",
                planned_to="2099-01-03T23:59:59",
            )
        ]
    )._events()[0]
    assert (event.start, event.end) == (date(2099, 1, 1), date(2099, 1, 4))


async def test_whole_day_window_sent_in_utc_is_all_day_in_local_time(hass):
    await hass.config.async_set_time_zone("Europe/Amsterdam")
    event = _calendar(
        [
            _parcel(
                "DHL",
                "A",
                planned_from="2099-01-01T23:00:00Z",
                planned_to="2099-01-02T22:59:59Z",
            )
        ]
    )._events()[0]
    assert (event.start, event.end) == (date(2099, 1, 2), date(2099, 1, 3))


def test_a_moment_stretched_to_the_end_of_its_day_stays_timed():
    event = _calendar(
        [
            _parcel(
                "DHL",
                "A",
                planned_from="2099-01-01T14:00:00+01:00",
                planned_to="2099-01-01T23:59:59+01:00",
            )
        ]
    )._events()[0]
    assert not event.all_day


async def test_all_day_events_are_upcoming_and_filtered_by_range():
    cal = _calendar(
        [
            _parcel(
                "DHL",
                "PAST",
                planned_from="2000-01-01T00:00:00",
                planned_to="2000-01-01T23:59:59",
            ),
            _parcel(
                "DHL",
                "FUTURE",
                planned_from="2099-01-01T00:00:00",
                planned_to="2099-01-01T23:59:59",
            ),
        ]
    )
    assert cal.event.uid == "DHL_FUTURE"
    events = await cal.async_get_events(
        MagicMock(), datetime(2098, 1, 1, tzinfo=UTC), datetime(2100, 1, 1, tzinfo=UTC)
    )
    assert {e.uid for e in events} == {"DHL_FUTURE"}


def _summary(**overrides) -> str:
    parcel = _parcel("DHL", "B1", planned_from="2099-01-01T10:00:00Z")
    parcel.update(overrides)
    (event,) = _calendar([parcel])._events()
    return event.summary


def test_summary_prefers_contents_over_sender():
    assert _summary(contents="Blue Mug; Tea Towel") == "DHL: Blue Mug; Tea Towel"


def test_summary_uses_sender_without_contents():
    assert _summary(contents=None) == "DHL: Example Sender"


def test_summary_falls_back_to_barcode_without_contents_or_sender():
    assert _summary(contents=None, sender=None) == "DHL: Parcel B1"


def test_summary_works_when_contents_key_is_missing():
    parcel = _parcel("DHL", "B1", planned_from="2099-01-01T10:00:00Z")
    assert "contents" not in parcel
    (event,) = _calendar([parcel])._events()
    assert event.summary == "DHL: Example Sender"
