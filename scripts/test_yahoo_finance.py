"""Manual Yahoo Finance tester for Bagwatch."""

from __future__ import annotations

import argparse
import json
from datetime import UTC
from decimal import Decimal, InvalidOperation
from pathlib import Path
import sys

from _env import get_env

ROOT_DIR = Path(__file__).resolve().parent.parent
SESSION_DIR = ROOT_DIR / "custom_components" / "bagwatch"
if str(SESSION_DIR) not in sys.path:
    sys.path.insert(0, str(SESSION_DIR))

from yahoo_session import select_yahoo_session_quote

try:
    import yfinance as yf
except ImportError as err:  # pragma: no cover - depends on local env
    raise SystemExit(
        "yfinance is not installed in this environment. Install the Bagwatch dependency set first."
    ) from err


def normalize_number(value):
    """Convert values to JSON-friendly numbers when possible."""
    if value in (None, ""):
        return None
    try:
        return float(Decimal(str(value)))
    except (InvalidOperation, TypeError, ValueError):
        return value


def get_quote(symbol: str) -> dict:
    """Fetch a quote summary for one Yahoo Finance symbol."""
    ticker = yf.Ticker(symbol)
    fast_info = dict(getattr(ticker, "fast_info", {}) or {})
    info = dict(getattr(ticker, "info", {}) or {})
    history = ticker.history(period="5d", interval="1d", auto_adjust=False, actions=False)

    history_rows: list[dict] = []
    if hasattr(history, "empty") and not history.empty:
        for index, row in history.tail(5).iterrows():
            dt = index.to_pydatetime() if hasattr(index, "to_pydatetime") else index
            if getattr(dt, "tzinfo", None) is None:
                dt = dt.replace(tzinfo=UTC)
            history_rows.append(
                {
                    "datetime": dt.isoformat(),
                    "open": normalize_number(row.get("Open")),
                    "high": normalize_number(row.get("High")),
                    "low": normalize_number(row.get("Low")),
                    "close": normalize_number(row.get("Close")),
                    "volume": normalize_number(row.get("Volume")),
                }
            )

    session_price, session_as_of, market_state = select_yahoo_session_quote(info, fast_info)

    return {
        "symbol": symbol,
        "selected_session": {
            "marketState": market_state,
            "price": normalize_number(session_price),
            "as_of": session_as_of,
        },
        "fast_info": fast_info,
        "info": {
            "currency": info.get("currency"),
            "exchange": info.get("exchange"),
            "fullExchangeName": info.get("fullExchangeName"),
            "quoteType": info.get("quoteType"),
            "regularMarketPrice": normalize_number(info.get("regularMarketPrice")),
            "currentPrice": normalize_number(info.get("currentPrice")),
            "previousClose": normalize_number(info.get("previousClose")),
            "marketState": info.get("marketState"),
            "preMarketPrice": normalize_number(info.get("preMarketPrice")),
            "preMarketTime": info.get("preMarketTime"),
            "postMarketPrice": normalize_number(info.get("postMarketPrice")),
            "postMarketTime": info.get("postMarketTime"),
            "regularMarketTime": info.get("regularMarketTime"),
        },
        "history": history_rows,
    }


def main() -> None:
    """Run the CLI."""
    parser = argparse.ArgumentParser(description="Test Yahoo Finance lookups used by Bagwatch")
    subparsers = parser.add_subparsers(dest="command", required=True)

    quote_parser = subparsers.add_parser("quote", help="Fetch a Yahoo Finance quote")
    quote_parser.add_argument("--symbol", default=get_env("TEST_YAHOO_SYMBOL", "MSFT"))

    fx_parser = subparsers.add_parser("fx", help="Fetch a Yahoo Finance FX symbol")
    fx_parser.add_argument("--source", default=get_env("TEST_YAHOO_FX_SOURCE", "USD"))
    fx_parser.add_argument("--target", default=get_env("TEST_YAHOO_FX_TARGET", "PLN"))

    args = parser.parse_args()

    if args.command == "quote":
        payload = get_quote(args.symbol)
    else:
        payload = get_quote(f"{args.source.upper()}{args.target.upper()}=X")

    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
