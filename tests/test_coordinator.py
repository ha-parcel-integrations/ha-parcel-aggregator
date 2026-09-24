"""Tests for the Parcel Aggregator's parsing and aggregation helpers."""
from datetime import datetime, timezone

import pytest

from custom_components.parcel_aggregator.coordinator import (
    count_by_carrier,
    dedupe_parcels,
    next_delivery_from,
    parse_timestamp_state,
    sort_parcels_by_ts,
    strip_raw,
)


def _parcel(
    carrier: str = "DHL",
    barcode: str = "ABC",
    sender: str = "Sender",
    planned_from: str | None = None,
    pickup: bool = False,
    pickup_point: str | None = None,
    status: str = "in_transit",
    delivered: bool = False,
    delivered_at: str | None = None,
    raw: dict | None = None,
) -> dict:
    return {
        "carrier": carrier,
        "barcode": barcode,
        "sender": sender,
        "status": status,
        "delivered": delivered,
        "delivered_at": delivered_at,
        "planned_from": planned_from,
        "planned_to": None,
        "pickup": pickup,
        "pickup_point": pickup_point,
        "url": None,
        "raw": raw if raw is not None else {"_": "carrier-specific"},
    }


# ---------------------------------------------------------------------------
# parse_timestamp_state
# ---------------------------------------------------------------------------


def test_parse_timestamp_parses_iso_with_tz():
    dt = parse_timestamp_state("2026-06-12T10:00:00+02:00")
    assert dt is not None
    assert dt.year == 2026 and dt.hour == 10


def test_parse_timestamp_parses_z_suffix():
    dt = parse_timestamp_state("2026-06-12T10:00:00Z")
    assert dt == datetime(2026, 6, 12, 10, 0, 0, tzinfo=timezone.utc)


def test_parse_timestamp_returns_none_for_unavailable():
    assert parse_timestamp_state("unavailable") is None
    assert parse_timestamp_state(None) is None


def test_parse_timestamp_returns_none_for_garbage():
    assert parse_timestamp_state("not a date") is None


