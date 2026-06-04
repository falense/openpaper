# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx"]
# ///
"""Fetch weather data from yr.no (MET Norway) for the OpenPaper newspaper.

Outputs a JSON object to stdout with current conditions and a 4-day forecast.
Designed to be run standalone via `uv run fetchers/weather.py`.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

API_URL = "https://api.met.no/weatherapi/locationforecast/2.0/compact"
USER_AGENT = "OpenPaper/0.2.0 github.com/falense/openpaper"
CACHE_MAX_AGE_SECONDS = 3600  # 1 hour

# yr.no symbol_code → OpenPaper icon mapping
ICON_RAIN_KEYWORDS = ("rain", "sleet", "drizzle")
ICON_SNOW_KEYWORDS = ("snow",)
ICON_SUN_PREFIXES = ("clearsky", "fair")
ICON_CLOUD_PREFIXES = ("cloudy", "partlycloudy")

# Wind direction compass labels (16-point)
COMPASS_DIRECTIONS = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
]

WEEKDAY_ABBREV = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def symbol_to_icon(symbol_code: str) -> str:
    """Map a yr.no symbol_code to an OpenPaper icon name."""
    code = symbol_code.lower()

    # Check sun/fair first (clearsky_day, fair_night, etc.)
    for prefix in ICON_SUN_PREFIXES:
        if code.startswith(prefix):
            return "sun"

    # Check cloud
    for prefix in ICON_CLOUD_PREFIXES:
        if code.startswith(prefix):
            return "cloud"

    # Check rain/sleet/drizzle
    for keyword in ICON_RAIN_KEYWORDS:
        if keyword in code:
            return "rain"

    # Check snow
    for keyword in ICON_SNOW_KEYWORDS:
        if keyword in code:
            return "snow"

    return "cloud"


def degrees_to_compass(degrees: float) -> str:
    """Convert wind direction in degrees to a compass label."""
    index = round(degrees / 22.5) % 16
    return COMPASS_DIRECTIONS[index]


def format_wind(speed_mps: float, direction_deg: float) -> str:
    """Format wind speed (m/s) and direction (degrees) into a human string."""
    kmh = round(speed_mps * 3.6)
    compass = degrees_to_compass(direction_deg)
    return f"{compass} {kmh} km/h"


def generate_description(
    current_symbol: str,
    forecast_symbols: list[str],
) -> str:
    """Generate a short weather description from the current and upcoming symbols."""
    current_icon = symbol_to_icon(current_symbol)
    current_code = current_symbol.lower()

    # Describe current conditions
    if current_icon == "sun":
        current_desc = "Clear skies"
    elif current_icon == "rain":
        if "heavy" in current_code:
            current_desc = "Heavy rain"
        elif "light" in current_code or "drizzle" in current_code:
            current_desc = "Light rain"
        else:
            current_desc = "Rain"
    elif current_icon == "snow":
        if "heavy" in current_code:
            current_desc = "Heavy snow"
        elif "light" in current_code:
            current_desc = "Light snow"
        else:
            current_desc = "Snow"
    elif "partlycloudy" in current_code:
        current_desc = "Partly cloudy"
    else:
        current_desc = "Overcast"

    # Look at upcoming hours to add a trend
    if not forecast_symbols:
        return current_desc

    upcoming_icons = [symbol_to_icon(s) for s in forecast_symbols[:6]]

    # Check if conditions change
    if current_icon in ("cloud", "rain") and upcoming_icons.count("sun") >= 3:
        return f"{current_desc}, clearing later"
    elif current_icon == "sun" and upcoming_icons.count("rain") >= 2:
        return f"{current_desc}, rain expected later"
    elif current_icon == "sun" and upcoming_icons.count("cloud") >= 3:
        return f"{current_desc}, clouds building"
    elif current_icon == "rain" and upcoming_icons.count("rain") <= 1:
        return f"{current_desc}, easing soon"

    return current_desc


def placeholder_output() -> dict:
    """Return placeholder JSON when data is unavailable."""
    return {
        "icon": "cloud",
        "temp": None,
        "description": "Weather data unavailable",
        "high": None,
        "low": None,
        "wind": "--",
        "forecast": [],
    }


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------


def get_cached(cache_dir: Path | None) -> dict | None:
    """Return cached API response if fresh enough, else None."""
    if cache_dir is None:
        return None
    cache_file = cache_dir / "weather_yr.json"
    if not cache_file.exists():
        return None
    age = time.time() - cache_file.stat().st_mtime
    if age > CACHE_MAX_AGE_SECONDS:
        return None
    try:
        return json.loads(cache_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def write_cache(cache_dir: Path | None, data: dict) -> None:
    """Write API response to cache."""
    if cache_dir is None:
        return
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / "weather_yr.json"
    try:
        cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        print(f"Warning: failed to write cache: {exc}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------


def fetch_weather(lat: float, lon: float, cache_dir: Path | None) -> dict:
    """Fetch weather data from yr.no and return the raw API JSON."""
    # Try cache first
    cached = get_cached(cache_dir)
    if cached is not None:
        print("Using cached weather data", file=sys.stderr)
        return cached

    url = f"{API_URL}?lat={lat}&lon={lon}"
    headers = {"User-Agent": USER_AGENT}

    response = httpx.get(url, headers=headers, timeout=15.0)
    response.raise_for_status()
    data = response.json()

    write_cache(cache_dir, data)
    return data


def parse_weather(data: dict, location_name: str) -> dict:
    """Parse yr.no API response into OpenPaper weather JSON."""
    timeseries = data.get("properties", {}).get("timeseries", [])
    if not timeseries:
        print("Warning: no timeseries in API response", file=sys.stderr)
        return placeholder_output()

    # --- Current conditions ---
    current = timeseries[0]
    instant = current.get("data", {}).get("instant", {}).get("details", {})
    next_1h = current.get("data", {}).get("next_1_hours", {})
    # Fall back to next_6_hours if next_1_hours isn't available
    if not next_1h:
        next_1h = current.get("data", {}).get("next_6_hours", {})

    temp = instant.get("air_temperature")
    wind_speed = instant.get("wind_speed", 0)
    wind_dir = instant.get("wind_from_direction", 0)
    symbol_code = next_1h.get("summary", {}).get("symbol_code", "cloudy")

    icon = symbol_to_icon(symbol_code)
    wind = format_wind(wind_speed, wind_dir)

    # --- Today's high/low ---
    now = datetime.now(timezone.utc)
    today_str = now.strftime("%Y-%m-%d")

    today_temps: list[float] = []
    for entry in timeseries:
        entry_time = entry.get("time", "")
        if entry_time.startswith(today_str):
            t = entry.get("data", {}).get("instant", {}).get("details", {}).get("air_temperature")
            if t is not None:
                today_temps.append(t)

    high = round(max(today_temps)) if today_temps else None
    low = round(min(today_temps)) if today_temps else None

    # --- Collect upcoming symbol codes for description ---
    upcoming_symbols: list[str] = []
    for entry in timeseries[1:13]:  # next ~12 hours
        n1h = entry.get("data", {}).get("next_1_hours", {})
        if not n1h:
            n1h = entry.get("data", {}).get("next_6_hours", {})
        sc = n1h.get("summary", {}).get("symbol_code")
        if sc:
            upcoming_symbols.append(sc)

    description = generate_description(symbol_code, upcoming_symbols)

    # --- 4-day forecast (noon each day) ---
    forecast: list[dict] = []
    seen_dates: set[str] = {today_str}

    for entry in timeseries:
        entry_time = entry.get("time", "")
        if not entry_time:
            continue

        try:
            dt = datetime.fromisoformat(entry_time.replace("Z", "+00:00"))
        except ValueError:
            continue

        date_str = dt.strftime("%Y-%m-%d")
        if date_str in seen_dates:
            continue

        # Accept entries near noon (11:00–13:00)
        if dt.hour < 11 or dt.hour > 13:
            continue

        entry_temp = entry.get("data", {}).get("instant", {}).get("details", {}).get("air_temperature")
        if entry_temp is None:
            continue

        day_abbrev = WEEKDAY_ABBREV[dt.weekday()]
        forecast.append({"day": day_abbrev, "temp": round(entry_temp)})
        seen_dates.add(date_str)

        if len(forecast) >= 4:
            break

    return {
        "icon": icon,
        "temp": round(temp) if temp is not None else None,
        "description": description,
        "high": high,
        "low": low,
        "wind": wind,
        "forecast": forecast,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch weather data from yr.no for OpenPaper.",
    )
    parser.add_argument(
        "--lat",
        type=float,
        default=59.91,
        help="Latitude (default: 59.91 for Oslo)",
    )
    parser.add_argument(
        "--lon",
        type=float,
        default=10.75,
        help="Longitude (default: 10.75 for Oslo)",
    )
    parser.add_argument(
        "--location-name",
        type=str,
        default="Oslo, Norway",
        help="Display name for the location (default: Oslo, Norway)",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        help="Directory to cache API responses (cached for 1 hour)",
    )

    args = parser.parse_args()

    try:
        data = fetch_weather(args.lat, args.lon, args.cache_dir)
        result = parse_weather(data, args.location_name)
    except httpx.HTTPStatusError as exc:
        print(f"Error: HTTP {exc.response.status_code} from yr.no", file=sys.stderr)
        result = placeholder_output()
    except httpx.RequestError as exc:
        print(f"Error: failed to reach yr.no: {exc}", file=sys.stderr)
        result = placeholder_output()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        result = placeholder_output()

    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    print()  # trailing newline


if __name__ == "__main__":
    main()
