"""Constants for the Bagwatch integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "bagwatch"

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BUTTON]

CONF_PORTFOLIO_NAME = "portfolio_name"
CONF_PROVIDER = "provider"
CONF_CRYPTO_PRICE_PROVIDER = "crypto_price_provider"
CONF_BASE_CURRENCY = "base_currency"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_PORTFOLIO = "portfolio"
CONF_API_KEY = "api_key"
CONF_COINGECKO_API_KEY = "coingecko_api_key"
CONF_SYMBOL = "symbol"
CONF_NAME = "name"
CONF_ASSET_TYPE = "asset_type"
CONF_QUANTITY = "quantity"
CONF_AVERAGE_BUY_PRICE = "average_buy_price"
CONF_BUY_CURRENCY = "buy_currency"
CONF_COST_BASIS = "cost_basis"
CONF_COST_CURRENCY = "cost_currency"
CONF_COST_BASIS_BASE = "cost_basis_base"
CONF_FEES_TOTAL = "fees_total"
CONF_PROVIDER_SYMBOL = "provider_symbol"
CONF_EXCHANGE = "exchange"
CONF_COUNTRY = "country"
CONF_TRANSACTION_TYPE = "transaction_type"
CONF_TRADE_DATE = "trade_date"
CONF_UNIT_PRICE = "unit_price"
CONF_CURRENCY = "currency"

DEFAULT_PORTFOLIO_NAME = "Portfolio"
DEFAULT_PROVIDER = "yahoo_finance"
DEFAULT_CRYPTO_PRICE_PROVIDER = "primary_only"
DEFAULT_BASE_CURRENCY = "USD"
DEFAULT_SCAN_INTERVAL = 900
DEFAULT_ASSET_TYPE = "stock"
DEFAULT_TRANSACTION_TYPE = "buy"

PROVIDER_TWELVE_DATA = "twelve_data"
PROVIDER_YAHOO_FINANCE = "yahoo_finance"
CRYPTO_PROVIDER_COINGECKO_THEN_PRIMARY = "coingecko_then_primary"
CRYPTO_PROVIDER_PRIMARY_ONLY = "primary_only"
LEGACY_CRYPTO_PROVIDER_COINGECKO_THEN_TWELVE = "coingecko_then_twelve"
LEGACY_CRYPTO_PROVIDER_TWELVE_ONLY = "twelve_data_only"
SUPPORTED_PROVIDERS = [PROVIDER_YAHOO_FINANCE, PROVIDER_TWELVE_DATA]
SUPPORTED_CRYPTO_PRICE_PROVIDERS = [
    CRYPTO_PROVIDER_PRIMARY_ONLY,
    CRYPTO_PROVIDER_COINGECKO_THEN_PRIMARY,
]
SUPPORTED_ASSET_TYPES = ["stock", "etf", "crypto"]
SUPPORTED_TRANSACTION_TYPES = ["buy", "sell"]
TRANSACTION_TYPE_BUY = "buy"
TRANSACTION_TYPE_SELL = "sell"

ATTR_DATA_SOURCE = "data_source"
ATTR_BASE_CURRENCY = "base_currency"
ATTR_QUOTE_CURRENCY = "quote_currency"
ATTR_PRICE_TO_BASE_RATE = "price_to_base_rate"
ATTR_IS_FX_ESTIMATE = "is_fx_estimate"
ATTR_AS_OF = "as_of"
ATTR_POSITION_COUNT = "position_count"
ATTR_TRANSACTION_COUNT = "transaction_count"
ATTR_AVERAGE_COST_BASE = "average_cost_base"
ATTR_LAST_TRADE_DATE = "last_trade_date"
ATTR_IS_CLOSED = "is_closed"
ATTR_PREVIOUS_CLOSE = "previous_close"
ATTR_VOLUME = "volume"
ATTR_MARKET_CAP = "market_cap"
ATTR_DIVIDEND_YIELD = "dividend_yield"
