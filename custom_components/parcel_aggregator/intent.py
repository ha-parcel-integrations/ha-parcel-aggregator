"""Assist intent for natural-language parcel details.

Answers "what is it" style follow-ups (e.g. after "how many packages do I
receive today?") with a spoken summary built from the ``parcels`` attribute,
instead of just the bucket's bare count. Triggered either by the default
(non-LLM) Assist agent via sentences the user installs into
``config/custom_sentences/<lang>/`` (see the README), or automatically by an
LLM-based Assist agent through the wrapper in ``llm.py``.
"""
from __future__ import annotations

from typing import override

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent

from .assist import (
    ASSIST_BUCKETS,
    DEFAULT_ASSIST_BUCKET,
    describe_bucket,
    get_assist_strings,
    get_loaded_coordinator,
    is_bucket_exposed,
)

INTENT_GET_PARCEL_DETAILS = "ParcelAggregatorGetDetails"


async def async_setup_intents(hass: HomeAssistant) -> None:
    """Register the Parcel Aggregator intent handlers."""
    intent.async_register(hass, GetParcelDetailsIntentHandler())


class GetParcelDetailsIntentHandler(intent.IntentHandler):
    """Describe a Parcel Aggregator bucket's parcels in natural language."""

    intent_type = INTENT_GET_PARCEL_DETAILS
    description = (
        "Describe the carrier, sender, status and expected delivery window "
        "of the user's parcels"
    )
    slot_schema = {vol.Optional("bucket"): vol.In(ASSIST_BUCKETS)}

    @override
    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        """Handle the intent."""
        hass = intent_obj.hass
        slots = self.async_validate_slots(intent_obj.slots)
        bucket = slots.get("bucket", {}).get("value", DEFAULT_ASSIST_BUCKET)

        response = intent_obj.create_response()
        response.response_type = intent.IntentResponseType.QUERY_ANSWER

        coordinator = get_loaded_coordinator(hass)
        if coordinator is None:
            strings = await get_assist_strings(hass, intent_obj.language)
            response.async_set_speech(strings["not_set_up"])
            return response

        if not is_bucket_exposed(hass, intent_obj.assistant, bucket):
            strings = await get_assist_strings(hass, intent_obj.language)
            response.async_set_speech(strings["not_exposed"])
            return response

        info = (coordinator.data or {}).get(bucket) or {}
        response.async_set_speech(
            await describe_bucket(hass, info, bucket, language=intent_obj.language)
        )
        return response
