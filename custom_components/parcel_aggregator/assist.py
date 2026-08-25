"""Shared building blocks for Assist support (intent + LLM tool).

Builds a natural-language summary of a bucket's ``parcels`` list, e.g.
"You have 1 incoming parcel: a PostNL parcel from Bol.com, expected today
between 14:00 and 16:00." Both ``intent.py`` (the built-in Assist agent) and
``llm.py`` (LLM-based Assist agents) call into this module so the wording
stays in one place.

Every phrase lives in ``strings.json`` / ``translations/<lang>.json`` under
the "assist" key, loaded through Home Assistant's own translation system —
the same mechanism this integration already uses for entity names and issue
text. Adding a language is a translation-file contribution, not a Python
change; there's no per-language branching here to extend.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.homeassistant import async_should_expose
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import translation
from homeassistant.util import dt as dt_util

from .const import DOMAIN, ParcelStatus
from .coordinator import ParcelAggregatorCoordinator, parse_timestamp_state

# Buckets the aggregator can describe in natural language. Limited to the
# incoming side of the parcel contract — outgoing/outgoing_delivered are
# deliberately excluded, as "what am I sending" isn't a use case for Assist.
# Also excludes "next_delivery", which has a different ({value, parcel}) shape.
ASSIST_BUCKETS = (
    "incoming",
    "delivered",
    "awaiting_pickup",
)

DEFAULT_ASSIST_BUCKET = "incoming"

_ASSIST_CATEGORY = "assist"
_ASSIST_PREFIX = f"component.{DOMAIN}.{_ASSIST_CATEGORY}."


async def get_assist_strings(hass: HomeAssistant, language: str | None) -> dict[str, str]:
    """Return the flattened "assist" translation strings for ``language``.

    Home Assistant's translation cache already merges English underneath any
    other language on a per-key basis (``homeassistant.helpers.translation``),
    so a language with no "assist" section yet — or only a partial one —
    degrades to English one missing key at a time rather than needing a
    fallback here.
    """
    lang = (language or "en").split("-")[0].lower()
    raw = await translation.async_get_translations(
        hass, lang, _ASSIST_CATEGORY, integrations={DOMAIN}
    )
    return {key.removeprefix(_ASSIST_PREFIX): value for key, value in raw.items()}


def _format_clock(dt: datetime) -> str:
    return dt_util.as_local(dt).strftime("%H:%M")


def _day_phrase(dt: datetime, strings: dict[str, str]) -> str:
    """Say "today"/"tomorrow"/"on <weekday>" for ``dt``'s local calendar date.

    A bucket like "incoming" holds every active parcel, not just today's —
    without this, a parcel expected next week would read as "expected
    between 14:00 and 16:00" with nothing to say it isn't today.
    """
    local_date = dt_util.as_local(dt).date()
    delta = (local_date - dt_util.now().date()).days
    if delta == 0:
        return strings["day_today"]
    if delta == 1:
        return strings["day_tomorrow"]
    weekday = strings[f"weekday.{local_date.weekday()}"]
    return strings["day_weekday"].format(weekday=weekday)


def _describe_status_or_window(parcel: dict[str, Any], strings: dict[str, str]) -> str:
    start = parse_timestamp_state(parcel.get("planned_from"))
    end = parse_timestamp_state(parcel.get("planned_to"))
    if start and end:
        return strings["expected_between"].format(
            day=_day_phrase(start, strings),
            start=_format_clock(start),
            end=_format_clock(end),
        )
    if start:
        return strings["expected_around"].format(
            day=_day_phrase(start, strings), start=_format_clock(start)
        )
    status = ParcelStatus(parcel.get("status") or ParcelStatus.UNKNOWN)
    return strings[f"status.{status.value}"]


def _describe_parcel(parcel: dict[str, Any], strings: dict[str, str]) -> str:
    carrier = parcel.get("carrier") or strings["unknown_carrier"]
    sender = parcel.get("sender")
    template_key = "parcel_with_sender" if sender else "parcel_without_sender"
    base = strings[template_key].format(carrier=carrier, sender=sender)
    return f"{base}, {_describe_status_or_window(parcel, strings)}"


def _join_items(items: list[str], strings: dict[str, str]) -> str:
    if len(items) == 1:
        return items[0]
    return f"{'; '.join(items[:-1])} {strings['join_last']} {items[-1]}"


async def describe_bucket(
    hass: HomeAssistant,
    info: dict[str, Any],
    bucket: str,
    *,
    language: str | None = "en",
) -> str:
    """Build a natural-language summary of a bucket's parcel list."""
    strings = await get_assist_strings(hass, language)
    parcels: list[dict[str, Any]] = info.get("parcels", [])
    plural = strings[f"bucket.{bucket}.other"]

    if not parcels:
        return strings["no_parcels"].format(label=plural)

    singular = strings[f"bucket.{bucket}.one"]
    label = singular if len(parcels) == 1 else plural
    items = _join_items([_describe_parcel(p, strings) for p in parcels], strings)
    return strings["summary"].format(count=len(parcels), label=label, items=items)


def get_loaded_coordinator(hass: HomeAssistant) -> ParcelAggregatorCoordinator | None:
    """Return the aggregator's coordinator, if its (single) config entry is loaded."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state is ConfigEntryState.LOADED:
            return entry.runtime_data
    return None


def is_bucket_exposed(hass: HomeAssistant, assistant: str | None, bucket: str) -> bool:
    """Whether the bucket's sensor is exposed to ``assistant``.

    ``assistant`` is ``None`` for direct (non-conversation) intent calls,
    which are already privileged and skip exposure filtering — mirroring how
    ``MatchTargetsConstraints(assistant=None)`` behaves elsewhere in core.
    """
    if assistant is None:
        return True
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{DOMAIN}_{bucket}"
    )
    return entity_id is not None and async_should_expose(hass, assistant, entity_id)


def any_bucket_exposed(hass: HomeAssistant, assistant: str | None) -> bool:
    """Whether at least one bucket sensor is exposed to ``assistant``."""
    return any(is_bucket_exposed(hass, assistant, bucket) for bucket in ASSIST_BUCKETS)