def test_parse_timestamp_treats_naive_iso_as_utc():
    # Regression: when one source carrier emits "2026-06-12T10:00:00" without
    # a tz suffix and another emits "...Z", the downstream sort crashed with
    # "can't compare offset-naive and offset-aware datetimes". Naive values
    # must come back tagged so every result is mutually comparable.
    dt = parse_timestamp_state("2026-06-12T10:00:00")
    assert dt == datetime(2026, 6, 12, 10, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# dedupe_parcels
# ---------------------------------------------------------------------------


def test_dedupe_collapses_same_carrier_and_barcode():
    # Two source instances (e.g. two PostNL accounts with shared visibility)
    # both reporting the same parcel — regression for issue #7.
    a = _parcel(carrier="PostNL", barcode="AAAA1111111111", sender="Account Owner A")
    b = _parcel(carrier="PostNL", barcode="AAAA1111111111", sender="Shop One")
    assert dedupe_parcels([a, b]) == [a]


def test_dedupe_keeps_distinct_barcodes():
    a = _parcel(carrier="PostNL", barcode="AAAA1111111111")
    b = _parcel(carrier="PostNL", barcode="BBBB2222222222")
    assert dedupe_parcels([a, b]) == [a, b]


def test_dedupe_keeps_same_barcode_across_different_carriers():
    a = _parcel(carrier="PostNL", barcode="SHARED")
    b = _parcel(carrier="DHL", barcode="SHARED")
    assert dedupe_parcels([a, b]) == [a, b]


def test_dedupe_keeps_two_distinct_parcels_from_two_accounts_same_carrier():
    # Two PostNL accounts with two genuinely different parcels — not a dupe.
    a = _parcel(carrier="PostNL", barcode="AAAA1111111111")
    b = _parcel(carrier="PostNL", barcode="BBBB2222222222")
    assert dedupe_parcels([a, b]) == [a, b]


# ---------------------------------------------------------------------------
# count_by_carrier
# ---------------------------------------------------------------------------


def test_count_by_carrier_counts_across_carriers():
    parcels = [
        _parcel(carrier="DHL", barcode="1"),
        _parcel(carrier="DHL", barcode="2"),
        _parcel(carrier="PostNL", barcode="3"),
    ]
    result = count_by_carrier(parcels)
    assert result == {"total": 3, "by_carrier": {"DHL": 2, "PostNL": 1}}


def test_count_by_carrier_empty_list():
    assert count_by_carrier([]) == {"total": 0, "by_carrier": {}}


# ---------------------------------------------------------------------------
# strip_raw
# ---------------------------------------------------------------------------


def test_strip_raw_removes_raw_key():
    parcel = _parcel(raw={"big": "payload"})
    assert "raw" in parcel
    stripped = strip_raw(parcel)
    assert "raw" not in stripped
    assert stripped["carrier"] == "DHL"
    # original is untouched
    assert "raw" in parcel


def test_strip_raw_is_noop_when_raw_missing():
    parcel = {"carrier": "DHL", "barcode": "ABC"}
    assert strip_raw(parcel) == parcel


def test_strip_raw_keeps_top_level_history():
    """The opt-in history timeline is a top-level field, so it survives
    strip_raw() and flows through the aggregator unchanged."""
    history = [{"timestamp": "2026-06-24T17:23:13Z", "status": "delivered", "raw_status": "DELIVERED"}]
    parcel = {**_parcel(), "history": history}
    stripped = strip_raw(parcel)
    assert "raw" not in stripped
    assert stripped["history"] == history


def test_next_delivery_keeps_history_on_the_parcel():
    history = [{"timestamp": "2026-06-20T09:00:00Z", "status": "in_transit", "raw_status": "PARCEL_SORTED_AT_HUB"}]
    parcel = {**_parcel(planned_from="2026-06-20T09:00:00Z"), "history": history}
    result = next_delivery_from([parcel])
    assert result["parcel"]["history"] == history
    assert "raw" not in result["parcel"]


# ---------------------------------------------------------------------------
# sort_parcels_by_ts
# ---------------------------------------------------------------------------


def test_sort_parcels_orders_ascending_by_planned_from():
    parcels = [
        _parcel(barcode="late", planned_from="2026-06-15T10:00:00+00:00"),
        _parcel(barcode="early", planned_from="2026-06-13T08:00:00+00:00"),
        _parcel(barcode="mid", planned_from="2026-06-14T12:00:00+00:00"),
    ]
    ordered = [p["barcode"] for p in sort_parcels_by_ts(parcels, "planned_from")]
    assert ordered == ["early", "mid", "late"]


def test_sort_parcels_orders_descending_for_delivered_at():
    parcels = [
        _parcel(barcode="oldest", delivered=True, delivered_at="2026-06-13T08:00:00+00:00"),
        _parcel(barcode="newest", delivered=True, delivered_at="2026-06-15T10:00:00+00:00"),
        _parcel(barcode="mid", delivered=True, delivered_at="2026-06-14T12:00:00+00:00"),
    ]
    ordered = [p["barcode"] for p in sort_parcels_by_ts(parcels, "delivered_at", descending=True)]
    assert ordered == ["newest", "mid", "oldest"]


def test_sort_parcels_keeps_missing_timestamps_at_end():
    parcels = [
        _parcel(barcode="no-ts-1", planned_from=None),
        _parcel(barcode="early", planned_from="2026-06-13T08:00:00+00:00"),
        _parcel(barcode="no-ts-2", planned_from="garbage"),
        _parcel(barcode="late", planned_from="2026-06-15T10:00:00+00:00"),
    ]
    ordered = [p["barcode"] for p in sort_parcels_by_ts(parcels, "planned_from")]
    assert ordered[:2] == ["early", "late"]
    assert set(ordered[2:]) == {"no-ts-1", "no-ts-2"}


def test_sort_parcels_missing_timestamps_stay_at_end_when_descending():
    parcels = [
        _parcel(barcode="no-ts", delivered=True, delivered_at=None),
        _parcel(barcode="newer", delivered=True, delivered_at="2026-06-15T10:00:00+00:00"),
        _parcel(barcode="older", delivered=True, delivered_at="2026-06-13T10:00:00+00:00"),
    ]
    ordered = [p["barcode"] for p in sort_parcels_by_ts(parcels, "delivered_at", descending=True)]
    assert ordered == ["newer", "older", "no-ts"]


def test_sort_parcels_empty_input_returns_empty_list():
    assert sort_parcels_by_ts([], "planned_from") == []


# ---------------------------------------------------------------------------
# Coordinator integration: dedup across two source instances
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_shared_parcel_across_two_accounts_is_deduped(hass):
    """Regression for issue #7: two PostNL accounts with shared visibility
    both report the same barcode — the aggregator must count it once."""
    from homeassistant.helpers import entity_registry as er
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.parcel_aggregator.const import DOMAIN

    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data={})
    entry.add_to_hass(hass)

    registry = er.async_get(hass)
    source_entity_ids = []
    for account in ("account-a", "account-b"):
        postnl_entry = MockConfigEntry(domain="postnl", unique_id=account)
        postnl_entry.add_to_hass(hass)
        registered = registry.async_get_or_create(
            domain="sensor",
            platform="postnl",
            unique_id=f"{account}_incoming_parcels",
            config_entry=postnl_entry,
        )
        source_entity_ids.append(registered.entity_id)

    shared_parcel_via_a = _parcel(
        carrier="PostNL", barcode="AAAA1111111111", sender="Account Owner A"
    )
    shared_parcel_via_b = _parcel(
        carrier="PostNL", barcode="AAAA1111111111", sender="Shop One"
    )
    hass.states.async_set(
        source_entity_ids[0], "1", {"parcels": [shared_parcel_via_a]}
    )
    hass.states.async_set(
        source_entity_ids[1], "1", {"parcels": [shared_parcel_via_b]}
    )

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    data = entry.runtime_data.data
    assert data["incoming"]["total"] == 1
    assert data["incoming"]["by_carrier"] == {"PostNL": 1}
    assert len(data["incoming"]["parcels"]) == 1
    assert data["incoming"]["parcels"][0]["barcode"] == "AAAA1111111111"


