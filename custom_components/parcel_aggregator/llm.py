"""LLM tool for the Parcel Aggregator integration.

Wraps the ``ParcelAggregatorGetDetails`` intent (see ``intent.py``) as an
LLM tool via ``IntentTool``, so an LLM-based Assist agent (e.g. OpenAI,
Google Generative AI, or a local LLM configured as the Assist agent) can
call it directly — no custom_sentences setup required, unlike the built-in
Assist agent path. Only advertised when at least one bucket sensor is
exposed to the calling assistant.

Requires the ``<domain>/llm.py`` integration-platform discovery added to HA
core in 2026.8; on older cores this file is simply never imported, so it's
inert rather than breaking anything.
"""
from __future__ import annotations

from homeassistant.components.llm import LLMTools
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import intent
from homeassistant.helpers.llm import LLM_API_ASSIST, IntentTool, LLMContext

from .assist import any_bucket_exposed, get_loaded_coordinator
from .intent import INTENT_GET_PARCEL_DETAILS


@callback
def async_get_tools(
    hass: HomeAssistant, llm_context: LLMContext, api_id: str
) -> LLMTools | None:
    """Return the Parcel Aggregator LLM tool when parcels are exposed."""
    if api_id != LLM_API_ASSIST:
        return None
    if get_loaded_coordinator(hass) is None:
        return None
    if not any_bucket_exposed(hass, llm_context.assistant):
        return None

    handlers = [
        handler
        for handler in intent.async_get(hass)
        if handler.intent_type == INTENT_GET_PARCEL_DETAILS
    ]
    if not handlers:
        return None

    return LLMTools(tools=[IntentTool(INTENT_GET_PARCEL_DETAILS, handlers[0])])
