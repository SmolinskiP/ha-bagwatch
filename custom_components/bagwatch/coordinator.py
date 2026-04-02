"""Coordinator for Bagwatch."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from decimal import Decimal
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_BASE_CURRENCY,
    CONF_PORTFOLIO,
    CONF_PORTFOLIO_NAME,
    CONF_PROVIDER,
    CONF_SCAN_INTERVAL,
    DEFAULT_BASE_CURRENCY,
    DEFAULT_PORTFOLIO_NAME,
    DEFAULT_PROVIDER,
    DEFAULT_SCAN_INTERVAL,
)
from .models import (
    HoldingConfig,
    MarketQuote,
    PortfolioSnapshot,
    PortfolioValidationError,
    build_portfolio_snapshot,
    parse_holdings_text,
)
from .provider import MarketDataError, TwelveDataClient

_LOGGER = logging.getLogger(__name__)


class BagwatchCoordinator(DataUpdateCoordinator[PortfolioSnapshot]):
    """Coordinate market data updates and portfolio calculations."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: TwelveDataClient,
    ) -> None:
        """Initialize the coordinator."""
        self.config_entry = entry
        self._client = client
        self._portfolio_name = str(
            self._entry_value(CONF_PORTFOLIO_NAME, DEFAULT_PORTFOLIO_NAME)
        ).strip()
        self._provider = str(self._entry_value(CONF_PROVIDER, DEFAULT_PROVIDER)).strip()
        self._base_currency = str(
            self._entry_value(CONF_BASE_CURRENCY, DEFAULT_BASE_CURRENCY)
        ).strip().upper()
        self._portfolio_text = str(self._entry_value(CONF_PORTFOLIO, "")).strip()
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

    async def _async_update_data(self) -> PortfolioSnapshot:
        """Fetch the latest data and build a portfolio snapshot."""
        if self._provider != DEFAULT_PROVIDER:
            raise UpdateFailed(f"Unsupported provider configured: {self._provider}")

        try:
            holdings = parse_holdings_text(self._portfolio_text)
            quotes = await self._async_fetch_quotes(holdings)
            fx_rates = await self._async_fetch_fx_rates(holdings, quotes)
            return build_portfolio_snapshot(
                name=self._portfolio_name,
                base_currency=self._base_currency,
                holdings=holdings,
                quotes=quotes,
                fx_rates=fx_rates,
            )
        except (PortfolioValidationError, MarketDataError) as err:
            raise UpdateFailed(str(err)) from err

    async def _async_fetch_quotes(
        self,
        holdings: list[HoldingConfig],
    ) -> dict[str, MarketQuote]:
        """Fetch quotes for all holdings."""
        tasks = [self._client.async_get_quote(holding.to_provider_query()) for holding in holdings]
        results = await asyncio.gather(*tasks)
        return {
            holding.key: quote
            for holding, quote in zip(holdings, results, strict=True)
        }

    async def _async_fetch_fx_rates(
        self,
        holdings: list[HoldingConfig],
        quotes: dict[str, MarketQuote],
    ) -> dict[tuple[str, str], Decimal]:
        """Fetch FX rates needed to convert all values into the base currency."""
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

            cost_currency = (
                holding.cost_currency
                or holding.buy_currency
                or quote_currency
            )
            if cost_currency != self._base_currency:
                pairs_to_fetch.add((cost_currency, self._base_currency))

        tasks = [
            self._client.async_get_exchange_rate(source, target)
            for source, target in pairs_to_fetch
        ]
        results = await asyncio.gather(*tasks)
        for pair, rate in zip(pairs_to_fetch, results, strict=True):
            fx_rates[pair] = rate

        return fx_rates