# ---------------------------------------------------------------------------
# next_delivery_from
# ---------------------------------------------------------------------------


def test_next_delivery_picks_earliest_across_carriers():
    parcels = [
        _parcel(carrier="DHL", barcode="A", planned_from="2026-06-15T10:00:00+00:00"),
        _parcel(carrier="PostNL", barcode="B", planned_from="2026-06-13T08:00:00+00:00"),
        _parcel(carrier="DPD", barcode="C", planned_from="2026-06-14T12:00:00+00:00"),
    ]
    result = next_delivery_from(parcels)
    assert result["value"] == datetime(2026, 6, 13, 8, 0, 0, tzinfo=timezone.utc)
    assert result["parcel"]["barcode"] == "B"
    assert result["parcel"]["carrier"] == "PostNL"
    # raw is stripped from the surfaced parcel
    assert "raw" not in result["parcel"]


def test_next_delivery_by_carrier_keeps_earliest_per_carrier():
    parcels = [
        _parcel(carrier="DHL", barcode="A", planned_from="2026-06-15T10:00:00+00:00"),
        _parcel(carrier="DHL", barcode="B", planned_from="2026-06-13T10:00:00+00:00"),
    ]
    result = next_delivery_from(parcels)
    assert result["by_carrier"]["DHL"] == datetime(2026, 6, 13, 10, 0, 0, tzinfo=timezone.utc)


def test_next_delivery_skips_parcels_without_planned_from():
    parcels = [
        _parcel(carrier="DHL", barcode="A", planned_from=None),
        _parcel(carrier="PostNL", barcode="B", planned_from="2026-06-13T10:00:00+00:00"),
    ]
    result = next_delivery_from(parcels)
    assert result["parcel"]["barcode"] == "B"


