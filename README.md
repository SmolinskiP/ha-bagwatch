# Home Assistant Bagwatch

Custom integration for Home Assistant that tracks user-managed portfolio positions for stocks, ETFs and crypto.

## Current MVP

This version provides:

- provider setup through Home Assistant UI
- positions managed as separate Bagwatch items after integration setup
- no hardcoded holdings
- total portfolio sensors
- per-position sensors
- one provider implementation on start: Twelve Data
- support for stocks, ETFs and crypto
- FX conversion into a chosen base currency
- configurable refresh interval via `scan_interval`

## How configuration works now

Bagwatch is split into two layers:

- the main integration stores provider settings such as API key, base currency and refresh interval
- each portfolio position is added separately after setup as its own Bagwatch position

This means the user flow is now:

1. add the Bagwatch integration
2. configure provider settings
3. open the integration and add positions one by one
4. each position stores symbol, quantity, buy price and optional provider hints

This is the intended direction for the integration because positions are not part of one huge blob anymore.

## HACS installation

This repository is prepared for installation as a HACS custom repository.

Requirements from current HACS docs:

- the repository must be public on GitHub
- the repository must contain `README.md`
- the repository must contain `hacs.json`
- the integration files must live under `custom_components/bagwatch/`
- integration repositories must provide `documentation`, `issue_tracker`, `codeowners`, `name`, and `version` in `manifest.json`
- integration repositories should provide brand assets

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
9. Add positions from the Bagwatch integration page.

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

Important limitation of the free plan according to Twelve Data's official pricing/support pages:

- Basic plan is free
- Basic includes `8 API credits per minute` and `800 per day`
- Basic includes real-time US equities and ETFs, real-time forex, and real-time crypto
- Basic is limited to `3 markets`
- broader international coverage is part of higher tiers

Practical implication:

- US stocks and crypto are a good fit for the free tier
- symbols from markets such as Poland may work only as trial symbols or may require a paid plan depending on coverage
- because of that, the integration supports `provider_symbol`, `exchange`, and `country` hints

## Position fields

Each position can store:

- `symbol`: user-facing symbol such as `MSFT.US`, `PKN.PL` or `BTC`
- `name`: optional display name
- `asset_type`: for example `stock`, `etf`, `crypto`
- `quantity`: position size
- `average_buy_price`: average buy price per unit
- `buy_currency`: currency for `average_buy_price`
- `cost_basis`: optional total position cost instead of `quantity * average_buy_price`
- `cost_currency`: currency for `cost_basis`
- `cost_basis_base`: optional exact total cost already expressed in portfolio base currency
- `fees_total`: optional fees added to cost basis
- `provider_symbol`: optional exact provider symbol when user-facing symbol differs
- `exchange`: optional provider hint
- `country`: optional provider hint

## FX caveat

Exact P/L in the portfolio base currency is only truly exact when one of these is provided:

- `cost_basis_base`
- cost data already stored in the same base currency

If the user provides only purchase data in another currency, the integration converts cost using current FX. In that case the entity attribute `is_fx_estimate` is set to `true`.
