"""Coordinator for Bagwatch."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_BASE_CURRENCY,
    CONF_CRYPTO_PRICE_PROVIDER,
    CONF_PORTFOLIO,
    CONF_PORTFOLIO_NAME,
    CONF_PROVIDER,
    CONF_SCAN_INTERVAL,
    CRYPTO_PROVIDER_COINGECKO_THEN_PRIMARY,
    DEFAULT_BASE_CURRENCY,
    DEFAULT_CRYPTO_PRICE_PROVIDER,
    DEFAULT_PORTFOLIO_NAME,
    DEFAULT_PROVIDER,
    DEFAULT_SCAN_INTERVAL,
    LEGACY_CRYPTO_PROVIDER_COINGECKO_THEN_TWELVE,
    LEGACY_CRYPTO_PROVIDER_TWELVE_ONLY,
    PROVIDER_TWELVE_DATA,
    PROVIDER_YAHOO_FINANCE,
)
from .models import (
    AssetConfig,
    HoldingConfig,
    MarketQuote,
    PortfolioSnapshot,
    PortfolioValidationError,
    TransactionBundle,
    TransactionConfig,
    build_portfolio_snapshot_from_holdings,
    build_portfolio_snapshot_from_transactions,
    group_transactions,
    parse_holdings_data,
    parse_holdings_text,
    parse_transactions_data,
)
from .provider import (
    CoinGeckoClient,
    MarketDataError,
    TwelveDataClient,
    YahooFinanceClient,
)

_LOGGER = logging.getLogger(__name__)
LEGACY_SUBENTRY_TYPE_POSITION = "position"
SUBENTRY_TYPE_TRANSACTION = "transaction"


def _subentry_sort_key(subentry: Any) -> tuple[str, str]:
    """Return a version-safe sorting key for config subentries."""
    created_at = getattr(subentry, "created_at", None)
    modified_at = getattr(subentry, "modified_at", None)
    timestamp = created_at or modified_at
    if isinstance(timestamp, datetime):
        return (timestamp.isoformat(), getattr(subentry, "subentry_id", ""))
    return ("", getattr(subentry, "subentry_id", ""))


def _is_rate_limit_error(err: MarketDataError) -> bool:
    """Return True when a provider rejected the call due to rate limiting."""
    message = str(err).lower()
    return "api credits" in message or "current minute" in message or "rate limit" in message


def _normalize_crypto_price_provider(value: str | None) -> str:
    """Normalize legacy crypto provider strategy values."""
    normalized = (value or DEFAULT_CRYPTO_PRICE_PROVIDER).strip().lower()
    if normalized == LEGACY_CRYPTO_PROVIDER_COINGECKO_THEN_TWELVE:
        return CRYPTO_PROVIDER_COINGECKO_THEN_PRIMARY
    if normalized == LEGACY_CRYPTO_PROVIDER_TWELVE_ONLY:
        return "primary_only"
    return normalized or DEFAULT_CRYPTO_PRICE_PROVIDER


class BagwatchCoordinator(DataUpdateCoordinator[PortfolioSnapshot]):
    """Coordinate market data updates and portfolio calculations."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        twelve_data_client: TwelveDataClient,
        coingecko_client: CoinGeckoClient,
        yahoo_finance_client: YahooFinanceClient,
    ) -> None:
        """Initialize the coordinator."""
        self.config_entry = entry
        self._twelve_data_client = twelve_data_client
        self._coingecko_client = coingecko_client
        self._yahoo_finance_client = yahoo_finance_client
        self._portfolio_name = str(
            self._entry_value(CONF_PORTFOLIO_NAME, DEFAULT_PORTFOLIO_NAME)
        ).strip()
        self._provider = str(self._entry_value(CONF_PROVIDER, DEFAULT_PROVIDER)).strip()
        self._crypto_price_provider = _normalize_crypto_price_provider(
            str(
                self._entry_value(
                    CONF_CRYPTO_PRICE_PROVIDER,
                    DEFAULT_CRYPTO_PRICE_PROVIDER,
                )
            )
        )
        self._base_currency = str(
            self._entry_value(CONF_BASE_CURRENCY, DEFAULT_BASE_CURRENCY)
        ).strip().upper()
        self._scan_interval = max(
            60,
            int(self._entry_value(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
        )

        super().__init__(
            hass,
            _LOGGER,
            name="Bagwatch",
            update_interval=timedelta(seconds=self._scan_interval),
            always_update=False,
        )

    def _entry_value(self, key: str, default: str | int) -> str | int:
        """Read a config value from options or data."""
        return self.config_entry.options.get(key, self.config_entry.data.get(key, default))

    def _transaction_records_from_subentries(self) -> list[dict[str, object]]:
        """Return stored transaction records with deterministic ordering metadata."""
        transaction_subentries = sorted(
            (
                subentry
                for subentry in self.config_entry.subentries.values()
                if subentry.subentry_type == SUBENTRY_TYPE_TRANSACTION
            ),
            key=_subentry_sort_key,
        )
        return [
            dict(subentry.data) | {"_order_index": index}
            for index, subentry in enumerate(transaction_subentries)
        ]

    def _legacy_holdings_from_subentries(self) -> list[HoldingConfig]:
        """Return legacy position subentries, if any."""
        legacy_subentries: list[ConfigSubentry] = [
            subentry
            for subentry in self.config_entry.subentries.values()
            if subentry.subentry_type == LEGACY_SUBENTRY_TYPE_POSITION
        ]
        if not legacy_subentries:
            return []
        return parse_holdings_data([dict(subentry.data) for subentry in legacy_subentries])

    def _load_transactions(self) -> list[TransactionConfig]:
        """Load transactions from subentries."""
        records = self._transaction_records_from_subentries()
        if not records:
            return []
        return parse_transactions_data(records)

    def _load_legacy_holdings(self) -> list[HoldingConfig]:
        """Load holdings from subentries or legacy stored JSON."""
        legacy_holdings = self._legacy_holdings_from_subentries()
        if legacy_holdings:
            return legacy_holdings

        legacy_portfolio = str(self.config_entry.data.get(CONF_PORTFOLIO, "")).strip()
        if legacy_portfolio:
            return parse_holdings_text(legacy_portfolio)

        return []

    def _build_empty_snapshot(self) -> PortfolioSnapshot:
        """Build an empty portfolio snapshot when no data exists yet."""
        return PortfolioSnapshot(
            name=self._portfolio_name,
            base_currency=self._base_currency,
            updated_at=datetime.now(UTC),
            positions=[],
            market_value_base=Decimal("0"),
            cost_basis_base=Decimal("0"),
            unrealized_gain_base=Decimal("0"),
            unrealized_gain_pct=None,
            realized_gain_base=Decimal("0"),
            realized_gain_pct=None,
            open_positions_count=0,
            transaction_count=0,
        )

    def get_configured_assets(self) -> list[AssetConfig]:
        """Return configured assets even when the latest snapshot could not price them."""
        try:
            transactions = self._load_transactions()
            if transactions:
                return [bundle.asset for bundle in group_transactions(transactions)]

            legacy_holdings = self._load_legacy_holdings()
            if legacy_holdings:
                return [holding.to_asset_config() for holding in legacy_holdings]
        except PortfolioValidationError as err:
            _LOGGER.warning("Failed to resolve configured assets for Bagwatch entities: %s", err)

        if self.data is not None:
            return [position.asset for position in self.data.positions]
        return []

    async def _async_update_data(self) -> PortfolioSnapshot:
        """Fetch the latest data and build a portfolio snapshot."""
        try:
            transactions = self._load_transactions()
            legacy_holdings = self._load_legacy_holdings()

            if transactions and legacy_holdings:
                raise PortfolioValidationError(
                    "Bagwatch cannot mix legacy positions with the new transaction ledger"
                )

            if transactions:
                bundles = group_transactions(transactions)
                quotes = await self._async_fetch_quotes_for_assets(
                    [bundle.asset for bundle in bundles]
                )
                bundles = [
                    bundle for bundle in bundles if bundle.asset.key in quotes
                ]
                if not bundles:
                    _LOGGER.warning(
                        "No valid asset quotes available for the current Bagwatch transaction ledger"
                    )
                    return self._build_empty_snapshot()
                fx_rates = await self._async_fetch_fx_rates_for_transactions(
                    bundles,
                    quotes,
                )
                return build_portfolio_snapshot_from_transactions(
                    name=self._portfolio_name,
                    base_currency=self._base_currency,
                    bundles=bundles,
                    quotes=quotes,
                    fx_rates=fx_rates,
                )

            if legacy_holdings:
                quotes = await self._async_fetch_quotes_for_holdings(legacy_holdings)
                legacy_holdings = [
                    holding for holding in legacy_holdings if holding.key in quotes
                ]
                if not legacy_holdings:
                    _LOGGER.warning(
                        "No valid asset quotes available for the current Bagwatch legacy holdings"
                    )
                    return self._build_empty_snapshot()
                fx_rates = await self._async_fetch_fx_rates_for_holdings(
                    legacy_holdings,
                    quotes,
                )
                return build_portfolio_snapshot_from_holdings(
                    name=self._portfolio_name,
                    base_currency=self._base_currency,
                    holdings=legacy_holdings,
                    quotes=quotes,
                    fx_rates=fx_rates,
                )

            return self._build_empty_snapshot()
        except PortfolioValidationError as err:
            raise UpdateFailed(str(err)) from err
        except MarketDataError as err:
            if _is_rate_limit_error(err) and self.data is not None:
                _LOGGER.warning(
                    "Market data rate limit hit; keeping the last successful Bagwatch snapshot: %s",
                    err,
                )
                return self.data
            raise UpdateFailed(str(err)) from err

    async def _async_fetch_quotes_for_assets(
        self,
        assets: list[AssetConfig],
    ) -> dict[str, MarketQuote]:
        """Fetch quotes with provider routing and crypto fallback."""
        quotes: dict[str, MarketQuote] = {}
        primary_assets: list[AssetConfig] = [
            asset for asset in assets if asset.asset_type != "crypto"
        ]
        crypto_assets: list[AssetConfig] = [
            asset for asset in assets if asset.asset_type == "crypto"
        ]

        if (
            crypto_assets
            and self._crypto_price_provider == CRYPTO_PROVIDER_COINGECKO_THEN_PRIMARY
        ):
            try:
                coingecko_quotes, unresolved_assets = await self._coingecko_client.async_get_crypto_quotes(
                    crypto_assets,
                    quote_currency="usd",
                )
                quotes.update(coingecko_quotes)
                primary_assets.extend(unresolved_assets)
                if unresolved_assets:
                    _LOGGER.info(
                        "CoinGecko could not resolve %s crypto asset(s); falling back to the selected primary provider",
                        len(unresolved_assets),
                    )
            except MarketDataError as err:
                _LOGGER.warning(
                    "CoinGecko crypto fetch failed, falling back to the selected primary provider: %s",
                    err,
                )
                primary_assets.extend(crypto_assets)
        else:
            primary_assets.extend(crypto_assets)

        if primary_assets:
            quotes.update(await self._async_fetch_primary_quotes(primary_assets))

        return quotes

    async def _async_fetch_primary_quotes(
        self,
        assets: list[AssetConfig],
    ) -> dict[str, MarketQuote]:
        """Fetch quotes from the configured primary provider."""
        if not assets:
            return {}

        if self._provider == PROVIDER_TWELVE_DATA:
            tasks = [
                self._twelve_data_client.async_get_quote(asset.to_provider_query())
                for asset in assets
            ]
        elif self._provider == PROVIDER_YAHOO_FINANCE:
            tasks = [
                self._yahoo_finance_client.async_get_quote(asset)
                for asset in assets
            ]
        else:
            raise MarketDataError(f"Unsupported provider configured: {self._provider}")

        results = await asyncio.gather(*tasks, return_exceptions=True)
        quotes: dict[str, MarketQuote] = {}
        for asset, result in zip(assets, results, strict=True):
            if isinstance(result, Exception):
                _LOGGER.warning(
                    "Skipping asset '%s' because quote fetch failed: %s",
                    asset.display_name,
                    result,
                )
                continue
            quotes[asset.key] = result

        return quotes

    async def _async_fetch_quotes_for_holdings(
        self,
        holdings: list[HoldingConfig],
    ) -> dict[str, MarketQuote]:
        """Fetch quotes for legacy holdings."""
        assets = [holding.to_asset_config() for holding in holdings]
        return await self._async_fetch_quotes_for_assets(assets)

    async def _async_fetch_fx_rates_for_transactions(
        self,
        bundles: list[TransactionBundle],
        quotes: dict[str, MarketQuote],
    ) -> dict[tuple[str, str], Decimal]:
        """Fetch FX rates needed for transaction-ledger calculations."""
        fx_rates: dict[tuple[str, str], Decimal] = {
            (self._base_currency, self._base_currency): Decimal("1")
        }
        pairs_to_fetch: set[tuple[str, str]] = set()

        for bundle in bundles:
            quote_currency = quotes[bundle.asset.key].currency.upper()
            if quote_currency != self._base_currency:
                pairs_to_fetch.add((quote_currency, self._base_currency))

            for transaction in bundle.transactions:
                if transaction.currency != self._base_currency:
                    pairs_to_fetch.add((transaction.currency, self._base_currency))

        if not pairs_to_fetch:
            return fx_rates

        tasks = [
            self._async_get_exchange_rate(source, target)
            for source, target in pairs_to_fetch
        ]
        results = await asyncio.gather(*tasks)
        for pair, rate in zip(pairs_to_fetch, results, strict=True):
            fx_rates[pair] = rate

        return fx_rates

    async def _async_fetch_fx_rates_for_holdings(
        self,
        holdings: list[HoldingConfig],
        quotes: dict[str, MarketQuote],
    ) -> dict[tuple[str, str], Decimal]:
        """Fetch FX rates needed for legacy holding calculations."""
        fx_rates: dict[tuple[str, str], Decimal] = {
            (self._base_currency, self._base_currency): Decimal("1")
        }
        pairs_to_fetch: set[tuple[str, str]] = set()

        for holding in holdings:
            quote_currency = quotes[holding.key].currency.upper()
            if quote_currency != self._base_currency:
                pairs_to_fetch.add((quote_currency, self._base_currency))

            if holding.cost_basis_base is not None:
                continue

            cost_currency = holding.cost_currency or holding.buy_currency or quote_currency
            if cost_currency != self._base_currency:
                pairs_to_fetch.add((cost_currency, self._base_currency))

        if not pairs_to_fetch:
            return fx_rates

        tasks = [
            self._async_get_exchange_rate(source, target)
            for source, target in pairs_to_fetch
        ]
        results = await asyncio.gather(*tasks)
        for pair, rate in zip(pairs_to_fetch, results, strict=True):
            fx_rates[pair] = rate

        return fx_rates

    async def _async_get_exchange_rate(
        self,
        source_currency: str,
        target_currency: str,
    ) -> Decimal:
        """Fetch FX using the selected primary provider."""
        if self._provider == PROVIDER_TWELVE_DATA:
            return await self._twelve_data_client.async_get_exchange_rate(
                source_currency,
                target_currency,
            )
        if self._provider == PROVIDER_YAHOO_FINANCE:
            return await self._yahoo_finance_client.async_get_exchange_rate(
                source_currency,
                target_currency,
            )
        raise MarketDataError(f"Unsupported provider configured: {self._provider}")
