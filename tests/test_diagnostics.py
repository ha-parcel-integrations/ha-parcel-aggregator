"""Tests for the Parcel Aggregator diagnostics handler."""
from unittest.mock import MagicMock

import pytest

from custom_components.parcel_aggregator.diagnostics import (
    TO_REDACT,
    async_get_config_entry_diagnostics,
)

REDACTED = "**REDACTED**"


def _entry(*, sources: dict[str, dict[str, str]] | None = None, data: dict | None = None) -> MagicMock:
    coordinator = MagicMock()
    coordinator._sources = sources or {"incoming": {}, "outgoing": {}, "delivered": {}}
    coordinator.data = data

    entry = MagicMock()
    entry.runtime_data = coordinator
    return entry


@pytest.mark.asyncio
async def test_diagnostics_reports_watched_sources():
    entry = _entry(
        sources={
            "incoming": {
                "sensor.dhl_incoming_parcels": "dhl_nl",
                "sensor.postnl_incoming_parcels": "postnl",
            },
            "outgoing": {"sensor.dpd_outgoing_parcels": "dpd"},
            "delivered": {},
        },
    )
    result = await async_get_config_entry_diagnostics(MagicMock(), entry)
    assert result["watched_source_count"] == 3
    assert "sensor.dhl_incoming_parcels" in result["sources_by_bucket"]["incoming"]


@pytest.mark.asyncio
async def test_diagnostics_redacts_per_parcel_pii():
    entry = _entry(
        data={
            "incoming": {
                "total": 1,
                "by_carrier": {"DHL": 1},
                "parcels": [
                    {
                        "carrier": "DHL",
                        "barcode": "3SABC123",
                        "sender": "Online Retailer",
                        "url": "https://example.com/track",
                        "pickup_point": "Albert Heijn Vondellaan",
                    }
                ],
            }
        },
    )
    result = await async_get_config_entry_diagnostics(MagicMock(), entry)
    parcel = result["data"]["incoming"]["parcels"][0]
    assert parcel["carrier"] == "DHL"  # not PII
    assert parcel["barcode"] == REDACTED
    assert parcel["sender"] == REDACTED
    assert parcel["url"] == REDACTED
    assert parcel["pickup_point"] == REDACTED
    # Counts and per-carrier breakdown stay untouched
    assert result["data"]["incoming"]["total"] == 1
    assert result["data"]["incoming"]["by_carrier"] == {"DHL": 1}


def test_to_redact_covers_expected_keys():
    for key in ("barcode", "sender", "pickup_point", "url", "raw"):
        assert key in TO_REDACT
