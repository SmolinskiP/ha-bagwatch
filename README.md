# Home Assistant Bagwatch

Custom integration for Home Assistant that tracks a user-managed portfolio of stocks, ETFs and crypto.

## Current direction

Bagwatch now treats the portfolio as a transaction ledger instead of one static position per symbol.

That means the user:

1. adds the integration and configures the provider
2. adds individual `buy` and `sell` transactions from the integration page
3. gets derived position sensors per asset and portfolio-wide totals
4. can remove an entire position with the `Delete Position` button on the asset device

From that ledger Bagwatch calculates:

- open quantity per asset
- average cost
- open cost basis
- current value
- unrealized P/L
- realized P/L from partial sales

The accounting model is deliberately simple for now:

- no FIFO / LIFO lots
- no dividends yet
- realized P/L is calculated against the current weighted average cost of the open position history

## Current features

- provider setup through Home Assistant UI
- transactions managed as separate Bagwatch items after integration setup
- no hardcoded holdings
- portfolio sensors for current value, open cost basis, unrealized P/L and realized P/L
- per-asset sensors for price, quantity, average cost, current value, unrealized P/L and realized P/L
- per-asset `Delete Position` button that removes all transactions for that symbol
- one provider implementation on start: Twelve Data
- support for stocks, ETFs and crypto
- FX conversion into a chosen base currency
- configurable refresh interval via `scan_interval`

## HACS installation

This repository is prepared for installation as a HACS custom repository.

Requirements from current HACS docs:

- the repository must be public on GitHub
- the repository must contain `README.md`
- the repository must contain `hacs.json`
- the integration files must live under `custom_components/bagwatch/`
- integration repositories must provide `documentation`, `issue_tracker`, `codeowners`, `name`, and `version` in `manifest.json`

Official HACS docs:

- Custom repositories: https://www.hacs.xyz/docs/faq/custom_repositories/
- Integration repository requirements: https://www.hacs.xyz/docs/publish/integration/

### Steps

1. Push this repository to a public GitHub repository.
2. In Home Assistant, open HACS.
3. Open the three-dot menu and choose `Custom repositories`.
4. Paste the GitHub repository URL.
5. Select repository type `Integration`.
6. Install `Bagwatch` from HACS.
7. Restart Home Assistant.
8. Add the integration from `Settings > Devices & services`.
9. Add transactions from the Bagwatch integration page.

## Transaction fields

Each transaction stores:

- `symbol`: user-facing symbol such as `MSFT.US`, `PKN.PL` or `BTC`
- `name`: optional display name for the asset device
- `asset_type`: `stock`, `etf`, or `crypto`
- `transaction_type`: `buy` or `sell`
- `quantity`: trade size
- `unit_price`: executed price per one unit
- `currency`: transaction currency
- `trade_date`: date used to order the ledger
- `fees_total`: optional fees for that trade
- `provider_symbol`: optional exact provider ticker when the display symbol differs from the data provider symbol

## Provider choice

The integration currently starts with Twelve Data because its official docs and pricing cover:

- stocks
- ETFs
- crypto
- forex / exchange rates
- free API keys

Official sources:

- Docs: https://twelvedata.com/docs
- Pricing: https://twelvedata.com/pricing
- Trial / free-plan notes: https://support.twelvedata.com/en/articles/5335783-trial

## FX caveat

If the portfolio base currency differs from the trade currency, Bagwatch currently converts historical transactions using currently fetched FX rates.

That means:

- current market value is correct in the current base-currency view
- historical cost basis and realized P/L can be FX-estimated instead of truly historical
- the entity attribute `is_fx_estimate` is set when this approximation is in play

## Legacy note

Older Bagwatch test versions stored one aggregated position per symbol. The new transaction-ledger version should not be mixed with those old position subentries in the same integration entry.
