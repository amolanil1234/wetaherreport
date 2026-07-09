"""Smoke tests for weather fetch and optional live email send."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import DEFAULT_CITIES, should_send_live_email
from emailer import send_weather_email
from formatter import format_report_markdown, format_report_text
from weather import build_weather_report, geocode_city


def main() -> int:
    print("=== Geocoding checks ===")
    for city in DEFAULT_CITIES:
        coords = geocode_city(city.name, city.country_code)
        print(
            f"OK {city.name}: {coords.name}, {coords.country} "
            f"({coords.latitude}, {coords.longitude}) tz={coords.timezone}"
        )

    print("\n=== Weather report ===")
    report = build_weather_report(DEFAULT_CITIES)
    print(format_report_markdown(report))

    failed = [city.city_name for city in report.cities if city.error]
    if failed:
        print(f"\nFAILED cities: {', '.join(failed)}")
        return 1

    print("\n=== Plain-text preview (first 20 lines) ===")
    preview_lines = format_report_text(report).splitlines()[:20]
    print("\n".join(preview_lines))

    if should_send_live_email():
        print("\n=== Sending live email (SEND_LIVE_EMAIL=1) ===")
        result = send_weather_email(report)
        print(result)
    else:
        print("\nSkipping live email (set SEND_LIVE_EMAIL=1 in .env to send)")

    print("\nAll smoke tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
