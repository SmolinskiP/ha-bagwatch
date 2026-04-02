"""Tests for portfolio models."""

from __future__ import annotations

from decimal import Decimal
import importlib.util
from pathlib import Path
import sys

MODULE_PATH = Path(__file__).resolve().parent.parent / "custom_components" / "bagwatch" / "models.py"
SPEC = importlib.util.spec_from_file_location("bagwatch_models", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
MODELS = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODELS
SPEC.loader.exec_module(MODELS)

MarketQuote = MODELS.MarketQuote
PortfolioValidationError = MODELS.PortfolioValidationError
group_transactions = MODELS.group_transactions
parse_holdings_text = MODELS.parse_holdings_text
parse_transactions_data = MODELS.parse_transactions_data
build_portfolio_snapshot = MODELS.build_portfolio_snapshot
build_portfolio_snapshot_from_transactions = MODELS.build_portfolio_snapshot_from_transactions


def test_parse_holdings_text_accepts_array() -> None:
    """A plain legacy JSON array should still parse correctly."""
    holdings = parse_holdings_text(
        """
        [
          {
            "symbol": "KO.US",
            "quantity": 10,
            "average_buy_price": 50,
            "buy_currency": "USD"
          }
        ]
        """
    )

    assert len(holdings) == 1
    assert holdings[0].symbol == "KO.US"
    assert holdings[0].quantity == Decimal("10")


def test_group_transactions_rejects_partial_sell_above_open_quantity() -> None:
    """Selling more than currently owned should fail validation."""
    transactions = parse_transactions_data(
        [
            {
                "symbol": "MSFT.US",
                "asset_type": "stock",
                "transaction_type": "buy",
                "quantity": "2",
                "unit_price": "390",
                "currency": "USD",
                "trade_date": "2026-01-10",
            },
            {
                "symbol": "MSFT.US",
                "asset_type": "stock",
                "transaction_type": "sell",
                "quantity": "3",
                "unit_price": "410",
                "currency": "USD",
                "trade_date": "2026-02-10",
            },
        ]
    )

    try:
        group_transactions(transactions)
    except PortfolioValidationError as err:
        assert "exceeds the available quantity" in str(err)
    else:
        raise AssertionError("Expected sell validation error")


def test_build_portfolio_snapshot_from_transactions_tracks_realized_and_unrealized_gain() -> None:
    """Average-cost transactions should produce open and realized P/L."""
    transactions = parse_transactions_data(
        [
            {
                "symbol": "MSFT.US",
                "name": "Microsoft",
                "asset_type": "stock",
                "transaction_type": "buy",
                "quantity": "2",
                "unit_price": "390",
                "currency": "USD",
                "trade_date": "2026-01-10",
                "_order_index": 0,
            },
            {
                "symbol": "MSFT.US",
                "asset_type": "stock",
                "transaction_type": "buy",
                "quantity": "1",
                "unit_price": "420",
                "currency": "USD",
                "trade_date": "2026-02-10",
                "_order_index": 1,
            },
            {
                "symbol": "MSFT.US",
                "asset_type": "stock",
                "transaction_type": "sell",
                "quantity": "1",
                "unit_price": "450",
                "currency": "USD",
                "trade_date": "2026-03-10",
                "_order_index": 2,
            },
        ]
    )

    bundles = group_transactions(transactions)
    quotes = {
        "MSFT.US": MarketQuote(symbol="MSFT", price=Decimal("500"), currency="USD")
    }
    fx_rates = {("USD", "USD"): Decimal("1")}

    snapshot = build_portfolio_snapshot_from_transactions(
        name="My Portfolio",
        base_currency="USD",
        bundles=bundles,
        quotes=quotes,
        fx_rates=fx_rates,
    )

    position = snapshot.positions[0]
    assert position.quantity == Decimal("2")
    assert position.average_cost_base == Decimal("400")
    assert position.cost_basis_base == Decimal("800")
    assert position.market_value_base == Decimal("1000")
    assert position.unrealized_gain_base == Decimal("200")
    assert position.realized_gain_base == Decimal("50")
    assert snapshot.realized_gain_base == Decimal("50")


def test_build_portfolio_snapshot_from_transactions_converts_fx() -> None:
    """Transaction-ledger values should be converted into the portfolio base currency."""
    transactions = parse_transactions_data(
        [
            {
                "symbol": "KO.US",
                "asset_type": "stock",
                "transaction_type": "buy",
                "quantity": "10",
                "unit_price": "50",
                "currency": "USD",
                "trade_date": "2026-01-10",
                "_order_index": 0,
            }
        ]
    )

    bundles = group_transactions(transactions)
    quotes = {
        "KO.US": MarketQuote(symbol="KO", price=Decimal("55"), currency="USD")
    }
    fx_rates = {
        ("USD", "PLN"): Decimal("4"),
        ("PLN", "PLN"): Decimal("1"),
    }

    snapshot = build_portfolio_snapshot_from_transactions(
        name="FX Portfolio",
        base_currency="PLN",
        bundles=bundles,
        quotes=quotes,
        fx_rates=fx_rates,
    )

    assert snapshot.market_value_base == Decimal("2200")
    assert snapshot.cost_basis_base == Decimal("2000")
    assert snapshot.unrealized_gain_base == Decimal("200")


def test_build_portfolio_snapshot_legacy_holdings_still_work() -> None:
    """Legacy aggregated-holding snapshots should still calculate correctly."""
    holdings = parse_holdings_text(
        """
        [
          {
            "symbol": "PKN.PL",
            "quantity": 5,
            "average_buy_price": 60,
            "buy_currency": "PLN"
          }
        ]
        """
    )

    quotes = {
        holdings[0].key: MarketQuote(symbol="PKN", price=Decimal("70"), currency="PLN")
    }
    fx_rates = {("PLN", "PLN"): Decimal("1")}

    snapshot = build_portfolio_snapshot(
        name="Legacy",
        base_currency="PLN",
        holdings=holdings,
        quotes=quotes,
        fx_rates=fx_rates,
    )

    assert snapshot.market_value_base == Decimal("350")
    assert snapshot.cost_basis_base == Decimal("300")
    assert snapshot.unrealized_gain_base == Decimal("50")
