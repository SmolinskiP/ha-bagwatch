"""Manual Twelve Data endpoint tester for Bagwatch."""

from __future__ import annotations

import argparse
import json
from urllib.parse import urlencode
from urllib.request import urlopen

from _env import get_env, require_env

BASE_URL = "https://api.twelvedata.com"


def request(endpoint: str, params: dict[str, str]) -> dict:
    """Call a Twelve Data endpoint and return the parsed JSON payload."""
    query = urlencode({key: value for key, value in params.items() if value not in (None, "")})
    with urlopen(f"{BASE_URL}/{endpoint}?{query}") as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    """Run the CLI."""
    parser = argparse.ArgumentParser(description="Test Twelve Data endpoints used by Bagwatch")
    subparsers = parser.add_subparsers(dest="command", required=True)

    quote_parser = subparsers.add_parser("quote", help="Test the quote endpoint")
    quote_parser.add_argument("--symbol", default=get_env("TEST_TWELVE_SYMBOL", "MSFT"))
    quote_parser.add_argument("--exchange", default=get_env("TEST_TWELVE_EXCHANGE", ""))
    quote_parser.add_argument("--country", default=get_env("TEST_TWELVE_COUNTRY", "United States"))
    quote_parser.add_argument(
        "--asset-type",
        dest="asset_type",
        default=get_env("TEST_TWELVE_ASSET_TYPE", "Common Stock"),
    )

    fx_parser = subparsers.add_parser("fx", help="Test the exchange_rate endpoint")
    fx_parser.add_argument("--source", default=get_env("TEST_YAHOO_FX_SOURCE", "USD"))
    fx_parser.add_argument("--target", default=get_env("TEST_YAHOO_FX_TARGET", "PLN"))

    args = parser.parse_args()
    api_key = require_env("TWELVE_DATA_API_KEY")

    if args.command == "quote":
        payload = request(
            "quote",
            {
                "symbol": args.symbol,
                "exchange": args.exchange,
                "country": args.country,
                "type": args.asset_type,
                "apikey": api_key,
            },
        )
    else:
        payload = request(
            "exchange_rate",
            {
                "symbol": f"{args.source.upper()}/{args.target.upper()}",
                "apikey": api_key,
            },
        )

    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
