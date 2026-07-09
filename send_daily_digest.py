"""CLI entry point for scheduled daily weather digest emails."""

from __future__ import annotations

import logging
import sys
from datetime import datetime

from config import DEFAULT_CITIES, ensure_log_dir, get_digest_timezone
from emailer import send_weather_email
from formatter import format_report_markdown
from james_clear import sync_james_clear_quotes
from quotes import fetch_digest_inspiration
from weather import build_weather_report


def setup_logging() -> logging.Logger:
    log_dir = ensure_log_dir()
    log_file = log_dir / "digest.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    return logging.getLogger("weather_digest")


def main() -> int:
    logger = setup_logging()
    logger.info("Starting daily weather digest")

    try:
        # Pull any new 3-2-1 emails since last run (ideas + quotes + questions).
        quote_sync = sync_james_clear_quotes(only_new=True)
        logger.info(
            "James Clear sync (%s): emails=%s ideas=%s quotes=%s questions=%s "
            "added=%s quote_total=%s question_total=%s",
            quote_sync.get("mode"),
            quote_sync.get("emails_scanned"),
            quote_sync.get("ideas_extracted"),
            quote_sync.get("quotes_extracted"),
            quote_sync.get("questions_extracted"),
            quote_sync.get("entries_added"),
            quote_sync.get("quotes_total"),
            quote_sync.get("questions_total"),
        )
    except Exception:
        logger.exception(
            "James Clear quote sync failed; continuing with existing/local quotes"
        )

    try:
        report = build_weather_report(DEFAULT_CITIES, get_digest_timezone())
    except Exception:
        logger.exception("Failed to build weather report")
        return 1

    for city in report.cities:
        if city.error:
            logger.warning("%s: %s", city.city_name, city.error)
        else:
            logger.info("Fetched weather for %s", city.city_name)

    if report.all_failed:
        logger.error("All cities failed; email not sent")
        return 1

    inspiration = fetch_digest_inspiration(mark_used=True)
    if inspiration:
        logger.info(
            "Using 3-2-1 issue: %s (ideas=%s question=%s)",
            inspiration.subject,
            len(inspiration.ideas),
            bool(inspiration.question),
        )
    else:
        logger.warning("No James Clear 3-2-1 issue available for this digest")

    try:
        result = send_weather_email(report, inspiration=inspiration)
        logger.info(result)
    except Exception:
        logger.exception("Failed to send weather email")
        return 1

    logger.info("Digest completed at %s", datetime.now().isoformat())
    print(format_report_markdown(report, inspiration))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
