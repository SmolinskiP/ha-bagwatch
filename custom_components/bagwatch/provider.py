"""Market data provider clients."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
import time
from typing import Any

from aiohttp import ClientError, ClientSession

from .models import AssetConfig, MarketQuote, ProviderQuery


class MarketDataError(RuntimeError):
    """Raised when a market data provider call fails."""


class TwelveDataClient:
    """Minimal Twelve Data client for quotes and FX."""

    _BASE_URL = "https://api.twelvedata.com"
    _CACHE_TTL_SECONDS = 65.0

    def __init__(self, session: ClientSession, api_key: str) -> None:
        """Initialize the client."""
        self._session = session
        self._api_key = api_key
        self._response_cache: dict[
            tuple[str, tuple[tuple[str, str], ...]],
            tuple[float, dict[str, Any]],
        ] = {}

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
        cache_key = (
            endpoint,
            tuple(
                sorted(
                    (key, str(value))
                    for key, value in clean_params.items()
                    if key != "apikey"
                )
            ),
        )
        now = time.monotonic()
        cached = self._response_cache.get(cache_key)
        if cached is not None and now - cached[0] < self._CACHE_TTL_SECONDS:
            return dict(cached[1])

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

        self._response_cache[cache_key] = (now, dict(payload))
        return payload


class CoinGeckoClient:
    """Minimal CoinGecko client for crypto quotes."""

    _BASE_URL = "https://api.coingecko.com/api/v3"
    _PRICE_CACHE_TTL_SECONDS = 65.0
    _COINS_LIST_CACHE_TTL_SECONDS = 3600.0

    def __init__(self, session: ClientSession, api_key: str | None = None) -> None:
        """Initialize the client."""
        self._session = session
        self._api_key = api_key.strip() if api_key else None
        self._response_cache: dict[
            tuple[str, tuple[tuple[str, str], ...]],
            tuple[float, Any],
        ] = {}

    async def async_get_crypto_quotes(
        self,
        assets: list[AssetConfig],
        *,
        quote_currency: str = "usd",
    ) -> tuple[dict[str, MarketQuote], list[AssetConfig]]:
        """Fetch crypto quotes for assets resolvable by CoinGecko."""
        asset_by_key = {asset.key: asset for asset in assets}
        ids_by_key: dict[str, str] = {}
        unresolved: list[AssetConfig] = []

        for asset in assets:
            coin_id = await self._async_resolve_coin_id(asset)
            if coin_id is None:
                unresolved.append(asset)
                continue
            ids_by_key[asset.key] = coin_id

        if not ids_by_key:
            return {}, unresolved

        requested_ids = sorted(set(ids_by_key.values()))
        payload = await self._async_request(
            "simple/price",
            {
                "ids": ",".join(requested_ids),
                "vs_currencies": quote_currency.lower(),
                "include_last_updated_at": "true",
            },
            ttl_seconds=self._PRICE_CACHE_TTL_SECONDS,
        )

        quotes: dict[str, MarketQuote] = {}
        for asset_key, coin_id in ids_by_key.items():
            coin_payload = payload.get(coin_id)
            if not isinstance(coin_payload, dict):
                unresolved.append(asset_by_key[asset_key])
                continue

            raw_price = coin_payload.get(quote_currency.lower())
            if raw_price is None:
                unresolved.append(asset_by_key[asset_key])
                continue

            try:
                price = Decimal(str(raw_price))
            except (InvalidOperation, TypeError):
                unresolved.append(asset_by_key[asset_key])
                continue

            last_updated_at = coin_payload.get("last_updated_at")
            as_of = None
            if last_updated_at is not None:
                try:
                    as_of = datetime.fromtimestamp(
                        float(last_updated_at), tz=UTC
                    ).isoformat()
                except (TypeError, ValueError, OSError):
                    as_of = None

            quotes[asset_key] = MarketQuote(
                symbol=coin_id,
                price=price,
                currency=quote_currency.upper(),
                exchange="CoinGecko",
                asset_type="Digital Currency",
                as_of=as_of,
            )

        return quotes, unresolved

    async def _async_resolve_coin_id(self, asset: AssetConfig) -> str | None:
        """Resolve a CoinGecko coin id for a crypto asset."""
        lookup = await self._async_get_coin_lookup()

        explicit_id = self._explicit_coin_id(asset)
        if explicit_id and explicit_id in lookup["id_map"]:
            return explicit_id

        symbol_core = asset.symbol.split(".", 1)[0].split("/", 1)[0].strip().lower()
        if symbol_core in lookup["id_map"]:
            return symbol_core

        if symbol_core in lookup["symbol_map"] and len(lookup["symbol_map"][symbol_core]) == 1:
            return lookup["symbol_map"][symbol_core][0]

        if asset.name:
            name_key = asset.name.strip().lower()
            if name_key in lookup["name_map"] and len(lookup["name_map"][name_key]) == 1:
                return lookup["name_map"][name_key][0]

        return None

    def _explicit_coin_id(self, asset: AssetConfig) -> str | None:
        """Extract an explicit CoinGecko id hint from provider_symbol."""
        if not asset.provider_symbol:
            return None
        provider_symbol = asset.provider_symbol.strip().lower()
        for prefix in ("coingecko:", "cg:"):
            if provider_symbol.startswith(prefix):
                coin_id = provider_symbol.removeprefix(prefix).strip()
                return coin_id or None
        return None

    async def _async_get_coin_lookup(self) -> dict[str, Any]:
        """Return cached CoinGecko coin lookup maps."""
        payload = await self._async_request(
            "coins/list",
            {},
            ttl_seconds=self._COINS_LIST_CACHE_TTL_SECONDS,
        )
        if not isinstance(payload, list):
            raise MarketDataError("CoinGecko coins list returned an invalid payload")

        id_map: dict[str, dict[str, str]] = {}
        symbol_map: dict[str, list[str]] = defaultdict(list)
        name_map: dict[str, list[str]] = defaultdict(list)

        for item in payload:
            if not isinstance(item, dict):
                continue
            coin_id = str(item.get("id", "")).strip().lower()
            symbol = str(item.get("symbol", "")).strip().lower()
            name = str(item.get("name", "")).strip().lower()
            if not coin_id:
                continue
            id_map[coin_id] = item
            if symbol:
                symbol_map[symbol].append(coin_id)
            if name:
                name_map[name].append(coin_id)

        return {
            "id_map": id_map,
            "symbol_map": symbol_map,
            "name_map": name_map,
        }

    async def _async_request(
        self,
        endpoint: str,
        params: dict[str, Any],
        *,
        ttl_seconds: float,
    ) -> Any:
        """Perform a GET request against CoinGecko."""
        clean_params = {
            key: value
            for key, value in params.items()
            if value not in (None, "")
        }
        if self._api_key:
            clean_params["x_cg_demo_api_key"] = self._api_key

        cache_key = (
            endpoint,
            tuple(
                sorted(
                    (key, str(value))
                    for key, value in clean_params.items()
                    if key != "x_cg_demo_api_key"
                )
            ),
        )
        now = time.monotonic()
        cached = self._response_cache.get(cache_key)
        if cached is not None and now - cached[0] < ttl_seconds:
            cached_payload = cached[1]
            if isinstance(cached_payload, dict):
                return dict(cached_payload)
            if isinstance(cached_payload, list):
                return list(cached_payload)
            return cached_payload

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
                f"Request to CoinGecko endpoint '{endpoint}' failed"
            ) from err

        self._response_cache[cache_key] = (now, payload)
        if isinstance(payload, dict):
            return dict(payload)
        if isinstance(payload, list):
            return list(payload)
        return payload
