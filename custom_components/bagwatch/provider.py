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

try:
    import yfinance as yf
except ImportError:  # pragma: no cover - runtime dependency in Home Assistant
    yf = None


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
            previous_close=self._optional_decimal(
                payload.get("previous_close") or payload.get("previousClose")
            ),
            volume=self._optional_int(payload.get("volume")),
            market_cap=self._optional_decimal(
                payload.get("market_cap") or payload.get("marketCap")
            ),
            dividend_yield=self._optional_percentage(
                payload.get("dividend_yield") or payload.get("dividendYield")
            ),
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

    def _optional_decimal(self, value: Any) -> Decimal | None:
        """Convert an optional numeric provider field into Decimal."""
        if value in (None, ""):
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, TypeError):
            return None

    def _optional_int(self, value: Any) -> int | None:
        """Convert an optional numeric provider field into int."""
        if value in (None, ""):
            return None
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None

    def _optional_percentage(self, value: Any) -> Decimal | None:
        """Normalize optional percentage-like fields into percent units."""
        numeric = self._optional_decimal(value)
        if numeric is None:
            return None
        return numeric * Decimal("100") if Decimal("0") < numeric <= Decimal("1") else numeric


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
                "include_market_cap": "true",
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
                market_cap=self._optional_decimal(
                    coin_payload.get(f"{quote_currency.lower()}_market_cap")
                ),
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

    def _optional_decimal(self, value: Any) -> Decimal | None:
        """Convert an optional numeric provider field into Decimal."""
        if value in (None, ""):
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, TypeError):
            return None


