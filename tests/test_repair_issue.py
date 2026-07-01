"""Tests for the no-source-carriers repair issue."""
import pytest

from homeassistant.helpers import issue_registry as ir

from custom_components.parcel_aggregator.const import DOMAIN
from custom_components.parcel_aggregator.coordinator import NO_SOURCES_ISSUE_ID


def _add_entry(hass):
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data={})
    entry.add_to_hass(hass)
    return entry


@pytest.mark.asyncio
async def test_no_sources_issue_created_when_no_carriers_installed(hass):
    """With no source carrier entities, a warning repair issue is registered."""
    entry = _add_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = ir.async_get(hass)
    issue = registry.async_get_issue(DOMAIN, NO_SOURCES_ISSUE_ID)
    assert issue is not None
    assert issue.severity is ir.IssueSeverity.WARNING
    assert "DHL" in issue.translation_placeholders["carriers"]


@pytest.mark.asyncio
async def test_no_sources_issue_cleared_when_carrier_appears(hass):
    """Reloading after a carrier sensor is registered clears the repair issue."""
    from homeassistant.helpers import entity_registry as er
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    # First setup creates the issue (no source carrier yet)
    entry = _add_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = ir.async_get(hass)
    assert registry.async_get_issue(DOMAIN, NO_SOURCES_ISSUE_ID) is not None

    # Register a dummy DHL source entity into a placeholder config entry
    dhl_entry = MockConfigEntry(domain="dhl_nl", unique_id="dhl-account")
    dhl_entry.add_to_hass(hass)
    er.async_get(hass).async_get_or_create(
        domain="sensor",
        platform="dhl_nl",
        unique_id="dhl-account_incoming_parcels",
        config_entry=dhl_entry,
    )

    # Reload aggregator: discovery should now find the source and clear the issue
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert registry.async_get_issue(DOMAIN, NO_SOURCES_ISSUE_ID) is None


@pytest.mark.asyncio
async def test_no_sources_issue_cleared_without_reload_when_carrier_appears(hass):
    """Registering a carrier source sensor after setup clears the issue live —
    no manual reload of the aggregator needed."""
    from homeassistant.helpers import entity_registry as er
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = _add_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = ir.async_get(hass)
    assert registry.async_get_issue(DOMAIN, NO_SOURCES_ISSUE_ID) is not None

    gls_entry = MockConfigEntry(domain="gls", unique_id="gls")
    gls_entry.add_to_hass(hass)
    er.async_get(hass).async_get_or_create(
        domain="sensor",
        platform="gls",
        unique_id=f"{gls_entry.entry_id}_incoming_parcels",
        config_entry=gls_entry,
    )
    await hass.async_block_till_done()

    assert registry.async_get_issue(DOMAIN, NO_SOURCES_ISSUE_ID) is None
