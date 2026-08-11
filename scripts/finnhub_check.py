"""Read-only Finnhub credential and quote-freshness canary."""
from __future__ import annotations

from datetime import datetime, timezone
import os

from market_data.finnhub import FinnhubClient, FinnhubError


def main() -> int:
    symbol = os.getenv("FINNHUB_CHECK_SYMBOL", "AAPL").strip().upper()
    max_age = max(60, int(os.getenv("FINNHUB_MAX_QUOTE_AGE_SECONDS", "259200")))
    try:
        quote = FinnhubClient().quote(symbol)
        observed = datetime.fromisoformat(quote["as_of"])
        age = (datetime.now(timezone.utc) - observed).total_seconds()
        if age < -180 or age > max_age:
            raise FinnhubError("quote timestamp is outside the canary freshness window")
        print(f"Finnhub authenticated: symbol={quote['symbol']} source=finnhub "
              f"age_seconds={max(0, round(age))} read_only=true execution_authority=false")
        return 0
    except FinnhubError as exc:
        print(f"Finnhub canary failed: {exc}; read_only=true execution_authority=false")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
