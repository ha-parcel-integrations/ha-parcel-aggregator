"""Tests for the Assist natural-language summary helpers."""
from datetime import timedelta

import pytest
from homeassistant.components.homeassistant.exposed_entities import async_expose_entity
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.parcel_aggregator.assist import (
    ASSIST_BUCKETS,
    any_bucket_exposed,
    describe_bucket,
    get_assist_strings,
    get_loaded_coordinator,
    is_bucket_exposed,
)
from custom_components.parcel_aggregator.const import DOMAIN
from custom_components.parcel_aggregator.coordinator import ParcelAggregatorCoordinator


def _parcel(
    carrier: str = "PostNL",
    sender: str | None = "Bol.com",
    status: str = "out_for_delivery",
    planned_from: str | None = None,
    planned_to: str | None = None,
) -> dict:
    return {
        "carrier": carrier,
        "sender": sender,
        "status": status,
        "planned_from": planned_from,
        "planned_to": planned_to,
    }


# ---------------------------------------------------------------------------
# get_assist_strings
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_assist_strings_loads_english_source(hass):
    strings = await get_assist_strings(hass, "en")
    assert strings["bucket.incoming.one"] == "incoming parcel"
    assert strings["no_parcels"] == "You have no {label}."


@pytest.mark.asyncio
async def test_get_assist_strings_loads_dutch(hass):
    strings = await get_assist_strings(hass, "nl")
    assert strings["bucket.incoming.one"] == "binnenkomend pakket"


@pytest.mark.asyncio
async def test_get_assist_strings_falls_back_to_english_for_unknown_language(hass):
    # No translations/xx.json exists; HA's translation cache merges English
    # underneath any language on a per-key basis, so this still resolves.
    strings = await get_assist_strings(hass, "xx")
    assert strings["no_parcels"] == "You have no {label}."


@pytest.mark.asyncio
async def test_get_assist_strings_normalizes_regional_variants(hass):
    strings = await get_assist_strings(hass, "nl-NL")
    assert strings["bucket.incoming.one"] == "binnenkomend pakket"


# ---------------------------------------------------------------------------
# describe_bucket
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_describe_bucket_empty_en(hass):
    text = await describe_bucket(hass, {"parcels": []}, "incoming")
    assert text == "You have no incoming parcels."


@pytest.mark.asyncio
async def test_describe_bucket_empty_nl(hass):
    text = await describe_bucket(hass, {"parcels": []}, "incoming", language="nl")
    assert text == "Je hebt geen binnenkomende pakketten."


_WEEKDAY_NAMES_EN = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]


def _at(days_from_now: int, hour: int) -> str:
    """Return an ISO timestamp ``days_from_now`` days out, at ``hour`` UTC."""
    dt = dt_util.now() + timedelta(days=days_from_now)
    return dt.replace(hour=hour, minute=0, second=0, microsecond=0).isoformat()


@pytest.mark.asyncio
async def test_describe_bucket_single_parcel_expected_today(hass):
    await hass.config.async_set_time_zone("UTC")
    info = {"parcels": [_parcel(planned_from=_at(0, 14), planned_to=_at(0, 16))]}
    text = await describe_bucket(hass, info, "incoming", language="en")
    assert text == (
        "You have 1 incoming parcel: a PostNL parcel from Bol.com, "
        "expected today between 14:00 and 16:00."
    )


@pytest.mark.asyncio
async def test_describe_bucket_single_parcel_expected_tomorrow(hass):
    await hass.config.async_set_time_zone("UTC")
    info = {"parcels": [_parcel(planned_from=_at(1, 9))]}
    text = await describe_bucket(hass, info, "incoming", language="en")
    assert "expected tomorrow around 09:00" in text


@pytest.mark.asyncio
async def test_describe_bucket_single_parcel_expected_later_weekday(hass):
    await hass.config.async_set_time_zone("UTC")
    dt = dt_util.now() + timedelta(days=3)
    weekday_name = _WEEKDAY_NAMES_EN[dt.weekday()]
    info = {"parcels": [_parcel(planned_from=_at(3, 10))]}
    text = await describe_bucket(hass, info, "incoming", language="en")
    assert f"expected on {weekday_name} around 10:00" in text


