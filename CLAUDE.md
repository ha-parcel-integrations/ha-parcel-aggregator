# Working in this repository

Home Assistant custom integration that rolls up parcel counts and next-delivery
timestamps from the DHL, PostNL, DPD, GLS, Dragonfly, Trunkrs and Cainiao
integrations into one set of sensors. Distributed via HACS; not part of HA core.
**Gold** quality tier, minimum HA `2024.7.0`. **Not a carrier** — it consumes the
suite's parcel contract and re-emits it; it has no external API.

## Shared conventions — fetch when relevant

Suite-wide rules live in
[`.github/CONVENTIONS.md`](https://github.com/ha-parcel-integrations/.github/blob/main/CONVENTIONS.md)
and are **not** repeated here. Don't fetch it every session — fetch it **before**
you act in one of these areas:

| Before you … | Fetch `CONVENTIONS.md` § |
|---|---|
| touch entities, sensors, config/options flow, coordinator, diagnostics, **repair issues**, translations | *Home Assistant developer docs* (its table points on to the canonical HA page — don't rely on memory) |
| change how a parcel field, `ParcelStatus`, or a carrier bus event is consumed / re-emitted | *Parcel contract* — the shape and events this repo aggregates; the aggregator re-emits under a unified prefix with `raw` stripped |
| commit, bump, tag, release, or write release notes; add a feature without a test | *Workflow / Commits / Versioning / Testing* |

## Load-bearing decisions — do not refactor away

- **No external API — subscribes to source sensor *state changes***
  (`async_track_state_change_event`), not polling. Freshness is bound to how often
  each carrier polls.
- **Source discovery is event-driven, not per-poll.** `async_setup` discovers once
  (`_refresh_sources`) then listens to `EVENT_ENTITY_REGISTRY_UPDATED`: when a
  known carrier's source sensor is added/removed, discovery re-runs, the
  state-change subscription is rebuilt and the repair issue is created/cleared —
  no manual reload. **Do NOT move discovery onto every poll/compute**; the
  registry listener is the only re-discovery trigger.
- **Source contract — three maps in `const.py` must stay in sync** (adding a
  carrier means updating all three): `KNOWN_CARRIERS` (HA domain → label),
  `SOURCE_SUFFIXES` (`unique_id` suffix → bucket: incoming / outgoing / delivered
  / outgoing_delivered), `ATTR_KEY_BY_BUCKET` (bucket → source attribute key,
  always `parcels`).
- **Longest-suffix matching in `_discover`**: `_outgoing_delivered_parcels` also
  ends with `_delivered_parcels`, so discovery iterates suffixes **longest-first**
  and breaks on first match. Do not revert to dict-order iteration — delivered
  outgoing parcels would be mis-bucketed as incoming delivered.
- **Carrier event re-emit layer.** The coordinator subscribes to every
  `<prefix>_parcel_registered` / `_status_changed` / `_delivered` /
  `_delivery_time_changed` **and** the outgoing pair (`_outgoing_parcel_status_changed`
  / `_outgoing_parcel_delivered`) from carriers in `CARRIER_EVENT_PREFIXES`, and
  re-fires each under the matching `parcel_aggregator_*` name (`EVENT_*` in
  `const.py`). **To onboard a carrier that ships the canonical event contract, add
  its HA domain to `CARRIER_EVENT_PREFIXES` — nothing else.** Account-less carriers
  (GLS, Dragonfly, Trunkrs, Cainiao) never fire the outgoing pair; subscribing to
  an event that never fires is harmless.
- **`strip_raw()` keeps events small** by dropping `raw`. **Per-parcel `history`
  is top-level**, so it survives `strip_raw` and flows through the aggregated
  `parcels` lists and re-emitted events automatically — **do not add `history` to
  `strip_raw`'s drop set**. `history` is `null` unless the source carrier's own
  history option is on.
- **Combined deliveries `calendar`** (`{DOMAIN}_deliveries`): read-only over the
  merged `coordinator.data["incoming"]["parcels"]`, **no own polling**, enabled by
  default. Summary is **carrier-prefixed** (`"DHL: <sender>"`) and `uid` is
  `{carrier}_{barcode}` so the merged agenda stays unambiguous. This is *the*
  cross-carrier calendar; per-carrier repos each ship their own single-account one.
- **Repair issue** (`ir.async_create_issue` / `async_delete_issue`) when no source
  carrier integrations are detected; clears once a carrier appears.
- **Recorder**: list sensors exclude `parcels`/`shipments`; the next-delivery
  sensor excludes its singular `parcel` attribute so the potentially large history
  never hits the recorder DB.
- **Entities**: `has_entity_name` + `translation_key`, `icons.json`, translated
  units (Dutch `pakketten`/`zendingen`); no `_attr_icon` /
  `_attr_native_unit_of_measurement`. Config flow skips the confirm form
  (single-call create). Coordinator takes `config_entry=entry`.

## Deliberately skipped

- **No `_attr_attribution`** — the aggregator talks to no single upstream, so one
  attribution string would mislead; attribution lives on the per-carrier repos.
- **Platinum tier** — needs `mypy --strict` clean + ≥95% coverage; the user chose
  to stop at gold.

## Running tests

```
python -m pytest tests/ --cov=custom_components.parcel_aggregator
```

Coverage must stay **above 95%** (gold-tier target). Run before committing. The
aggregator maps no statuses, so it ships no *Unrecognised parcel status* issue
template.