def test_next_delivery_returns_none_when_no_data():
    result = next_delivery_from([])
    assert result == {"value": None, "by_carrier": {}, "parcel": None}


def test_next_delivery_returns_none_when_no_timestamps():
    result = next_delivery_from([_parcel(planned_from=None)])
    assert result["value"] is None
    assert result["parcel"] is None


# ---------------------------------------------------------------------------
# Source discovery — bucket assignment by unique_id suffix
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_discover_buckets_sources_by_suffix(hass):
    """A carrier's outgoing-delivered sensor must land in its own bucket, not
    in ``delivered`` — its unique_id also ends with ``_delivered_parcels``."""
    from homeassistant.helpers import entity_registry as er
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.parcel_aggregator.const import DOMAIN
    from custom_components.parcel_aggregator.coordinator import (
        ParcelAggregatorCoordinator,
    )

    reg = er.async_get(hass)

    def _add(unique_id: str) -> str:
        return reg.async_get_or_create("sensor", "dhl_nl", unique_id).entity_id

    incoming = _add("acc_incoming_parcels")
    outgoing = _add("acc_outgoing_parcels")
    delivered = _add("acc_delivered_parcels")
    outgoing_delivered = _add("acc_outgoing_delivered_parcels")
    en_route = _add("acc_en_route_to_pickup_point")
    awaiting = _add("acc_awaiting_pickup")

    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data={})
    entry.add_to_hass(hass)
    coordinator = ParcelAggregatorCoordinator(hass, entry)
    coordinator._discover()

    assert incoming in coordinator._sources["incoming"]
    assert outgoing in coordinator._sources["outgoing"]
    assert delivered in coordinator._sources["delivered"]
    assert outgoing_delivered in coordinator._sources["outgoing_delivered"]
    assert en_route in coordinator._sources["en_route_to_pickup_point"]
    assert awaiting in coordinator._sources["awaiting_pickup"]
    # Regression: the outgoing-delivered sensor must NOT be swallowed by the
    # shorter ``_delivered_parcels`` suffix.
    assert outgoing_delivered not in coordinator._sources["delivered"]


async def _setup_with_sources(hass, sources: dict[tuple[str, str], tuple[str, dict]]):
    """Register carrier source sensors, set their states, set up the aggregator."""
    from homeassistant.helpers import entity_registry as er
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.parcel_aggregator.const import DOMAIN

    registry = er.async_get(hass)
    for (platform, unique_id), (state, attributes) in sources.items():
        entity_id = registry.async_get_or_create("sensor", platform, unique_id).entity_id
        hass.states.async_set(entity_id, state, attributes)

    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry.runtime_data.data


@pytest.mark.asyncio
async def test_en_route_to_pickup_point_merges_and_dedupes_across_carriers(hass):
    shared = _parcel(carrier="PostNL", barcode="SHARED", pickup=True, planned_from="2026-09-26T10:00:00+00:00")
    dpd = _parcel(carrier="DPD", barcode="DPD1", pickup=True, planned_from="2026-09-25T10:00:00+00:00")
    data = await _setup_with_sources(hass, {
        ("postnl", "a_en_route_to_pickup_point"): ("1", {"parcels": [shared]}),
        ("postnl", "b_en_route_to_pickup_point"): ("1", {"parcels": [dict(shared)]}),
        ("dpd", "e1_en_route_to_pickup_point"): ("1", {"parcels": [dpd]}),
    })

    bucket = data["en_route_to_pickup_point"]
    assert bucket["total"] == 2
    assert bucket["by_carrier"] == {"PostNL": 1, "DPD": 1}
    assert [p["barcode"] for p in bucket["parcels"]] == ["DPD1", "SHARED"]
    assert bucket["any_available"] is True