class YahooFinanceClient:
    """Experimental Yahoo Finance client powered by yfinance."""

    _CACHE_TTL_SECONDS = 65.0
    _SUFFIX_MAP = {
        "US": "",
        "PL": ".WA",
        "UK": ".L",
        "NL": ".AS",
        "FR": ".PA",
        "DE": ".DE",
    }

    def __init__(self) -> None:
        """Initialize the client."""
        self._response_cache: dict[tuple[str, str], tuple[float, Any]] = {}

    async def async_get_quote(self, asset: AssetConfig) -> MarketQuote:
        """Fetch the latest quote for an asset via Yahoo Finance."""
        yahoo_symbol = self._resolve_symbol(asset)
        cache_key = ("quote", yahoo_symbol)
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        payload = await asyncio.to_thread(self._sync_get_quote_payload, asset, yahoo_symbol)
        self._response_cache[cache_key] = (time.monotonic(), payload)
        return payload

    async def async_get_exchange_rate(
        self,
        source_currency: str,
        target_currency: str,
    ) -> Decimal:
        """Fetch an FX rate via Yahoo Finance."""
        if source_currency == target_currency:
            return Decimal("1")

        yahoo_symbol = f"{source_currency.upper()}{target_currency.upper()}=X"
        cache_key = ("fx", yahoo_symbol)
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        rate = await asyncio.to_thread(
            self._sync_get_exchange_rate,
            yahoo_symbol,
            source_currency.upper(),
            target_currency.upper(),
        )
        self._response_cache[cache_key] = (time.monotonic(), rate)
        return rate

    def _get_cached(self, cache_key: tuple[str, str]) -> Any | None:
        """Return a cached response when it is still fresh."""
        cached = self._response_cache.get(cache_key)
        if cached is None:
            return None
        if time.monotonic() - cached[0] >= self._CACHE_TTL_SECONDS:
            return None
        return cached[1]

    def _sync_get_quote_payload(
        self,
        asset: AssetConfig,
        yahoo_symbol: str,
    ) -> MarketQuote:
        """Resolve a Yahoo quote synchronously inside the executor."""
        ticker = self._ticker(yahoo_symbol)
        raw_price: Any = None
        currency: str | None = None
        exchange: str | None = None
        asset_type: str | None = None
        as_of: str | None = None

        fast_info = self._safe_mapping(getattr(ticker, "fast_info", None))
        if fast_info:
            raw_price = self._first_value(
                fast_info.get("lastPrice"),
                fast_info.get("regularMarketPrice"),
                fast_info.get("previousClose"),
            )
            currency = self._normalize_text(fast_info.get("currency"))
            exchange = self._normalize_text(fast_info.get("exchange"))

        info = self._safe_mapping(getattr(ticker, "info", None))
        if info:
            raw_price = self._first_value(
                raw_price,
                info.get("regularMarketPrice"),
                info.get("currentPrice"),
                info.get("previousClose"),
                info.get("navPrice"),
            )
            currency = currency or self._normalize_text(info.get("currency"))
            exchange = exchange or self._normalize_text(
                info.get("fullExchangeName") or info.get("exchange")
            )
            asset_type = self._normalize_text(info.get("quoteType"))

        history = ticker.history(period="5d", interval="1d", auto_adjust=False, actions=False)
        if hasattr(history, "empty") and not history.empty:
            latest_row = history.iloc[-1]
            raw_price = self._first_value(raw_price, latest_row.get("Close"))
            latest_index = history.index[-1]
            if hasattr(latest_index, "to_pydatetime"):
                latest_dt = latest_index.to_pydatetime()
                if latest_dt.tzinfo is None:
                    latest_dt = latest_dt.replace(tzinfo=UTC)
                as_of = latest_dt.isoformat()

        if raw_price is None:
            raise MarketDataError(f"No Yahoo Finance price returned for symbol '{yahoo_symbol}'")

        try:
            price = Decimal(str(raw_price))
        except (InvalidOperation, TypeError) as err:
            raise MarketDataError(
                f"Invalid Yahoo Finance price returned for symbol '{yahoo_symbol}': {raw_price!r}"
            ) from err

        if currency is None:
            currency = "USD"

        previous_close = self._first_decimal(
            fast_info.get("regularMarketPreviousClose"),
            fast_info.get("previousClose"),
            info.get("previousClose"),
            history.iloc[-2].get("Close")
            if hasattr(history, "empty") and getattr(history, "shape", (0, 0))[0] >= 2
            else None,
        )
        volume = self._first_int(
            history.iloc[-1].get("Volume")
            if hasattr(history, "empty") and not history.empty
            else None,
            fast_info.get("lastVolume"),
            info.get("volume"),
        )
        market_cap = self._first_decimal(
            fast_info.get("marketCap"),
            info.get("marketCap"),
        )
        dividend_yield = self._normalize_dividend_yield(
            info.get("dividendYield"),
            info.get("trailingAnnualDividendYield"),
        )

        return MarketQuote(
            symbol=yahoo_symbol,
            price=price,
            currency=currency.upper(),
            exchange=exchange or "Yahoo Finance",
            asset_type=asset_type,
            as_of=as_of,
            previous_close=previous_close,
            volume=volume,
            market_cap=market_cap,
            dividend_yield=dividend_yield,
        )

    def _sync_get_exchange_rate(
        self,
        yahoo_symbol: str,
        source_currency: str,
        target_currency: str,
    ) -> Decimal:
        """Resolve a Yahoo FX rate synchronously inside the executor."""
        quote = self._sync_get_quote_payload(
            AssetConfig(
                symbol=f"{source_currency}/{target_currency}",
                asset_type="forex",
                name=None,
                provider_symbol=yahoo_symbol,
                exchange=None,
                country=None,
            ),
            yahoo_symbol,
        )
        return quote.price

    def _ticker(self, symbol: str):
        """Return a yfinance ticker instance or raise a clear error."""
        if yf is None:
            raise MarketDataError(
                "Yahoo Finance support requires the optional 'yfinance' package"
            )
        try:
            return yf.Ticker(symbol)
        except Exception as err:  # pragma: no cover - library-specific failures
            raise MarketDataError(
                f"Failed to initialize Yahoo Finance ticker '{symbol}'"
            ) from err

    def _resolve_symbol(self, asset: AssetConfig) -> str:
        """Resolve the symbol format expected by Yahoo Finance."""
        explicit = self._explicit_provider_symbol(asset.provider_symbol)
        if explicit:
            return explicit

        if asset.asset_type == "crypto":
            symbol_core = asset.symbol.split(".", 1)[0].split("/", 1)[0].split("-", 1)[0]
            return f"{symbol_core.strip().upper()}-USD"

        symbol = asset.symbol.strip().upper()
        if " " in symbol:
            raise MarketDataError(
                f"Asset '{asset.symbol}' requires a Yahoo-specific provider symbol"
            )

        if "." in symbol:
            ticker, suffix = symbol.rsplit(".", 1)
            mapped_suffix = self._SUFFIX_MAP.get(suffix.upper())
            if mapped_suffix is not None:
                return f"{ticker.upper()}{mapped_suffix}"

        return symbol

    def _explicit_provider_symbol(self, provider_symbol: str | None) -> str | None:
        """Extract a Yahoo-specific provider symbol hint when present."""
        if not provider_symbol:
            return None
        cleaned = provider_symbol.strip()
        lowered = cleaned.lower()
        if lowered.startswith(("cg:", "coingecko:")):
            return None
        for prefix in ("yahoo:", "yf:"):
            if lowered.startswith(prefix):
                explicit = cleaned[len(prefix):].strip()
                return explicit or None
        return cleaned or None

    def _safe_mapping(self, payload: Any) -> dict[str, Any] | None:
        """Return a dict-like payload if one is available."""
        if payload is None:
            return None
        if isinstance(payload, dict):
            return payload
        try:
            return dict(payload)
        except (TypeError, ValueError):
            return None

    def _first_value(self, *values: Any) -> Any:
        """Return the first usable value from a list of candidates."""
        for value in values:
            if value not in (None, ""):
                return value
        return None

    def _normalize_text(self, value: Any) -> str | None:
        """Normalize optional textual payload values."""
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None

    def _first_decimal(self, *values: Any) -> Decimal | None:
        """Return the first value that can be parsed as Decimal."""
        for value in values:
            decimal_value = self._to_decimal(value)
            if decimal_value is not None:
                return decimal_value
        return None

    def _first_int(self, *values: Any) -> int | None:
        """Return the first value that can be parsed as int."""
        for value in values:
            int_value = self._to_int(value)
            if int_value is not None:
                return int_value
        return None

    def _to_decimal(self, value: Any) -> Decimal | None:
        """Parse optional numerics into Decimal, ignoring invalid payloads."""
        if value in (None, ""):
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, TypeError):
            return None

    def _to_int(self, value: Any) -> int | None:
        """Parse optional numerics into int, ignoring invalid payloads."""
        if value in (None, ""):
            return None
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None

    def _normalize_dividend_yield(
        self,
        dividend_yield: Any,
        trailing_dividend_yield: Any,
    ) -> Decimal | None:
        """Normalize Yahoo dividend yield values into percent units."""
        primary = self._to_decimal(dividend_yield)
        if primary is not None:
            return primary

        trailing = self._to_decimal(trailing_dividend_yield)
        if trailing is None:
            return None
        return trailing * Decimal("100") if Decimal("0") < trailing <= Decimal("1") else trailing

    def _optional_decimal(self, value: Any) -> Decimal | None:
        """Alias for optional decimal parsing."""
        return self._to_decimal(value)
