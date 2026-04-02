"""Constants for the Bagwatch integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "bagwatch"

PLATFORMS: list[Platform] = [Platform.SENSOR]

CONF_PORTFOLIO_NAME = "portfolio_name"
CONF_PROVIDER = "provider"
CONF_BASE_CURRENCY = "base_currency"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_PORTFOLIO = "portfolio"
CONF_API_KEY = "api_key"
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

DEFAULT_PORTFOLIO_NAME = "Portfolio"
DEFAULT_PROVIDER = "twelve_data"
DEFAULT_BASE_CURRENCY = "USD"
DEFAULT_SCAN_INTERVAL = 900
DEFAULT_ASSET_TYPE = "stock"

PROVIDER_TWELVE_DATA = "twelve_data"
SUPPORTED_PROVIDERS = [PROVIDER_TWELVE_DATA]
SUPPORTED_ASSET_TYPES = ["stock", "etf", "crypto"]

ATTR_DATA_SOURCE = "data_source"
ATTR_BASE_CURRENCY = "base_currency"
ATTR_QUOTE_CURRENCY = "quote_currency"
ATTR_COST_CURRENCY = "cost_currency"
ATTR_PRICE_TO_BASE_RATE = "price_to_base_rate"
ATTR_COST_TO_BASE_RATE = "cost_to_base_rate"
ATTR_IS_FX_ESTIMATE = "is_fx_estimate"
ATTR_AS_OF = "as_of"
ATTR_POSITION_COUNT = "position_count"
