"""Manual CoinGecko endpoint tester for Bagwatch."""

from __future__ import annotations

import argparse
import json
from urllib.parse import urlencode
from urllib.request import urlopen

from _env import get_env

BASE_URL = "https://api.coingecko.com/api/v3"


def request(endpoint: str, params: dict[str, str]) -> object:
    """Call a CoinGecko endpoint and return the parsed JSON payload."""
    query = urlencode({key: value for key, value in params.items() if value not in (None, "")})
    with urlopen(f"{BASE_URL}/{endpoint}?{query}") as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    """Run the CLI."""
    parser = argparse.ArgumentParser(description="Test CoinGecko endpoints used by Bagwatch")
    subparsers = parser.add_subparsers(dest="command", required=True)

    coins_parser = subparsers.add_parser("coins", help="Fetch and optionally filter the coins list")
    coins_parser.add_argument("--match", default="")
    coins_parser.add_argument("--limit", type=int, default=20)

    price_parser = subparsers.add_parser("price", help="Fetch price data for one or more CoinGecko ids")
    price_parser.add_argument("--ids", default=get_env("TEST_COINGECKO_ID", "bitcoin"))
    price_parser.add_argument("--vs", dest="vs_currency", default=get_env("TEST_COINGECKO_VS_CURRENCY", "usd"))

    args = parser.parse_args()
    api_key = get_env("COINGECKO_API_KEY", "")

    if args.command == "coins":
        payload = request(
            "coins/list",
            {"x_cg_demo_api_key": api_key},
        )
        if args.match:
            match = args.match.strip().lower()
            payload = [
                item for item in payload
                if match in str(item.get("id", "")).lower()
                or match in str(item.get("symbol", "")).lower()
                or match in str(item.get("name", "")).lower()
            ]
        payload = payload[: args.limit]
    else:
        payload = request(
            "simple/price",
            {
                "ids": args.ids,
                "vs_currencies": args.vs_currency,
                "include_last_updated_at": "true",
                "x_cg_demo_api_key": api_key,
            },
        )

    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
