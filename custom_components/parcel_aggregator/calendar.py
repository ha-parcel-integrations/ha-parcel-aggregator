"""Calendar platform for the Parcel Aggregator integration."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import ParcelAggregatorConfigEntry
from .const import DOMAIN
from .coordinator import ParcelAggregatorCoordinator

# The coordinator drives updates via source state-change events.
PARALLEL_UPDATES = 0

# Fallback window length for a parcel that has a start moment but no end.
_DEFAULT_EVENT_DURATION = timedelta(hours=1)
_END_OF_DAY = time(23, 59, 59)


def _whole_days(start: datetime, end: datetime) -> tuple[date, date] | None:
    """Return the days a 00:00:00 to 23:59:59 window spans, else ``None``.

    Checked in the window's own offset first, so a carrier's local or naive
    wall clock counts, then in Home Assistant's zone for a window sent in UTC.
    The end date is exclusive, as Home Assistant expects for all-day events.
    """
    for first, last in ((start, end), (dt_util.as_local(start), dt_util.as_local(end))):
        if (
            first.time().replace(tzinfo=None) == time.min
            and last.time().replace(tzinfo=None, microsecond=0) == _END_OF_DAY
            and last.date() >= first.date()
        ):
            return first.date(), last.date() + timedelta(days=1)
    return None


def _build_device_info() -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, "aggregator")},
        name="Parcel Aggregator",
        manufacturer="Community",
        entry_type=DeviceEntryType.SERVICE,
    )


def _parse(value: str | None) -> datetime | None:
    """Parse an ISO 8601 string into a timezone-aware datetime, or ``None``."""
    if not value:
        return None
    parsed = dt_util.parse_datetime(value)
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt_util.UTC)
    return parsed


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ParcelAggregatorConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the combined deliveries calendar from a config entry."""
    async_add_entities([ParcelAggregatorCalendar(entry.runtime_data)])


class ParcelAggregatorCalendar(
    CoordinatorEntity[ParcelAggregatorCoordinator], CalendarEntity
):
    """A combined calendar of expected deliveries across every installed carrier.

    Reads the merged incoming-parcel list the coordinator already builds, so
    one agenda shows DHL, DPD and PostNL deliveries together. Read-only and
    free (no own polling); enabled by default, can be turned off per entity.
    Each event's summary is prefixed with the carrier so they stay
    distinguishable in a single calendar.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "deliveries"

    def __init__(self, coordinator: ParcelAggregatorCoordinator) -> None:
        """Initialise the combined deliveries calendar."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_deliveries"
        self._attr_device_info = _build_device_info()

    def _events(self) -> list[CalendarEvent]:
        """Build calendar events from every carrier's active incoming parcels."""
        info = (self.coordinator.data or {}).get("incoming") or {}
        events: list[CalendarEvent] = []
        for parcel in info.get("parcels", []):
            start = _parse(parcel.get("planned_from"))
            if start is None:
                continue
            end = _parse(parcel.get("planned_to"))
            if end is None or end <= start:
                end = start + _DEFAULT_EVENT_DURATION
            event_start: datetime | date = start
            event_end: datetime | date = end
            if days := _whole_days(start, end):
                event_start, event_end = days

            carrier = parcel.get("carrier") or "Parcel"
            barcode = parcel.get("barcode") or ""
            sender = parcel.get("sender")
            label = sender or (f"Parcel {barcode}" if barcode else "parcel")
            summary = f"{carrier}: {label}"
            description_parts = [
                f"Carrier: {carrier}",
                f"Barcode: {barcode}" if barcode else None,
                f"Status: {parcel.get('status')}" if parcel.get("status") else None,
                parcel.get("url"),
            ]
            description = "\n".join(p for p in description_parts if p)
            location = parcel.get("pickup_point") if parcel.get("pickup") else None
            uid = f"{carrier}_{barcode}" if barcode else None

            events.append(
                CalendarEvent(
                    start=event_start,
                    end=event_end,
                    summary=summary,
                    description=description or None,
                    location=location,
                    uid=uid,
                )
            )
        return events

    @property
    def event(self) -> CalendarEvent | None:
        """Return the current or next upcoming delivery event."""
        now = dt_util.now()
        upcoming = [event for event in self._events() if event.end_datetime_local > now]
        return (
            min(upcoming, key=lambda event: event.start_datetime_local)
            if upcoming
            else None
        )

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Return all delivery events that overlap the requested range."""
        return [
            event
            for event in self._events()
            if event.start_datetime_local < end_date
            and event.end_datetime_local > start_date
        ]
