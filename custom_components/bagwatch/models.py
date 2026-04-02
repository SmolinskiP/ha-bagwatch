"""Portfolio models, validation and calculations."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
import json
import re
from typing import Any

try:
    from .const import (
        TRANSACTION_TYPE_BUY,
        TRANSACTION_TYPE_SELL,
    )
except ImportError:
    TRANSACTION_TYPE_BUY = "buy"
    TRANSACTION_TYPE_SELL = "sell"


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
        return "stock"

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


def _normalize_transaction_type(value: str | None) -> str:
    """Normalize the transaction type."""
    if value is None:
        return TRANSACTION_TYPE_BUY
    normalized = value.strip().lower()
    if normalized not in (TRANSACTION_TYPE_BUY, TRANSACTION_TYPE_SELL):
        raise PortfolioValidationError(f"Unsupported transaction type: {value}")
    return normalized


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


def _parse_trade_date(value: Any, field_name: str) -> date:
    """Parse a trade date from HA form data."""
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if value is None:
        raise PortfolioValidationError(f"Missing value for '{field_name}'")

    try:
        return date.fromisoformat(str(value))
    except ValueError as err:
        raise PortfolioValidationError(
            f"Invalid date value for '{field_name}': {value!r}"
        ) from err


@dataclass(slots=True, frozen=True)
class ProviderQuery:
    """Provider-specific symbol query."""

    symbol: str
    exchange: str | None = None
    country: str | None = None
    asset_type_hint: str | None = None


@dataclass(slots=True, frozen=True)
class AssetConfig:
    """Normalized asset metadata derived from transactions."""

    symbol: str
    asset_type: str
    name: str | None
    provider_symbol: str | None
    exchange: str | None = None
    country: str | None = None

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
                f"Asset '{symbol}' requires 'provider_symbol' because the symbol contains spaces"
            )

        return ProviderQuery(
            symbol=symbol_upper,
            exchange=self.exchange,
            country=self.country,
            asset_type_hint=_provider_asset_type(self.asset_type),
        )


@dataclass(slots=True, frozen=True)
class TransactionConfig:
    """Normalized user transaction."""

    symbol: str
    transaction_type: str
    quantity: Decimal
    unit_price: Decimal
    currency: str
    trade_date: date
    fees_total: Decimal
    asset_type: str | None = None
    name: str | None = None
    provider_symbol: str | None = None
    exchange: str | None = None
    country: str | None = None
    order_index: int = 0

    @property
    def key(self) -> str:
        """Return a stable internal key."""
        return self.symbol.upper()

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "TransactionConfig":
        """Create a transaction from raw data."""
        symbol = str(raw.get("symbol", "")).strip()
        if not symbol:
            raise PortfolioValidationError("Each transaction requires a non-empty 'symbol'")

        quantity = _to_decimal(raw.get("quantity"), f"{symbol}.quantity")
        if quantity <= 0:
            raise PortfolioValidationError(f"Transaction '{symbol}' must have quantity > 0")

        unit_price = _to_decimal(raw.get("unit_price"), f"{symbol}.unit_price")
        if unit_price < 0:
            raise PortfolioValidationError(
                f"Transaction '{symbol}' must have unit_price >= 0"
            )

        currency = _normalize_currency(raw.get("currency"))
        if currency is None:
            raise PortfolioValidationError(f"Transaction '{symbol}' requires 'currency'")

        fees_total = _optional_decimal(raw.get("fees_total"), f"{symbol}.fees_total")
        fees_total = fees_total or Decimal("0")
        if fees_total < 0:
            raise PortfolioValidationError(
                f"Transaction '{symbol}' must have fees_total >= 0"
            )

        return cls(
            symbol=symbol,
            transaction_type=_normalize_transaction_type(raw.get("transaction_type")),
            quantity=quantity,
            unit_price=unit_price,
            currency=currency,
            trade_date=_parse_trade_date(raw.get("trade_date"), f"{symbol}.trade_date"),
            fees_total=fees_total,
            asset_type=_normalize_asset_type(raw.get("asset_type"))
            if raw.get("asset_type")
            else None,
            name=str(raw["name"]).strip() if raw.get("name") else None,
            provider_symbol=str(raw["provider_symbol"]).strip()
            if raw.get("provider_symbol")
            else None,
            exchange=str(raw["exchange"]).strip() if raw.get("exchange") else None,
            country=str(raw["country"]).strip() if raw.get("country") else None,
            order_index=int(raw.get("_order_index", 0)),
        )


@dataclass(slots=True, frozen=True)
class HoldingConfig:
    """Legacy normalized user holding."""

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
    def display_name(self) -> str:
        """Return a human-readable name."""
        return self.name or self.symbol

    def to_asset_config(self) -> AssetConfig:
        """Convert the holding metadata into an asset config."""
        return AssetConfig(
            symbol=self.symbol,
            asset_type=self.asset_type,
            name=self.name,
            provider_symbol=self.provider_symbol,
            exchange=self.exchange,
            country=self.country,
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
    previous_close: Decimal | None = None
    volume: int | None = None
    market_cap: Decimal | None = None
    dividend_yield: Decimal | None = None


@dataclass(slots=True, frozen=True)
class PositionSnapshot:
    """Calculated snapshot for a single tracked asset."""

    asset: AssetConfig
    quote: MarketQuote
    price_to_base_rate: Decimal
    current_price_base: Decimal
    quantity: Decimal
    average_cost_base: Decimal | None
    market_value_base: Decimal
    cost_basis_base: Decimal
    unrealized_gain_base: Decimal
    unrealized_gain_pct: Decimal | None
    realized_gain_base: Decimal
    realized_gain_pct: Decimal | None
    realized_cost_basis_base: Decimal
    total_fees_base: Decimal
    transaction_count: int
    last_trade_date: date
    is_fx_estimate: bool
    is_closed: bool


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
    realized_gain_base: Decimal
    realized_gain_pct: Decimal | None
    open_positions_count: int
    transaction_count: int


@dataclass(slots=True, frozen=True)
class TransactionBundle:
    """Transactions grouped by symbol with resolved asset metadata."""

    asset: AssetConfig
    transactions: list[TransactionConfig]


def parse_transactions_data(raw_transactions: list[dict[str, Any]]) -> list[TransactionConfig]:
    """Parse and validate transaction data."""
    if not isinstance(raw_transactions, list) or not raw_transactions:
        raise PortfolioValidationError("Portfolio must contain at least one transaction")

    transactions: list[TransactionConfig] = []
    for raw_transaction in raw_transactions:
        if not isinstance(raw_transaction, dict):
            raise PortfolioValidationError("Each transaction must be an object")
        transactions.append(TransactionConfig.from_dict(raw_transaction))
    return transactions


def _resolve_asset_metadata(transactions: list[TransactionConfig]) -> AssetConfig:
    """Resolve one asset definition from many transactions."""
    if not transactions:
        raise PortfolioValidationError("Asset metadata resolution requires transactions")

    symbol = transactions[0].symbol
    asset_type: str | None = None
    provider_symbol: str | None = None
    exchange: str | None = None
    country: str | None = None
    name: str | None = None

    for transaction in transactions:
        if transaction.asset_type:
            if asset_type is None:
                asset_type = transaction.asset_type
            elif asset_type != transaction.asset_type:
                raise PortfolioValidationError(
                    f"Conflicting asset_type values for '{symbol}'"
                )

        if transaction.provider_symbol:
            if provider_symbol is None:
                provider_symbol = transaction.provider_symbol
            elif provider_symbol != transaction.provider_symbol:
                raise PortfolioValidationError(
                    f"Conflicting provider_symbol values for '{symbol}'"
                )

        if transaction.exchange:
            if exchange is None:
                exchange = transaction.exchange
            elif exchange != transaction.exchange:
                raise PortfolioValidationError(
                    f"Conflicting exchange values for '{symbol}'"
                )

        if transaction.country:
            if country is None:
                country = transaction.country
            elif country != transaction.country:
                raise PortfolioValidationError(
                    f"Conflicting country values for '{symbol}'"
                )

        if transaction.name:
            name = transaction.name

    return AssetConfig(
        symbol=symbol,
        asset_type=asset_type or "stock",
        name=name,
        provider_symbol=provider_symbol,
        exchange=exchange,
        country=country,
    )


def group_transactions(transactions: list[TransactionConfig]) -> list[TransactionBundle]:
    """Group transactions per asset and validate partial sells."""
    if not transactions:
        raise PortfolioValidationError("Portfolio must contain at least one transaction")

    grouped: dict[str, list[TransactionConfig]] = defaultdict(list)
    for transaction in transactions:
        grouped[transaction.key].append(transaction)

    bundles: list[TransactionBundle] = []
    for symbol_transactions in grouped.values():
        ordered_transactions = sorted(
            symbol_transactions,
            key=lambda transaction: (
                transaction.trade_date,
                transaction.order_index,
                transaction.transaction_type,
            ),
        )

        open_quantity = Decimal("0")
        for transaction in ordered_transactions:
            if transaction.transaction_type == TRANSACTION_TYPE_BUY:
                open_quantity += transaction.quantity
                continue

            if transaction.quantity > open_quantity:
                raise PortfolioValidationError(
                    f"Sell transaction for '{transaction.symbol}' exceeds the available quantity"
                )
            open_quantity -= transaction.quantity

        bundles.append(
            TransactionBundle(
                asset=_resolve_asset_metadata(ordered_transactions),
                transactions=ordered_transactions,
            )
        )

    return sorted(bundles, key=lambda bundle: bundle.asset.display_name.lower())


def parse_holdings_data(raw_holdings: list[dict[str, Any]]) -> list[HoldingConfig]:
    """Parse and validate legacy holdings from Python data."""
    if not isinstance(raw_holdings, list) or not raw_holdings:
        raise PortfolioValidationError("Portfolio must contain at least one position")

    holdings: list[HoldingConfig] = []
    seen_symbols: set[str] = set()
    for raw_holding in raw_holdings:
        if not isinstance(raw_holding, dict):
            raise PortfolioValidationError("Each holding must be an object")

        holding = HoldingConfig.from_dict(raw_holding)
        symbol_key = holding.key
        if symbol_key in seen_symbols:
            raise PortfolioValidationError(
                f"Duplicate symbol '{holding.symbol}'. Merge lots into a single aggregated position."
            )
        seen_symbols.add(symbol_key)
        holdings.append(holding)

    return holdings


def serialize_holdings(raw_holdings: list[dict[str, Any]]) -> str:
    """Serialize holdings into the stored JSON format."""
    parse_holdings_data(raw_holdings)
    return json.dumps(raw_holdings)


def parse_holdings_text(text: str) -> list[HoldingConfig]:
    """Parse and validate legacy holdings JSON."""
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

    return parse_holdings_data(raw_holdings)


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


def build_portfolio_snapshot_from_transactions(
    *,
    name: str,
    base_currency: str,
    bundles: list[TransactionBundle],
    quotes: dict[str, MarketQuote],
    fx_rates: dict[tuple[str, str], Decimal],
) -> PortfolioSnapshot:
    """Build a calculated portfolio snapshot from transactions."""
    positions: list[PositionSnapshot] = []
    market_value_total = Decimal("0")
    cost_basis_total = Decimal("0")
    realized_gain_total = Decimal("0")
    realized_cost_total = Decimal("0")

    for bundle in bundles:
        if bundle.asset.key not in quotes:
            raise PortfolioValidationError(
                f"Missing quote for asset '{bundle.asset.display_name}'"
            )

        quote = quotes[bundle.asset.key]
        quote_currency = _normalize_currency(quote.currency)
        if quote_currency is None:
            raise PortfolioValidationError(
                f"Missing quote currency for asset '{bundle.asset.display_name}'"
            )

        price_to_base_rate = _get_fx_rate(quote_currency, base_currency, fx_rates)
        current_price_base = quote.price * price_to_base_rate

        quantity = Decimal("0")
        open_cost_base = Decimal("0")
        realized_gain_base = Decimal("0")
        realized_cost_basis_base = Decimal("0")
        total_fees_base = Decimal("0")
        is_fx_estimate = False

        for transaction in bundle.transactions:
            tx_rate = _get_fx_rate(transaction.currency, base_currency, fx_rates)
            gross_base = transaction.quantity * transaction.unit_price * tx_rate
            fees_base = transaction.fees_total * tx_rate
            total_fees_base += fees_base
            if transaction.currency != base_currency:
                is_fx_estimate = True

            if transaction.transaction_type == TRANSACTION_TYPE_BUY:
                quantity += transaction.quantity
                open_cost_base += gross_base + fees_base
                continue

            if quantity <= 0:
                raise PortfolioValidationError(
                    f"Sell transaction for '{transaction.symbol}' has no open quantity"
                )

            average_cost_base = open_cost_base / quantity
            cost_of_sale_base = average_cost_base * transaction.quantity
            proceeds_base = gross_base - fees_base
            realized_gain_base += proceeds_base - cost_of_sale_base
            realized_cost_basis_base += cost_of_sale_base
            quantity -= transaction.quantity
            open_cost_base -= cost_of_sale_base
            if quantity == 0:
                open_cost_base = Decimal("0")

        average_cost_base = open_cost_base / quantity if quantity > 0 else None
        market_value_base = quantity * current_price_base
        unrealized_gain_base = market_value_base - open_cost_base
        unrealized_gain_pct = (
            (unrealized_gain_base / open_cost_base) * Decimal("100")
            if open_cost_base != 0
            else None
        )
        realized_gain_pct = (
            (realized_gain_base / realized_cost_basis_base) * Decimal("100")
            if realized_cost_basis_base != 0
            else None
        )

        positions.append(
            PositionSnapshot(
                asset=bundle.asset,
                quote=quote,
                price_to_base_rate=price_to_base_rate,
                current_price_base=current_price_base,
                quantity=quantity,
                average_cost_base=average_cost_base,
                market_value_base=market_value_base,
                cost_basis_base=open_cost_base,
                unrealized_gain_base=unrealized_gain_base,
                unrealized_gain_pct=unrealized_gain_pct,
                realized_gain_base=realized_gain_base,
                realized_gain_pct=realized_gain_pct,
                realized_cost_basis_base=realized_cost_basis_base,
                total_fees_base=total_fees_base,
                transaction_count=len(bundle.transactions),
                last_trade_date=bundle.transactions[-1].trade_date,
                is_fx_estimate=is_fx_estimate,
                is_closed=quantity == 0,
            )
        )
        market_value_total += market_value_base
        cost_basis_total += open_cost_base
        realized_gain_total += realized_gain_base
        realized_cost_total += realized_cost_basis_base

    unrealized_gain_total = market_value_total - cost_basis_total
    unrealized_gain_pct_total = (
        (unrealized_gain_total / cost_basis_total) * Decimal("100")
        if cost_basis_total != 0
        else None
    )
    realized_gain_pct_total = (
        (realized_gain_total / realized_cost_total) * Decimal("100")
        if realized_cost_total != 0
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
        realized_gain_base=realized_gain_total,
        realized_gain_pct=realized_gain_pct_total,
        open_positions_count=sum(1 for position in positions if position.quantity > 0),
        transaction_count=sum(position.transaction_count for position in positions),
    )


def build_portfolio_snapshot_from_holdings(
    *,
    name: str,
    base_currency: str,
    holdings: list[HoldingConfig],
    quotes: dict[str, MarketQuote],
    fx_rates: dict[tuple[str, str], Decimal],
) -> PortfolioSnapshot:
    """Build a calculated snapshot from legacy aggregated holdings."""
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
        average_cost_base = (
            cost_basis_base / holding.quantity if holding.quantity != 0 else None
        )
        transaction_date = datetime.now(UTC).date()

        positions.append(
            PositionSnapshot(
                asset=holding.to_asset_config(),
                quote=quote,
                price_to_base_rate=price_to_base_rate,
                current_price_base=current_price_base,
                quantity=holding.quantity,
                average_cost_base=average_cost_base,
                market_value_base=market_value_base,
                cost_basis_base=cost_basis_base,
                unrealized_gain_base=unrealized_gain_base,
                unrealized_gain_pct=unrealized_gain_pct,
                realized_gain_base=Decimal("0"),
                realized_gain_pct=None,
                realized_cost_basis_base=Decimal("0"),
                total_fees_base=holding.fees_total,
                transaction_count=1,
                last_trade_date=transaction_date,
                is_fx_estimate=is_fx_estimate,
                is_closed=False,
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
        realized_gain_base=Decimal("0"),
        realized_gain_pct=None,
        open_positions_count=len(positions),
        transaction_count=len(positions),
    )


def build_portfolio_snapshot(
    *,
    name: str,
    base_currency: str,
    holdings: list[HoldingConfig],
    quotes: dict[str, MarketQuote],
    fx_rates: dict[tuple[str, str], Decimal],
) -> PortfolioSnapshot:
    """Backward-compatible wrapper for legacy holdings snapshots."""
    return build_portfolio_snapshot_from_holdings(
        name=name,
        base_currency=base_currency,
        holdings=holdings,
        quotes=quotes,
        fx_rates=fx_rates,
    )
