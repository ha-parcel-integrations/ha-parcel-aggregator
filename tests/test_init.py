"""Tests for the Parcel Aggregator setup/unload entry points."""
import pytest

from homeassistant.config_entries import ConfigEntryState

from custom_components.parcel_aggregator.const import DOMAIN
from custom_components.parcel_aggregator.coordinator import ParcelAggregatorCoordinator


def _add_entry(hass):
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data={})
    entry.add_to_hass(hass)
    return entry


@pytest.mark.asyncio
async def test_setup_entry_succeeds_with_no_sources(hass):
    """A fresh HA instance with no source carriers still sets up cleanly."""
    entry = _add_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert isinstance(entry.runtime_data, ParcelAggregatorCoordinator)


@pytest.mark.asyncio
async def test_unload_entry_calls_shutdown(hass):
    """Unloading the entry calls coordinator.async_shutdown."""
    entry = _add_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = entry.runtime_data

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.NOT_LOADED
    # async_shutdown clears the source-state listener; verifiable by absence
    # of an unsub reference (set to None on shutdown).
    assert coordinator._unsub_listener is None
