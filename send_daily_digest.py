"""CLI entry point for scheduled daily weather digest emails + WhatsApp."""

from __future__ import annotations

import logging
import sys
from datetime import datetime

from config import DEFAULT_CITIES, ensure_log_dir, get_digest_timezone, is_whatsapp_enabled
from emailer import send_weather_email
from formatter import format_report_markdown
from weather import build_weather_report
from whatsapp import send_weather_whatsapp


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
        logger.error("All cities failed; email/WhatsApp not sent")
        return 1

    email_ok = False
    whatsapp_ok = False
    exit_code = 0

    try:
        result = send_weather_email(report)
        logger.info(result)
        email_ok = True
    except Exception:
        logger.exception("Failed to send weather email")
        exit_code = 1

    if is_whatsapp_enabled():
        try:
            result = send_weather_whatsapp(report)
            logger.info(result)
            whatsapp_ok = True
        except Exception:
            logger.exception("Failed to send WhatsApp message")
            exit_code = 1
    else:
        logger.warning(
            "WhatsApp skipped — set WHATSAPP_APIKEY "
            "(and optional WHATSAPP_PHONE) to enable"
        )

    if email_ok or whatsapp_ok:
        logger.info("Digest completed at %s", datetime.now().isoformat())
        print(format_report_markdown(report))

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
