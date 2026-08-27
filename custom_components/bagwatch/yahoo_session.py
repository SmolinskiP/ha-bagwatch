"""Select the Yahoo Finance price for the current market session.

Yahoo's quote payload includes separate regular, pre-market and post-market
prints plus a ``marketState`` flag. ``regularMarketPrice`` / ``lastPrice`` stay
frozen outside the cash session, which is why Bagwatch previously stopped
updating after the close.

This helper prefers the live extended-hours print whenever the session is
not CLOSED:

* PRE / PREPRE → ``preMarketPrice``
* POST / POSTPOST → ``postMarketPrice``
* REGULAR / CLOSED / anything else → caller falls back to the regular print
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# Yahoo quote.marketState values. PREPRE is the early pre-market window,
# POSTPOST is late after-hours.
PRE_MARKET_STATES = frozenset({"PRE", "PREPRE"})
POST_MARKET_STATES = frozenset({"POST", "POSTPOST"})


def unix_timestamp_to_iso(value: Any) -> str | None:
    """Convert a Yahoo unix timestamp into an ISO-8601 UTC string."""
    if value in (None, ""):
        return None
    try:
        timestamp = float(value)
    except (TypeError, ValueError):
        return None
    if timestamp <= 0:
        return None
    try:
        return datetime.fromtimestamp(timestamp, tz=UTC).isoformat()
    except (OSError, OverflowError, ValueError):
        return None


def _nonzero_quote(value: Any) -> Any:
    """Return *value* when it looks like a real quote, otherwise None.

    Yahoo frequently sends ``0`` / ``0.0`` for pre/post fields when that
    session has no prints yet. Treat those as missing so the caller can fall
    back to the regular-session price.
    """
    if value in (None, ""):
        return None
    try:
        if float(value) == 0:
            return None
    except (TypeError, ValueError):
        return None
    return value


def _normalize_market_state(value: Any) -> str | None:
    """Normalize Yahoo marketState to an uppercase token."""
    if value in (None, ""):
        return None
    cleaned = str(value).strip().upper()
    return cleaned or None


def select_yahoo_session_quote(
    info: dict[str, Any] | None,
    fast_info: dict[str, Any] | None = None,
) -> tuple[Any, str | None, str | None]:
    """Return ``(price, as_of_iso, market_state)`` for the live Yahoo session.

    A ``None`` price means "no extended-hours print"; the caller should then
    use ``regularMarketPrice`` / ``lastPrice``. CLOSED (and REGULAR) always
    return a ``None`` price so leftover pre/post prints from an earlier
    window are not reused after the session ends.
    """
    info = info or {}
    fast_info = fast_info or {}
    market_state = _normalize_market_state(
        info.get("marketState") or fast_info.get("marketState")
    )

    if market_state in PRE_MARKET_STATES:
        price = _nonzero_quote(info.get("preMarketPrice"))
        if price is None:
            price = _nonzero_quote(fast_info.get("preMarketPrice"))
        if price is not None:
            as_of = unix_timestamp_to_iso(
                info.get("preMarketTime") or fast_info.get("preMarketTime")
            )
            return price, as_of, market_state

    if market_state in POST_MARKET_STATES:
        price = _nonzero_quote(info.get("postMarketPrice"))
        if price is None:
            price = _nonzero_quote(fast_info.get("postMarketPrice"))
        if price is not None:
            as_of = unix_timestamp_to_iso(
                info.get("postMarketTime") or fast_info.get("postMarketTime")
            )
            return price, as_of, market_state

    return None, None, market_state
