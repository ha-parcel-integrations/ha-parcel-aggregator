"""Diagnostics support for the Parcel Aggregator integration."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import ParcelAggregatorConfigEntry

# Per-parcel keys that may contain PII from the upstream carrier integrations.
# Counts (total / by_carrier) are kept untouched — they are not personal data.
TO_REDACT = {
    "barcode",
    "sender",
    "pickup_point",
    "url",
    "raw",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ParcelAggregatorConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a Parcel Aggregator config entry."""
    coordinator = entry.runtime_data
    data = coordinator.data or {}
    return {
        "watched_source_count": sum(
            len(bucket) for bucket in coordinator._sources.values()
        ),
        "sources_by_bucket": {
            bucket: list(entities.keys())
            for bucket, entities in coordinator._sources.items()
        },
        "data": async_redact_data(data, TO_REDACT),
    }
