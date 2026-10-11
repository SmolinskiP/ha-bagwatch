"""Tests for Yahoo extended-hours session price selection."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

MODULE_PATH = (
    Path(__file__).resolve().parent.parent
    / "custom_components"
    / "bagwatch"
    / "yahoo_session.py"
)
SPEC = importlib.util.spec_from_file_location("bagwatch_yahoo_session", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
YAHOO_SESSION = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = YAHOO_SESSION
SPEC.loader.exec_module(YAHOO_SESSION)

select_yahoo_session_quote = YAHOO_SESSION.select_yahoo_session_quote
unix_timestamp_to_iso = YAHOO_SESSION.unix_timestamp_to_iso


def test_pre_market_uses_pre_market_price() -> None:
    """PRE should prefer preMarketPrice over the frozen regular print."""
    price, as_of, state = select_yahoo_session_quote(
        {
            "marketState": "PRE",
            "regularMarketPrice": 100,
            "preMarketPrice": 102.5,
            "preMarketTime": 1_700_000_000,
            "postMarketPrice": 99,
        }
    )
    assert price == 102.5
    assert state == "PRE"
    assert as_of == "2023-11-14T22:13:20+00:00"


def test_prepre_is_treated_as_pre_market() -> None:
    """Early pre-market (PREPRE) should also use the pre-market print."""
    price, _, state = select_yahoo_session_quote(
        {"marketState": "PREPRE", "preMarketPrice": "10.25", "regularMarketPrice": 10}
    )
    assert price == "10.25"
    assert state == "PREPRE"


def test_post_market_uses_post_market_price() -> None:
    """POST should prefer postMarketPrice over the regular close."""
    price, as_of, state = select_yahoo_session_quote(
        {
            "marketState": "POST",
            "regularMarketPrice": 100,
            "preMarketPrice": 101,
            "postMarketPrice": 103.4,
            "postMarketTime": 1_700_010_000,
        }
    )
    assert price == 103.4
    assert state == "POST"
    assert as_of == "2023-11-15T01:00:00+00:00"


def test_postpost_is_treated_as_post_market() -> None:
    """Late after-hours (POSTPOST) should use the post-market print."""
    price, _, state = select_yahoo_session_quote(
        {"marketState": "postpost", "postMarketPrice": 88.1, "regularMarketPrice": 87}
    )
    assert price == 88.1
    assert state == "POSTPOST"


def test_closed_ignores_stale_extended_hours_prints() -> None:
    """CLOSED must not reuse leftover pre/post prices from the last window."""
    price, as_of, state = select_yahoo_session_quote(
        {
            "marketState": "CLOSED",
            "regularMarketPrice": 100,
            "preMarketPrice": 102,
            "postMarketPrice": 99,
        }
    )
    assert price is None
    assert as_of is None
    assert state == "CLOSED"


def test_regular_session_leaves_regular_price_to_the_caller() -> None:
    """REGULAR should not override lastPrice / regularMarketPrice."""
    price, as_of, state = select_yahoo_session_quote(
        {
            "marketState": "REGULAR",
            "regularMarketPrice": 100,
            "preMarketPrice": 99,
            "postMarketPrice": 101,
        }
    )
    assert price is None
    assert as_of is None
    assert state == "REGULAR"


def test_pre_market_without_a_print_falls_through() -> None:
    """A PRE session with no (or zero) pre-market print falls back."""
    price, _, state = select_yahoo_session_quote(
        {"marketState": "PRE", "preMarketPrice": 0, "regularMarketPrice": 50}
    )
    assert price is None
    assert state == "PRE"


def test_fast_info_is_used_when_info_lacks_the_extended_print() -> None:
    """fast_info is a fallback source for the extended-hours price."""
    price, _, state = select_yahoo_session_quote(
        {"marketState": "POST"},
        {"postMarketPrice": 12.34},
    )
    assert price == 12.34
    assert state == "POST"


def test_missing_market_state_falls_through() -> None:
    """No marketState means the regular-session fallback path."""
    price, as_of, state = select_yahoo_session_quote(
        {"preMarketPrice": 1, "postMarketPrice": 2, "regularMarketPrice": 3}
    )
    assert price is None
    assert as_of is None
    assert state is None


def test_unix_timestamp_to_iso_rejects_empty_values() -> None:
    """Zero / missing Yahoo timestamps should not produce a fake as_of."""
    assert unix_timestamp_to_iso(None) is None
    assert unix_timestamp_to_iso(0) is None
    assert unix_timestamp_to_iso("") is None
    assert unix_timestamp_to_iso("not-a-time") is None