@pytest.mark.asyncio
async def test_en_route_to_pickup_point_unavailable_sources(hass):
    data = await _setup_with_sources(hass, {
        ("dpd", "e1_en_route_to_pickup_point"): ("unavailable", {}),
        ("dpd", "e1_incoming_parcels"): ("0", {"parcels": []}),
    })

    bucket = data["en_route_to_pickup_point"]
    assert bucket["total"] == 0
    assert bucket["parcels"] == []
    assert bucket["any_available"] is False


@pytest.mark.asyncio
async def test_awaiting_pickup_merges_and_dedupes_carrier_sources(hass):
    shared = _parcel(carrier="PostNL", barcode="SHARED", status="at_pickup_point")
    inpost = _parcel(carrier="InPost", barcode="LOCKER", status="at_pickup_point")
    data = await _setup_with_sources(hass, {
        ("postnl", "a_awaiting_pickup"): ("1", {"parcels": [shared]}),
        ("postnl", "b_awaiting_pickup"): ("1", {"parcels": [dict(shared)]}),
        ("inpost", "e1_awaiting_pickup"): ("1", {"parcels": [inpost]}),
    })

    bucket = data["awaiting_pickup"]
    assert bucket["total"] == 2
    assert bucket["by_carrier"] == {"PostNL": 1, "InPost": 1}
    assert {p["barcode"] for p in bucket["parcels"]} == {"SHARED", "LOCKER"}
    assert bucket["any_available"] is True


@pytest.mark.asyncio
async def test_awaiting_pickup_comes_only_from_carrier_sources(hass):
    en_route = _parcel(carrier="DPD", barcode="EN_ROUTE", pickup=True)
    ready = _parcel(carrier="DPD", barcode="READY", pickup=True, status="at_pickup_point")
    no_sensor = _parcel(carrier="Trunkrs", barcode="NO_SENSOR", status="at_pickup_point")
    data = await _setup_with_sources(hass, {
        ("dpd", "e1_incoming_parcels"): ("2", {"parcels": [en_route, ready]}),
        ("dpd", "e1_en_route_to_pickup_point"): ("1", {"parcels": [en_route]}),
        ("dpd", "e1_awaiting_pickup"): ("1", {"parcels": [ready]}),
        ("trunkrs", "e2_incoming_parcels"): ("1", {"parcels": [no_sensor]}),
    })

    assert [p["barcode"] for p in data["en_route_to_pickup_point"]["parcels"]] == ["EN_ROUTE"]
    assert [p["barcode"] for p in data["awaiting_pickup"]["parcels"]] == ["READY"]


@pytest.mark.asyncio
async def test_awaiting_pickup_strips_raw(hass):
    parcel = _parcel(carrier="DPD", status="at_pickup_point", raw={"big": "payload"})
    data = await _setup_with_sources(hass, {
        ("dpd", "e1_awaiting_pickup"): ("1", {"parcels": [parcel]}),
    })

    assert "raw" not in data["awaiting_pickup"]["parcels"][0]


@pytest.mark.asyncio
async def test_carrier_unique_id_migration_is_picked_up_after_setup(hass):
    """A carrier renaming its summary unique_id after the aggregator started
    (same entity_id) must land the sensor in the right bucket."""
    from homeassistant.helpers import entity_registry as er

    ready = _parcel(carrier="DHL", barcode="READY", pickup=True, status="at_pickup_point")
    data = await _setup_with_sources(hass, {
        ("dhl_nl", "user1_pickup_pending"): ("1", {"parcels": [ready]}),
    })
    assert data["awaiting_pickup"]["total"] == 0

    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id("sensor", "dhl_nl", "user1_pickup_pending")
    registry.async_update_entity(entity_id, new_unique_id="user1_awaiting_pickup")
    await hass.async_block_till_done()

    entry = hass.config_entries.async_entries("parcel_aggregator")[0]
    assert entity_id in entry.runtime_data._sources["awaiting_pickup"]
    assert [p["barcode"] for p in entry.runtime_data.data["awaiting_pickup"]["parcels"]] == ["READY"]
