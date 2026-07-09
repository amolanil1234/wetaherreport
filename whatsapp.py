"""Send weather digest via WhatsApp using CallMeBot."""

from __future__ import annotations

import httpx

from config import get_whatsapp_api_key, get_whatsapp_phone, is_whatsapp_enabled
from formatter import format_report_whatsapp
from weather import WeatherReport

CALLMEBOT_URL = "https://api.callmebot.com/whatsapp.php"


def send_weather_whatsapp(report: WeatherReport) -> str:
    if not is_whatsapp_enabled():
        raise ValueError(
            "WhatsApp is not configured. Set WHATSAPP_PHONE and WHATSAPP_APIKEY in .env. "
            "Get an API key: add +34 644 53 78 49 as a contact, message it on WhatsApp with "
            "'I allow callmebot to send me messages', then save the apikey they reply with. "
            "See https://www.callmebot.com/blog/free-api-whatsapp-messages/"
        )

    phone = get_whatsapp_phone()
    apikey = get_whatsapp_api_key()
    text = format_report_whatsapp(report)

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(
                CALLMEBOT_URL,
                params={"phone": phone, "text": text, "apikey": apikey},
            )
            response.raise_for_status()
            body = response.text.strip()
    except Exception as exc:
        raise RuntimeError(f"Failed to send WhatsApp message: {exc}") from exc

    if "ERROR" in body.upper() or "invalid" in body.lower():
        raise RuntimeError(f"CallMeBot rejected the request: {body}")

    return f"WhatsApp sent to {phone} ({body or 'OK'})"
