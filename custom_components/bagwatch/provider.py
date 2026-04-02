"""Market data provider clients."""

from __future__ import annotations

import asyncio
from decimal import Decimal, InvalidOperation
from typing import Any

from aiohttp import ClientError, ClientSession

from .models import MarketQuote, ProviderQuery


class MarketDataError(RuntimeError):
    """Raised when a market data provider call fails."""


class TwelveDataClient:
    """Minimal Twelve Data client for quotes and FX."""

    _BASE_URL = "https://api.twelvedata.com"

    def __init__(self, session: ClientSession, api_key: str) -> None:
        """Initialize the client."""
        self._session = session
        self._api_key = api_key

    async def async_get_quote(self, query: ProviderQuery) -> MarketQuote:
        """Fetch the latest quote for a symbol."""
        payload = await self._async_request(
            "quote",
            {
                "symbol": query.symbol,
                "exchange": query.exchange,
                "country": query.country,
                "type": query.asset_type_hint,
            },
        )

        raw_price = payload.get("price") or payload.get("close")
        if raw_price is None:
            raise MarketDataError(f"No price returned for symbol '{query.symbol}'")

        try:
            price = Decimal(str(raw_price))
        except (InvalidOperation, TypeError) as err:
            raise MarketDataError(
                f"Invalid price returned for symbol '{query.symbol}': {raw_price!r}"
            ) from err

        currency = str(payload.get("currency") or "USD").upper()
        return MarketQuote(
            symbol=query.symbol,
            price=price,
            currency=currency,
            exchange=payload.get("exchange"),
            asset_type=payload.get("type"),
            as_of=payload.get("datetime"),
        )

    async def async_get_exchange_rate(
        self,
        source_currency: str,
        target_currency: str,
    ) -> Decimal:
        """Fetch an FX rate for a currency pair."""
        if source_currency == target_currency:
            return Decimal("1")

        payload = await self._async_request(
            "exchange_rate",
            {"symbol": f"{source_currency}/{target_currency}"},
        )

        raw_rate = payload.get("rate") or payload.get("exchange_rate")
        if raw_rate is None:
            raise MarketDataError(
                f"No FX rate returned for pair '{source_currency}/{target_currency}'"
            )

        try:
            return Decimal(str(raw_rate))
        except (InvalidOperation, TypeError) as err:
            raise MarketDataError(
                f"Invalid FX rate returned for pair '{source_currency}/{target_currency}'"
            ) from err

    async def _async_request(
        self,
        endpoint: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """Perform a GET request against Twelve Data."""
        clean_params = {
            key: value
            for key, value in params.items()
            if value not in (None, "")
        }
        clean_params["apikey"] = self._api_key

        try:
            async with asyncio.timeout(20):
                async with self._session.get(
                    f"{self._BASE_URL}/{endpoint}",
                    params=clean_params,
                ) as response:
                    response.raise_for_status()
                    payload = await response.json()
        except (TimeoutError, ClientError, ValueError) as err:
            raise MarketDataError(
                f"Request to Twelve Data endpoint '{endpoint}' failed"
            ) from err

        if payload.get("status") == "error":
            raise MarketDataError(
                payload.get("message")
                or payload.get("code")
                or f"Twelve Data returned an error for '{endpoint}'"
            )

        return payload
