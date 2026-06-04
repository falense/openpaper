# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx"]
# ///
"""Fetch market data from Yahoo Finance for the OpenPaper newspaper.

Outputs a JSON array to stdout with current prices, changes, and direction
for each requested symbol. Designed to be run standalone via
`uv run fetchers/markets.py`.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1d&interval=1d"
USER_AGENT = "OpenPaper/0.2.0"
CACHE_MAX_AGE_SECONDS = 900  # 15 minutes

DEFAULT_SYMBOLS = "^OSEAX,USDNOK=X,^GSPC,GC=F,BTC-USD,BZ=F"
DEFAULT_NAMES = "Oslo Børs,USD/NOK,S&P 500,Gold,Bitcoin,Brent"

# Symbols that represent currency pairs or small-unit values — show 2 decimals
CURRENCY_LIKE = {"USDNOK=X"}

# Symbols whose prices are typically large (>100) — show with thousands separator, no decimals
LARGE_VALUE = {"^OSEAX", "^GSPC", "GC=F", "BTC-USD"}


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


def format_value(price: float, symbol: str) -> str:
    """Format a market price for display.

    - Currency pairs: 2 decimal places (e.g. 10.42)
    - Large indices/commodities: thousands separator, no decimals (e.g. 1,486)
    - Others: 2 decimal places
    """
    if symbol in CURRENCY_LIKE:
        return f"{price:,.2f}"
    elif symbol in LARGE_VALUE or price >= 1000:
        return f"{price:,.0f}"
    elif price >= 100:
        return f"{price:,.1f}"
    else:
        return f"{price:,.2f}"


def format_change(change_pct: float) -> tuple[str, str]:
    """Format a percentage change and determine direction.

    Returns (change_string, direction).
    The change_string uses a minus sign (U+2212) for negative values.
    """
    if change_pct >= 0:
        return f"+{change_pct:.1f}%", "up"
    else:
        # Use proper minus sign (U+2212) for typography
        return f"−{abs(change_pct):.1f}%", "down"


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------


def cache_key(symbol: str) -> str:
    """Generate a filesystem-safe cache filename for a symbol."""
    safe = symbol.replace("^", "_caret_").replace("=", "_eq_").replace("/", "_slash_")
    return f"market_{safe}.json"


def get_cached(cache_dir: Path | None, symbol: str) -> dict | None:
    """Return cached API response if fresh enough, else None."""
    if cache_dir is None:
        return None
    cache_file = cache_dir / cache_key(symbol)
    if not cache_file.exists():
        return None
    age = time.time() - cache_file.stat().st_mtime
    if age > CACHE_MAX_AGE_SECONDS:
        return None
    try:
        return json.loads(cache_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def write_cache(cache_dir: Path | None, symbol: str, data: dict) -> None:
    """Write API response to cache."""
    if cache_dir is None:
        return
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / cache_key(symbol)
    try:
        cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        print(f"Warning: failed to write cache for {symbol}: {exc}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------


def fetch_symbol(symbol: str, cache_dir: Path | None) -> dict | None:
    """Fetch chart data for a single symbol from Yahoo Finance.

    Returns the parsed JSON response, or None on failure.
    """
    # Try cache first
    cached = get_cached(cache_dir, symbol)
    if cached is not None:
        return cached

    url = CHART_URL.format(symbol=symbol)
    headers = {"User-Agent": USER_AGENT}

    try:
        response = httpx.get(url, headers=headers, timeout=15.0)
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPStatusError as exc:
        print(
            f"Warning: HTTP {exc.response.status_code} for {symbol}",
            file=sys.stderr,
        )
        return None
    except httpx.RequestError as exc:
        print(f"Warning: request failed for {symbol}: {exc}", file=sys.stderr)
        return None
    except json.JSONDecodeError:
        print(f"Warning: invalid JSON response for {symbol}", file=sys.stderr)
        return None

    write_cache(cache_dir, symbol, data)
    return data


def parse_symbol(data: dict, symbol: str, display_name: str) -> dict | None:
    """Parse Yahoo Finance chart response into an OpenPaper market entry.

    Returns None if the data cannot be parsed.
    """
    try:
        result = data["chart"]["result"][0]
        meta = result["meta"]
    except (KeyError, IndexError, TypeError):
        print(f"Warning: unexpected data structure for {symbol}", file=sys.stderr)
        return None

    price = meta.get("regularMarketPrice")
    prev_close = meta.get("chartPreviousClose") or meta.get("previousClose")

    if price is None:
        print(f"Warning: no price data for {symbol}", file=sys.stderr)
        return None

    # Calculate change
    if prev_close and prev_close != 0:
        change_pct = ((price - prev_close) / prev_close) * 100
    else:
        change_pct = 0.0

    change_str, direction = format_change(change_pct)
    value_str = format_value(price, symbol)

    currency = meta.get("currency", "")

    return {
        "name": display_name,
        "value": value_str,
        "change": change_str,
        "direction": direction,
        "currency": currency,
    }


def fetch_markets(
    symbols: list[str],
    names: list[str],
    cache_dir: Path | None,
) -> list[dict]:
    """Fetch and parse market data for all requested symbols."""
    results: list[dict] = []

    for symbol, name in zip(symbols, names):
        data = fetch_symbol(symbol, cache_dir)
        if data is None:
            continue

        entry = parse_symbol(data, symbol, name)
        if entry is not None:
            results.append(entry)

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch market data from Yahoo Finance for OpenPaper.",
    )
    parser.add_argument(
        "--symbols",
        type=str,
        default=DEFAULT_SYMBOLS,
        help=f"Comma-separated Yahoo Finance symbols (default: {DEFAULT_SYMBOLS})",
    )
    parser.add_argument(
        "--names",
        type=str,
        default=DEFAULT_NAMES,
        help=f"Comma-separated display names (default: {DEFAULT_NAMES})",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        help="Directory to cache API responses (cached for 15 minutes)",
    )

    args = parser.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    names = [n.strip() for n in args.names.split(",") if n.strip()]

    if len(symbols) != len(names):
        print(
            f"Error: {len(symbols)} symbol(s) but {len(names)} name(s) — counts must match.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        results = fetch_markets(symbols, names, args.cache_dir)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        results = []

    json.dump(results, sys.stdout, ensure_ascii=False, indent=2)
    print()  # trailing newline


if __name__ == "__main__":
    main()
