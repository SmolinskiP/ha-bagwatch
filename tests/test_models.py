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
build_portfolio_snapshot = MODELS.build_portfolio_snapshot
parse_holdings_text = MODELS.parse_holdings_text


def test_parse_holdings_text_accepts_array() -> None:
    """A plain JSON array should parse correctly."""
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


def test_parse_holdings_text_rejects_duplicate_symbols() -> None:
    """Duplicate symbols should be rejected."""
    try:
        parse_holdings_text(
            """
            [
              {
                "symbol": "BTC",
                "asset_type": "crypto",
                "quantity": 0.1,
                "average_buy_price": 10000,
                "buy_currency": "USD"
              },
              {
                "symbol": "btc",
                "asset_type": "crypto",
                "quantity": 0.2,
                "average_buy_price": 12000,
                "buy_currency": "USD"
              }
            ]
            """
        )
    except PortfolioValidationError as err:
        assert "Duplicate symbol" in str(err)
    else:
        raise AssertionError("Expected duplicate symbol validation error")


def test_build_portfolio_snapshot_converts_fx_and_totals() -> None:
    """Portfolio values should be converted into the base currency."""
    holdings = parse_holdings_text(
        """
        [
          {
            "symbol": "KO.US",
            "quantity": 10,
            "average_buy_price": 50,
            "buy_currency": "USD"
          },
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
        holdings[0].key: MarketQuote(symbol="KO", price=Decimal("55"), currency="USD"),
        holdings[1].key: MarketQuote(symbol="PKN", price=Decimal("70"), currency="PLN"),
    }
    fx_rates = {
        ("USD", "PLN"): Decimal("4"),
        ("PLN", "PLN"): Decimal("1"),
    }

    snapshot = build_portfolio_snapshot(
        name="My Portfolio",
        base_currency="PLN",
        holdings=holdings,
        quotes=quotes,
        fx_rates=fx_rates,
    )

    assert snapshot.market_value_base == Decimal("2550")
    assert snapshot.cost_basis_base == Decimal("2300")
    assert snapshot.unrealized_gain_base == Decimal("250")
    assert round(float(snapshot.unrealized_gain_pct), 2) == 10.87


def test_cost_basis_base_disables_fx_estimate() -> None:
    """Exact base-currency cost should bypass FX estimation."""
    holdings = parse_holdings_text(
        """
        [
          {
            "symbol": "BTC",
            "asset_type": "crypto",
            "quantity": 0.5,
            "cost_basis_base": 10000
          }
        ]
        """
    )

    quotes = {
        holdings[0].key: MarketQuote(
            symbol="BTC/USD",
            price=Decimal("25000"),
            currency="USD",
        )
    }
    fx_rates = {("USD", "USD"): Decimal("1")}

    snapshot = build_portfolio_snapshot(
        name="Crypto",
        base_currency="USD",
        holdings=holdings,
        quotes=quotes,
        fx_rates=fx_rates,
    )

    assert snapshot.positions[0].is_fx_estimate is False
    assert snapshot.unrealized_gain_base == Decimal("2500.0")

