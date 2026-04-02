# Card Examples

This file documents concrete Lovelace card examples for Bagwatch showcase dashboards.

Recommended HACS cards:

- `apexcharts-card`
- `button-card`
- `mini-graph-card`
- `card-mod`

Entity naming used below follows the integration pattern:

- portfolio sensors: `sensor.<portfolio_slug>_<metric_slug>`
- position sensors: `sensor.<position_slug>_<metric_slug>`
- delete buttons: `button.<position_slug>_delete_position`

## Example 1: Portfolio Hero Cards

<img width="456" height="317" alt="image" src="https://github.com/user-attachments/assets/2dea79bc-2ce6-4edc-8e4b-6d7da5ce342a" />

Use this for:

- main README hero image
- two large cards for crypto and stock portfolios
- immediate portfolio value + unrealized percentage at a glance

Cards:

- `sensor.crypto_current_value`
- `sensor.stock_current_value`

```yaml
type: custom:button-card
entity: sensor.crypto_current_value
name: Crypto
icon: mdi:bitcoin
show_state: true
show_label: true
label: >
  [[[ return `U/P ${states['sensor.crypto_unrealized_gain_percentage']?.state ?? 'n/a'}%`; ]]]
styles:
  card:
    - border-radius: 22px
    - padding: 18px
    - min-height: 132px
    - background: linear-gradient(135deg, #0f172a 0%, #1d4ed8 50%, #22c55e 100%)
    - color: white
```

Repeat the same pattern for `sensor.stock_current_value` with a different gradient.

## Example 2: Allocation Donut

<img width="454" height="475" alt="image" src="https://github.com/user-attachments/assets/64dd07f3-9a03-4432-8218-5ce235f54f01" />

Use this for:

- one clean allocation chart
- compact portfolio composition visual
- the same pattern also works for crypto

Cards:

- `sensor.coca_cola_current_value`
- `sensor.microslop_current_value`
- `sensor.orlen_current_value`
- `sensor.pzu_current_value`

```yaml
type: custom:apexcharts-card
chart_type: donut
header:
  show: true
  title: Stock Allocation
  show_states: true
  colorize_states: true
apex_config:
  legend:
    show: true
    position: bottom
  dataLabels:
    enabled: false
  plotOptions:
    pie:
      donut:
        size: 60%
series:
  - entity: sensor.coca_cola_current_value
    name: Coca-Cola
    color: '#ef4444'
  - entity: sensor.microslop_current_value
    name: Microslop
    color: '#3b82f6'
  - entity: sensor.orlen_current_value
    name: Orlen
    color: '#f97316'
  - entity: sensor.pzu_current_value
    name: PZU
    color: '#eab308'
```

## Example 3: Portfolio Value Chart

<img width="457" height="398" alt="image" src="https://github.com/user-attachments/assets/dd435055-bb70-4568-9718-e36f69ff7cf2" />

Use this for:

- 30-day performance overview
- crypto vs stocks line/area comparison

Cards:

- `sensor.crypto_current_value`
- `sensor.stock_current_value`

```yaml
type: custom:apexcharts-card
graph_span: 30d
span:
  end: day
header:
  show: true
  title: Portfolio Value
  show_states: true
  colorize_states: true
all_series_config:
  type: area
  stroke_width: 3
  opacity: 0.18
  group_by:
    func: last
    duration: 1d
series:
  - entity: sensor.crypto_current_value
    name: Crypto
    color: '#22c55e'
  - entity: sensor.stock_current_value
    name: Stocks
    color: '#a855f7'
```

## Example 4: Price Tape Mini Graph

<img width="457" height="214" alt="image" src="https://github.com/user-attachments/assets/4ac4d8b4-a3ba-46b4-94e4-ba1c25068e1e" />

Use this for:

- compact position spotlight cards
- screenshot-friendly per-asset trend previews

Cards:

- `sensor.bitcoin_current_price`

```yaml
type: custom:mini-graph-card
name: Bitcoin Price
entities:
  - entity: sensor.bitcoin_current_price
    name: BTC
hours_to_show: 168
points_per_hour: 0.25
line_width: 3
font_size: 90
animate: true
show:
  fill: fade
  icon: false
  state: true
  points: false
  legend: false
color_thresholds:
  - value: 0
    color: '#f59e0b'
```

Repeat the same pattern for `Kaspa`, `Microslop`, or `Orlen` with different entities and colors.

## Example 5: BTC Price vs Volume

<img width="464" height="431" alt="image" src="https://github.com/user-attachments/assets/7430ec01-4698-472b-a1c5-f68b8122ac2f" />

Use this for:

- a more technical market card
- dual-axis chart combining price and volume

Cards:

- `sensor.bitcoin_current_price`
- `sensor.bitcoin_volume`

```yaml
type: custom:apexcharts-card
graph_span: 7d
header:
  show: true
  title: BTC Price vs Volume
  show_states: true
  colorize_states: true
yaxis:
  - id: left
    decimals: 2
  - id: right
    opposite: true
    decimals: 0
series:
  - entity: sensor.bitcoin_current_price
    name: BTC Price
    yaxis_id: left
    color: '#f59e0b'
    type: line
    stroke_width: 3
  - entity: sensor.bitcoin_volume
    name: BTC Volume
    yaxis_id: right
    color: '#64748b'
    type: column
    opacity: 0.35
```
