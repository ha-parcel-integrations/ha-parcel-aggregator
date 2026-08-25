"""Tests for the ParcelAggregatorGetDetails Assist intent."""
import pytest
from homeassistant.components.homeassistant.exposed_entities import async_expose_entity
from homeassistant.helpers import intent
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.parcel_aggregator import intent as parcel_intent
from custom_components.parcel_aggregator.const import DOMAIN

INCOMING_ENTITY_ID = "sensor.parcel_aggregator_incoming_parcels"


async def _setup_entry(hass):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@pytest.mark.asyncio
async def test_handle_without_setup_entry(hass):
    await parcel_intent.async_setup_intents(hass)

    response = await intent.async_handle(
        hass, "test", parcel_intent.INTENT_GET_PARCEL_DETAILS, {}
    )
    assert response.speech["plain"]["speech"] == "Parcel Aggregator is not set up."


@pytest.mark.asyncio
async def test_handle_defaults_to_incoming_bucket(hass):
    await _setup_entry(hass)
    await parcel_intent.async_setup_intents(hass)

    response = await intent.async_handle(
        hass, "test", parcel_intent.INTENT_GET_PARCEL_DETAILS, {}
    )
    assert response.response_type is intent.IntentResponseType.QUERY_ANSWER
    assert response.speech["plain"]["speech"] == "You have no incoming parcels."


@pytest.mark.asyncio
async def test_handle_respects_bucket_slot(hass):
    await _setup_entry(hass)
    await parcel_intent.async_setup_intents(hass)

    response = await intent.async_handle(
        hass,
        "test",
        parcel_intent.INTENT_GET_PARCEL_DETAILS,
        {"bucket": {"value": "awaiting_pickup"}},
    )
    assert response.speech["plain"]["speech"] == "You have no parcels awaiting pickup."


@pytest.mark.asyncio
async def test_handle_uses_dutch_when_language_is_nl(hass):
    await _setup_entry(hass)
    await parcel_intent.async_setup_intents(hass)

    response = await intent.async_handle(
        hass,
        "test",
        parcel_intent.INTENT_GET_PARCEL_DETAILS,
        {},
        language="nl",
    )
    assert response.speech["plain"]["speech"] == "Je hebt geen binnenkomende pakketten."


@pytest.mark.asyncio
async def test_handle_blocks_response_when_not_exposed(hass):
    assert await async_setup_component(hass, "homeassistant", {})
    await _setup_entry(hass)
    await parcel_intent.async_setup_intents(hass)
    async_expose_entity(hass, "conversation", INCOMING_ENTITY_ID, False)

    response = await intent.async_handle(
        hass,
        "test",
        parcel_intent.INTENT_GET_PARCEL_DETAILS,
        {},
        assistant="conversation",
    )
    assert (
        response.speech["plain"]["speech"]
        == "Those parcels are not exposed to this assistant."
    )


@pytest.mark.asyncio
async def test_handle_answers_when_exposed(hass):
    assert await async_setup_component(hass, "homeassistant", {})
    await _setup_entry(hass)
    await parcel_intent.async_setup_intents(hass)
    async_expose_entity(hass, "conversation", INCOMING_ENTITY_ID, True)

    response = await intent.async_handle(
        hass,
        "test",
        parcel_intent.INTENT_GET_PARCEL_DETAILS,
        {},
        assistant="conversation",
    )
    assert response.speech["plain"]["speech"] == "You have no incoming parcels."
