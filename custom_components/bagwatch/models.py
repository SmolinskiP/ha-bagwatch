"""Portfolio models, validation and calculations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
import json
import re
from typing import Any


class PortfolioValidationError(ValueError):
    """Raised when the user portfolio configuration is invalid."""


def _to_decimal(value: Any, field_name: str) -> Decimal:
    """Convert a raw value to Decimal."""
    if value is None:
        raise PortfolioValidationError(f"Missing numeric value for '{field_name}'")

    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError) as err:
        raise PortfolioValidationError(
            f"Invalid numeric value for '{field_name}': {value!r}"
        ) from err


def _optional_decimal(value: Any, field_name: str) -> Decimal | None:
    """Convert an optional raw value to Decimal."""
    if value is None:
        return None
    return _to_decimal(value, field_name)


def _normalize_currency(value: str | None) -> str | None:
    """Normalize a currency code."""
    if value is None:
        return None
    normalized = value.strip().upper()
    return normalized or None


def _normalize_asset_type(value: str | None) -> str:
    """Normalize the asset type."""
    if value is None:
        return "other"

    normalized = value.strip().lower()
    aliases = {
        "equity": "stock",
        "share": "stock",
        "shares": "stock",
        "coin": "crypto",
        "cryptocurrency": "crypto",
        "fund": "etf",
        "index": "benchmark",
    }
    return aliases.get(normalized, normalized)


def _slugify(value: str) -> str:
    """Create a stable slug for entity IDs."""
    slug = re.sub(r"[^a-z0-9]+", "_", value.strip().lower())
    return slug.strip("_") or "position"


def _provider_asset_type(asset_type: str) -> str | None:
    """Map local asset types to Twelve Data type hints."""
    mapping = {
        "stock": "Common Stock",
        "etf": "ETF",
        "crypto": "Digital Currency",
    }
    return mapping.get(asset_type)


@dataclass(slots=True, frozen=True)
class ProviderQuery:
    """Provider-specific symbol query."""

    symbol: str
    exchange: str | None = None
    country: str | None = None
    asset_type_hint: str | None = None


@dataclass(slots=True, frozen=True)
class HoldingConfig:
    """Normalized user holding."""

    symbol: str
    quantity: Decimal
    average_buy_price: Decimal | None
    buy_currency: str | None
    cost_basis: Decimal | None
    cost_currency: str | None
    cost_basis_base: Decimal | None
    fees_total: Decimal
    asset_type: str
    name: str | None
    provider_symbol: str | None
    exchange: str | None
    country: str | None

    @property
    def key(self) -> str:
        """Return a stable internal key."""
        return self.symbol.upper()

    @property
    def unique_id_suffix(self) -> str:
        """Return a stable suffix for entity unique IDs."""
        return _slugify(self.symbol)

    @property
    def display_name(self) -> str:
        """Return a human-readable name."""
        return self.name or self.symbol

    def to_provider_query(self) -> ProviderQuery:
        """Convert the user symbol to a provider query."""
        if self.provider_symbol:
            return ProviderQuery(
                symbol=self.provider_symbol,
                exchange=self.exchange,
                country=self.country,
                asset_type_hint=_provider_asset_type(self.asset_type),
            )

        symbol = self.symbol.strip()
        symbol_upper = symbol.upper()

        if self.asset_type == "crypto" and "/" not in symbol_upper:
            return ProviderQuery(
                symbol=f"{symbol_upper}/USD",
                exchange=self.exchange,
                country=self.country,
                asset_type_hint="Digital Currency",
            )

        if "." in symbol:
            ticker, suffix = symbol.rsplit(".", 1)
            suffix = suffix.upper()
            inferred_country = {
                "US": "United States",
                "PL": "Poland",
                "DE": "Germany",
                "UK": "United Kingdom",
                "NL": "Netherlands",
                "FR": "France",
            }.get(suffix)
            return ProviderQuery(
                symbol=ticker.upper(),
                exchange=self.exchange,
                country=self.country or inferred_country,
                asset_type_hint=_provider_asset_type(self.asset_type),
            )

        if " " in symbol:
            raise PortfolioValidationError(
                f"Position '{symbol}' requires 'provider_symbol' because the symbol contains spaces"
            )

        return ProviderQuery(
            symbol=symbol_upper,
            exchange=self.exchange,
            country=self.country,
            asset_type_hint=_provider_asset_type(self.asset_type),
        )

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "HoldingConfig":
        """Create a holding from raw JSON data."""
        symbol = str(raw.get("symbol", "")).strip()
        if not symbol:
            raise PortfolioValidationError("Each holding requires a non-empty 'symbol'")

        quantity = _to_decimal(raw.get("quantity"), f"{symbol}.quantity")
        if quantity <= 0:
            raise PortfolioValidationError(f"Position '{symbol}' must have quantity > 0")

        average_buy_price = _optional_decimal(
            raw.get("average_buy_price"),
            f"{symbol}.average_buy_price",
        )
        cost_basis = _optional_decimal(raw.get("cost_basis"), f"{symbol}.cost_basis")
        cost_basis_base = _optional_decimal(
            raw.get("cost_basis_base"),
            f"{symbol}.cost_basis_base",
        )
        fees_total = _optional_decimal(raw.get("fees_total"), f"{symbol}.fees_total")
        fees_total = fees_total or Decimal("0")

        if (
            average_buy_price is None
            and cost_basis is None
            and cost_basis_base is None
        ):
            raise PortfolioValidationError(
                f"Position '{symbol}' requires one of: average_buy_price, cost_basis, cost_basis_base"
            )

        return cls(
            symbol=symbol,
            quantity=quantity,
            average_buy_price=average_buy_price,
            buy_currency=_normalize_currency(raw.get("buy_currency")),
            cost_basis=cost_basis,
            cost_currency=_normalize_currency(raw.get("cost_currency")),
            cost_basis_base=cost_basis_base,
            fees_total=fees_total,
            asset_type=_normalize_asset_type(raw.get("asset_type")),
            name=str(raw["name"]).strip() if raw.get("name") else None,
            provider_symbol=str(raw["provider_symbol"]).strip()
            if raw.get("provider_symbol")
            else None,
            exchange=str(raw["exchange"]).strip() if raw.get("exchange") else None,
            country=str(raw["country"]).strip() if raw.get("country") else None,
        )


@dataclass(slots=True, frozen=True)
class MarketQuote:
    """Latest quote for a holding."""

    symbol: str
    price: Decimal
    currency: str
    exchange: str | None = None
    asset_type: str | None = None
    as_of: str | None = None


@dataclass(slots=True, frozen=True)
class PositionSnapshot:
    """Calculated snapshot for a single holding."""

    holding: HoldingConfig
    quote: MarketQuote
    price_to_base_rate: Decimal
    cost_to_base_rate: Decimal | None
    current_price_base: Decimal
    market_value_base: Decimal
    cost_basis_base: Decimal
    unrealized_gain_base: Decimal
    unrealized_gain_pct: Decimal | None
    is_fx_estimate: bool


@dataclass(slots=True, frozen=True)
class PortfolioSnapshot:
    """Calculated snapshot for the full portfolio."""

    name: str
    base_currency: str
    updated_at: datetime
    positions: list[PositionSnapshot]
    market_value_base: Decimal
    cost_basis_base: Decimal
    unrealized_gain_base: Decimal
    unrealized_gain_pct: Decimal | None


def parse_holdings_text(text: str) -> list[HoldingConfig]:
    """Parse and validate holdings JSON."""
    if not text or not text.strip():
        raise PortfolioValidationError("Portfolio JSON cannot be empty")

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as err:
        raise PortfolioValidationError(f"Portfolio JSON is invalid: {err.msg}") from err

    if isinstance(payload, dict):
        raw_holdings = payload.get("holdings")
    else:
        raw_holdings = payload

    if not isinstance(raw_holdings, list) or not raw_holdings:
        raise PortfolioValidationError(
            "Portfolio JSON must be a non-empty array or an object with a 'holdings' array"
        )

    holdings: list[HoldingConfig] = []
    seen_symbols: set[str] = set()
    for raw_holding in raw_holdings:
        if not isinstance(raw_holding, dict):
            raise PortfolioValidationError("Each holding must be a JSON object")

        holding = HoldingConfig.from_dict(raw_holding)
        symbol_key = holding.key
        if symbol_key in seen_symbols:
            raise PortfolioValidationError(
                f"Duplicate symbol '{holding.symbol}'. Merge lots into a single aggregated position."
            )
        seen_symbols.add(symbol_key)
        holdings.append(holding)

    return holdings


def _get_fx_rate(
    source_currency: str,
    target_currency: str,
    fx_rates: dict[tuple[str, str], Decimal],
) -> Decimal:
    """Resolve FX rate for a currency pair."""
    if source_currency == target_currency:
        return Decimal("1")

    pair = (source_currency, target_currency)
    if pair not in fx_rates:
        raise PortfolioValidationError(
            f"Missing FX rate from {source_currency} to {target_currency}"
        )
    return fx_rates[pair]


def build_portfolio_snapshot(
    *,
    name: str,
    base_currency: str,
    holdings: list[HoldingConfig],
    quotes: dict[str, MarketQuote],
    fx_rates: dict[tuple[str, str], Decimal],
) -> PortfolioSnapshot:
    """Build a calculated portfolio snapshot."""
    positions: list[PositionSnapshot] = []
    market_value_total = Decimal("0")
    cost_basis_total = Decimal("0")

    for holding in holdings:
        if holding.key not in quotes:
            raise PortfolioValidationError(
                f"Missing quote for position '{holding.display_name}'"
            )

        quote = quotes[holding.key]
        quote_currency = _normalize_currency(quote.currency)
        if quote_currency is None:
            raise PortfolioValidationError(
                f"Missing quote currency for position '{holding.display_name}'"
            )

        price_to_base_rate = _get_fx_rate(quote_currency, base_currency, fx_rates)
        current_price_base = quote.price * price_to_base_rate
        market_value_base = holding.quantity * current_price_base

        if holding.cost_basis_base is not None:
            cost_basis_base = holding.cost_basis_base
            cost_to_base_rate = None
            is_fx_estimate = False
        else:
            cost_currency = holding.cost_currency or holding.buy_currency or quote_currency
            cost_to_base_rate = _get_fx_rate(cost_currency, base_currency, fx_rates)
            native_cost = (
                holding.cost_basis
                if holding.cost_basis is not None
                else (holding.quantity * holding.average_buy_price) + holding.fees_total
            )
            cost_basis_base = native_cost * cost_to_base_rate
            is_fx_estimate = cost_currency != base_currency

        unrealized_gain_base = market_value_base - cost_basis_base
        unrealized_gain_pct = (
            (unrealized_gain_base / cost_basis_base) * Decimal("100")
            if cost_basis_base != 0
            else None
        )

        positions.append(
            PositionSnapshot(
                holding=holding,
                quote=quote,
                price_to_base_rate=price_to_base_rate,
                cost_to_base_rate=cost_to_base_rate,
                current_price_base=current_price_base,
                market_value_base=market_value_base,
                cost_basis_base=cost_basis_base,
                unrealized_gain_base=unrealized_gain_base,
                unrealized_gain_pct=unrealized_gain_pct,
                is_fx_estimate=is_fx_estimate,
            )
        )
        market_value_total += market_value_base
        cost_basis_total += cost_basis_base

    unrealized_gain_total = market_value_total - cost_basis_total
    unrealized_gain_pct_total = (
        (unrealized_gain_total / cost_basis_total) * Decimal("100")
        if cost_basis_total != 0
        else None
    )

    return PortfolioSnapshot(
        name=name,
        base_currency=base_currency,
        updated_at=datetime.now(UTC),
        positions=positions,
        market_value_base=market_value_total,
        cost_basis_base=cost_basis_total,
        unrealized_gain_base=unrealized_gain_total,
        unrealized_gain_pct=unrealized_gain_pct_total,
    )
