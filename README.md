# Bagwatch for Home Assistant

Bagwatch is a Home Assistant integration for tracking stocks, ETFs, and crypto without turning your setup into a spreadsheet graveyard.

It gives you portfolio stats, per-asset sensors, transaction-based tracking, and clean data you can drop straight into dashboards, cards, automations, and statistics views.

If you already live inside Home Assistant, Bagwatch lets your portfolio live there too.

<!-- Suggested screenshot: hero dashboard with portfolio summary and a few asset cards -->

## Key Features

- **Transaction-based tracking** - Add buys and sells instead of manually recalculating positions
- **Portfolio-level statistics** - Current value, open cost basis, realized and unrealized P/L
- **Per-asset entities** - Track each asset separately inside Home Assistant
- **Stocks, ETFs, and crypto** - One integration for the assets most people actually care about
- **Dashboard-ready sensors** - Built to work nicely with cards, charts, statistics, and automations
- **Delete Position action** - Remove a tracked asset cleanly from the device view
- **Base currency support** - Keep portfolio stats in the currency you actually want to see
- **Multi-provider crypto support** - Use CoinGecko for crypto with fallback to Twelve Data
- **Home Assistant-native setup** - Config flow, entities, devices, and HACS-friendly structure

## Why Bagwatch

Most portfolio tools are built as separate apps.

Bagwatch is built for people who want portfolio tracking inside Home Assistant, alongside everything else they already monitor.

Use it to:

- track total portfolio value
- monitor open cost basis
- see unrealized and realized gain / loss
- follow each asset separately
- build custom dashboards with native Home Assistant entities
- manage buys and sells without recalculating average cost by hand

## What it gives you

After setup, Bagwatch creates portfolio-level sensors such as:

- current portfolio value
- open cost basis
- unrealized gain / loss
- realized gain / loss
- open positions count
- transactions count

Each tracked asset also gets its own entities, including:

- current price
- quantity
- average cost
- current value
- unrealized gain / loss
- realized gain / loss

This makes it easy to build anything from a simple summary card to a full-screen finance dashboard.

<!-- Suggested screenshot: asset device page with sensors like current price, quantity, unrealized P/L -->

## How it works

Bagwatch uses a transaction-based model.

You add buy and sell transactions, and Bagwatch calculates the rest from that history:

- open quantity
- average cost
- open cost basis
- unrealized profit / loss
- realized profit / loss

That means the portfolio behaves like something you actually manage, not just a static list of manually edited positions.

## Requirements

Before you start, you need:

- a working Home Assistant instance
- access to HACS or your Home Assistant `config` directory
- a Twelve Data API key
- optionally, a CoinGecko API key for better crypto handling

Bagwatch uses Twelve Data for stocks, ETFs, and FX. For crypto, it can use CoinGecko first and fall back to Twelve Data if needed.

Get your keys here:

- https://twelvedata.com/
- https://www.coingecko.com/en/api

## Installation

### Option 1: HACS

1. Open HACS in Home Assistant.
2. Open `Custom repositories`.
3. Add this repository URL.
4. Select repository type `Integration`.
5. Install `Bagwatch`.
6. Restart Home Assistant.

After the restart, go to `Settings > Devices & services` and add the integration.

<!-- Suggested screenshot: HACS custom repository dialog and Bagwatch install page -->

### Option 2: Manual installation

1. Download this repository.
2. Copy `custom_components/bagwatch` into your Home Assistant `config/custom_components` directory.
3. Restart Home Assistant.
4. Go to `Settings > Devices & services`.
5. Add `Bagwatch`.

Expected structure:

```text
config/
  custom_components/
    bagwatch/
      __init__.py
      manifest.json
      ...
```

## Configuration

1. Add the `Bagwatch` integration from `Settings > Devices & services`.
2. Enter your Twelve Data API key.
3. Choose the crypto price strategy.
4. Optionally enter your CoinGecko API key.
5. Choose the base currency for the portfolio.
6. Set the refresh interval.
7. Finish the integration setup.
8. Open the integration and add transactions one by one.

Each transaction includes:

- symbol
- asset type
- transaction type
- quantity
- unit price
- trade currency
- trade date
- optional fees
- optional display name
- optional provider symbol

For crypto, you can also provide a CoinGecko coin id as `provider_symbol`, using prefixes like `cg:bitcoin`.

Once transactions are added, Bagwatch builds the current portfolio state automatically.

<!-- Suggested screenshot: add transaction flow -->

## Supported assets

Bagwatch currently supports:

- stocks
- ETFs
- crypto

## Built for dashboards

Bagwatch is useful on its own, but it gets much better once you put it on a dashboard.

Good dashboard ideas:

- portfolio summary cards
- current allocation by asset
- winners and losers
- asset detail cards
- long-term charts using Home Assistant statistics

It is meant to give you solid raw entities first, so your dashboard can look exactly how you want instead of how some external app decided it should.

<!-- Suggested screenshot: polished dashboard with stats and charts -->

## Notes

- Bagwatch is focused on practical portfolio tracking inside Home Assistant.
- A tracked asset can be removed using the `Delete Position` action on the asset device.
- The current accounting model is intentionally simple and useful: transaction-based, without turning the integration into accounting software.

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=SmolinskiP/ha-bagwatch&type=Date)](https://star-history.com/#SmolinskiP/ha-bagwatch&Date)

## 📄 License

MIT License. Do whatever you want, just don't blame me when something doesn't work.

## ☕ Support

If the app helped you and you want to buy me a coffee:
[☕ Buy me a coffee](https://buymeacoffee.com/smolinskip)
