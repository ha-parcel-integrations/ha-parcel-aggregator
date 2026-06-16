# Parcel Aggregator

A Home Assistant custom integration that rolls up parcel counts and next-delivery timestamps from the DHL, PostNL, and DPD integrations into a single set of sensors.

## Use cases

- A single dashboard card that shows how many parcels you expect today across DHL, PostNL and DPD without juggling per-carrier sensors.
- Automations like *"announce when a parcel is awaiting pickup at a service point"* or *"remind me an hour before the earliest delivery"* that you write once and they cover every carrier.
- A unified parcel list you can iterate over in templates or custom cards.

## How it works

This integration does **not** talk to any carrier API directly. It reads the state of entities that other parcel-tracking integrations already publish, and exposes aggregated sensors with a per-carrier breakdown on the attributes. If a carrier integration is not installed, it's silently skipped — install only what you need.

## How updates work

The aggregator is event-driven, not polling. At setup time it discovers source sensors from the installed carrier integrations and subscribes to their state-change events. Whenever any carrier sensor updates, the aggregator recomputes its sensors immediately. This means the aggregator's freshness is bound to how often each carrier integration polls (typically every 5–15 minutes).

If you install a new carrier integration after Parcel Aggregator was set up, **reload Parcel Aggregator** (Settings → Devices & Services → Parcel Aggregator → ⋮ → Reload) so it picks up the new source sensors.

## Supported sources

| Integration | Repository |
|-------------|-----------|
| DHL NL | [peternijssen/ha-dhl-nl](https://github.com/peternijssen/ha-dhl-nl) |
| PostNL | [peternijssen/ha-postnl](https://github.com/peternijssen/ha-postnl) |
| DPD | [peternijssen/ha-dpd](https://github.com/peternijssen/ha-dpd) |

## Requirements

- Home Assistant 2024.1 or newer
- At least one of the supported carrier integrations installed and authenticated

## Installation

### HACS (recommended)

1. Open HACS → **Integrations** → ⋮ → **Custom repositories**
2. Add this repository URL and select category **Integration**
3. Search for **Parcel Aggregator** and install it
4. Restart Home Assistant

### Manual

1. Copy the `parcel_aggregator` folder into your `config/custom_components/` directory
2. Restart Home Assistant

## Configuration

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **Parcel Aggregator**
3. Click **Submit** — no credentials needed

The aggregator discovers source entities at setup time. If you add a new carrier integration later, **reload Parcel Aggregator** to pick it up.

## Sensors

| Entity | Description |
|--------|-------------|
| `sensor.parcels_incoming` | Sum of active incoming parcels across all carriers; merged parcel list on the `parcels` attribute |
| `sensor.parcels_outgoing` | Sum of active outgoing shipments across all carriers; merged list on the `shipments` attribute |
| `sensor.parcels_delivered` | Sum of recently delivered parcels across all carriers (uses each carrier's own filter window); merged list on `parcels` |
| `sensor.parcels_awaiting_pickup` | Sum of active incoming parcels destined for a pickup point (ServicePoint / PostNL Point / ParcelShop); merged list on `parcels` |
| `sensor.parcels_next_delivery` | Earliest expected delivery datetime across all carriers; the matching parcel on the `parcel` attribute |

Every sensor exposes a `by_carrier` attribute with the per-carrier breakdown — handy for dashboard cards like "5 incoming (2 DHL · 3 PostNL)".

### Unified parcel list

The `parcels` / `shipments` attribute on each summary sensor contains every parcel from every installed carrier in the carrier-agnostic shape: `carrier`, `barcode`, `sender`, `status`, `delivered`, `delivered_at`, `planned_from`, `planned_to`, `pickup`, `pickup_point`, `url`. The carrier-specific `raw` payload is stripped to keep the aggregator's attribute size small — open the per-carrier sensor if you need it.

## Example automations

### Announce that a parcel is ready for pickup

```yaml
automation:
  - alias: "Parcel ready for pickup"
    trigger:
      platform: numeric_state
      entity_id: sensor.parcel_aggregator_awaiting_pickup
      above: 0
    action:
      service: notify.mobile_app
      data:
        title: "Parcel ready for pickup"
        message: >
          {{ state_attr('sensor.parcel_aggregator_awaiting_pickup', 'parcels')
             | map(attribute='sender') | join(', ') }}
```

### Notify one hour before the next delivery

```yaml
automation:
  - alias: "Delivery in 1 hour"
    trigger:
      platform: template
      value_template: >
        {% set when = states('sensor.parcel_aggregator_next_delivery') %}
        {% if when not in ('unknown', 'unavailable') %}
          {{ (as_datetime(when) - now()).total_seconds() | int == 3600 }}
        {% endif %}
    action:
      service: notify.mobile_app
      data:
        message: "Parcel arrives within an hour."
```

## Known limitations

- The aggregator only discovers source sensors **at setup time**. Install a new carrier integration → reload Parcel Aggregator before its sensors appear.
- The `next_delivery` timestamp is only as precise as the underlying carrier exposes. DPD for example only gives a date (midnight in the parcel's timezone), so use it for "today/tomorrow" alerts rather than precise hour windows.
- The `pickup` attribute is built from each carrier's location type and may lag the actual pickup-point status — DPD specifically cannot yet tell *en route* apart from *arrived at ParcelShop*.

## Disclaimer

This is an independent, community-built project with no affiliation, endorsement, or connection to DHL, PostNL, DPD, or any of their subsidiaries.

## Contributing

Pull requests and issues are welcome. Please open an issue before submitting a large change.

## License

MIT