@pytest.mark.asyncio
async def test_describe_bucket_falls_back_to_status_without_timestamps(hass):
    info = {"parcels": [_parcel(status="in_transit")]}
    text = await describe_bucket(hass, info, "incoming", language="en")
    assert text.endswith("a PostNL parcel from Bol.com, in transit.")


@pytest.mark.asyncio
async def test_describe_bucket_omits_sender_when_missing(hass):
    info = {"parcels": [_parcel(sender=None, status="in_transit")]}
    text = await describe_bucket(hass, info, "incoming", language="en")
    assert "a PostNL parcel, in transit." in text


@pytest.mark.asyncio
async def test_describe_bucket_joins_multiple_parcels(hass):
    info = {
        "parcels": [
            _parcel(carrier="PostNL", sender="Bol.com", status="in_transit"),
            _parcel(carrier="DHL", sender="Zalando", status="out_for_delivery"),
        ]
    }
    text = await describe_bucket(hass, info, "incoming", language="en")
    assert text == (
        "You have 2 incoming parcels: a PostNL parcel from Bol.com, in transit "
        "and a DHL parcel from Zalando, out for delivery."
    )


@pytest.mark.asyncio
async def test_describe_bucket_single_parcel_nl(hass):
    info = {"parcels": [_parcel(carrier="PostNL", sender="Bol.com", status="in_transit")]}
    text = await describe_bucket(hass, info, "incoming", language="nl")
    assert text == (
        "Je hebt 1 binnenkomend pakket: een PostNL-pakket van Bol.com, onderweg."
    )


@pytest.mark.asyncio
async def test_describe_bucket_unknown_language_falls_back_to_english(hass):
    info = {"parcels": []}
    text = await describe_bucket(hass, info, "incoming", language="xx")
    assert text == "You have no incoming parcels."


@pytest.mark.asyncio
async def test_describe_bucket_unmapped_status_defaults_to_unknown(hass):
    info = {"parcels": [_parcel(status=None)]}
    text = await describe_bucket(hass, info, "incoming", language="en")
    assert text.endswith("status unknown.")


# ---------------------------------------------------------------------------
# get_loaded_coordinator
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_loaded_coordinator_returns_none_without_entry(hass):
    assert get_loaded_coordinator(hass) is None


@pytest.mark.asyncio
async def test_get_loaded_coordinator_returns_coordinator_when_loaded(hass):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = get_loaded_coordinator(hass)
    assert isinstance(coordinator, ParcelAggregatorCoordinator)


# ---------------------------------------------------------------------------
# exposure helpers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_is_bucket_exposed_skips_check_without_assistant(hass):
    assert is_bucket_exposed(hass, None, "incoming") is True


@pytest.mark.asyncio
async def test_is_bucket_exposed_false_when_entity_missing(hass):
    assert is_bucket_exposed(hass, "conversation", "incoming") is False


@pytest.mark.asyncio
async def test_is_bucket_exposed_respects_toggle(hass):
    assert await async_setup_component(hass, "homeassistant", {})
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    entity_id = "sensor.parcel_aggregator_incoming_parcels"
    async_expose_entity(hass, "conversation", entity_id, False)
    assert is_bucket_exposed(hass, "conversation", "incoming") is False

    async_expose_entity(hass, "conversation", entity_id, True)
    assert is_bucket_exposed(hass, "conversation", "incoming") is True


@pytest.mark.asyncio
async def test_any_bucket_exposed_true_if_one_bucket_exposed(hass):
    assert await async_setup_component(hass, "homeassistant", {})
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    async_expose_entity(
        hass, "conversation", "sensor.parcel_aggregator_incoming_parcels", True
    )
    assert any_bucket_exposed(hass, "conversation") is True


@pytest.mark.asyncio
async def test_any_bucket_exposed_false_if_none_exposed(hass):
    assert await async_setup_component(hass, "homeassistant", {})
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    for bucket in ASSIST_BUCKETS:
        suffix = "" if bucket == "awaiting_pickup" else "_parcels"
        async_expose_entity(
            hass, "conversation", f"sensor.parcel_aggregator_{bucket}{suffix}", False
        )
    assert any_bucket_exposed(hass, "conversation") is False
