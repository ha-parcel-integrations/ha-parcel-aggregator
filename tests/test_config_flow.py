"""Tests for the Parcel Aggregator config flow."""
import pytest

from homeassistant.config_entries import SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType

from custom_components.parcel_aggregator.const import DOMAIN


@pytest.mark.asyncio
async def test_user_flow_creates_entry(hass):
    """A single-step flow with no input creates the entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Parcel Aggregator"
    assert result["data"] == {}


@pytest.mark.asyncio
async def test_user_flow_is_single_instance(hass):
    """A second flow attempt aborts because the integration is single-instance."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data={}).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
