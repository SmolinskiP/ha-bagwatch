"""Quick provider sanity check runner for Bagwatch."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PYTHON = sys.executable

COMMANDS = {
    "twelve_quote": [PYTHON, str(ROOT / "test_twelve_data.py"), "quote"],
    "twelve_fx": [PYTHON, str(ROOT / "test_twelve_data.py"), "fx"],
    "coingecko_price": [PYTHON, str(ROOT / "test_coingecko.py"), "price"],
    "yahoo_quote": [PYTHON, str(ROOT / "test_yahoo_finance.py"), "quote"],
    "yahoo_fx": [PYTHON, str(ROOT / "test_yahoo_finance.py"), "fx"],
}


def main() -> None:
    """Run all local provider checks one after another."""
    results: dict[str, dict[str, object]] = {}

    for name, command in COMMANDS.items():
        completed = subprocess.run(command, capture_output=True, text=True)
        results[name] = {
            "returncode": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
        }

    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
