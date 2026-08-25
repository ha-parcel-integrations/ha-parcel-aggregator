"""Tests for the Parcel Aggregator LLM tool platform.

Skipped wholesale on any HA version that predates ``homeassistant.helpers.llm``
/ ``homeassistant.components.llm`` — see the import-guard comment in
``custom_components/parcel_aggregator/llm.py``.
"""
import pytest
from homeassistant.components.homeassistant.exposed_entities import async_expose_entity
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

llm_helpers = pytest.importorskip("homeassistant.helpers.llm")
# The domain-platform-discovery mechanism (LLMTools, async_get_tools(hass,
# llm_context, api_id)) lives in this newer, separate module — it can lag
# behind homeassistant.helpers.llm, which is what llm.py's own ImportError
# guard actually keys off. Both must be present for these tests to apply.
llm_component = pytest.importorskip("homeassistant.components.llm")
LLM_API_ASSIST = llm_helpers.LLM_API_ASSIST
IntentTool = llm_helpers.IntentTool
LLMContext = llm_helpers.LLMContext

from custom_components.parcel_aggregator import intent as parcel_intent  # noqa: E402
from custom_components.parcel_aggregator import llm as parcel_llm  # noqa: E402
from custom_components.parcel_aggregator.const import DOMAIN  # noqa: E402

INCOMING_ENTITY_ID = "sensor.parcel_aggregator_incoming_parcels"


def _llm_context(hass) -> LLMContext:
    return LLMContext(
        platform="test",
        context=None,
        language="en",
        assistant="conversation",
        device_id=None,
    )


async def _setup_entry(hass):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@pytest.mark.asyncio
async def test_returns_none_for_other_api(hass):
    await _setup_entry(hass)
    await parcel_intent.async_setup_intents(hass)
    result = parcel_llm.async_get_tools(hass, _llm_context(hass), "other_api")
    assert result is None


@pytest.mark.asyncio
async def test_returns_none_without_config_entry(hass):
    result = parcel_llm.async_get_tools(hass, _llm_context(hass), LLM_API_ASSIST)
    assert result is None


@pytest.mark.asyncio
async def test_returns_none_when_nothing_exposed(hass):
    assert await async_setup_component(hass, "homeassistant", {})
    await _setup_entry(hass)
    await parcel_intent.async_setup_intents(hass)
    result = parcel_llm.async_get_tools(hass, _llm_context(hass), LLM_API_ASSIST)
    assert result is None


@pytest.mark.asyncio
async def test_returns_none_when_intent_not_registered(hass):
    assert await async_setup_component(hass, "homeassistant", {})
    await _setup_entry(hass)
    async_expose_entity(hass, "conversation", INCOMING_ENTITY_ID, True)

    result = parcel_llm.async_get_tools(hass, _llm_context(hass), LLM_API_ASSIST)
    assert result is None


@pytest.mark.asyncio
async def test_returns_intent_tool_when_exposed(hass):
    assert await async_setup_component(hass, "homeassistant", {})
    await _setup_entry(hass)
    await parcel_intent.async_setup_intents(hass)
    async_expose_entity(hass, "conversation", INCOMING_ENTITY_ID, True)

    result = parcel_llm.async_get_tools(hass, _llm_context(hass), LLM_API_ASSIST)
    assert result is not None
    assert len(result.tools) == 1
    tool = result.tools[0]
    assert isinstance(tool, IntentTool)
    assert tool.name == parcel_intent.INTENT_GET_PARCEL_DETAILS
