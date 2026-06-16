"""Parcel Aggregator custom component for Home Assistant."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import PLATFORMS
from .coordinator import ParcelAggregatorCoordinator

type ParcelAggregatorConfigEntry = ConfigEntry[ParcelAggregatorCoordinator]

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ParcelAggregatorConfigEntry
) -> bool:
    """Set up the Parcel Aggregator from a config entry."""
    coordinator = ParcelAggregatorCoordinator(hass, entry)
    await coordinator.async_setup()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: ParcelAggregatorConfigEntry
) -> bool:
    """Unload a Parcel Aggregator config entry."""
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.async_shutdown()
        return True
    return False
