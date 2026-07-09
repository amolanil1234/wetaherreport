"""Configuration and defaults for the weather email MCP server."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
LOG_DIR = PROJECT_ROOT / "logs"

load_dotenv(PROJECT_ROOT / ".env")

EmailProvider = Literal["sendgrid", "smtp"]


@dataclass(frozen=True)
class CityConfig:
    name: str
    country_code: str = "IN"


@dataclass(frozen=True)
class SmtpConfig:
    host: str
    port: int
    user: str
    password: str
    secure: bool


DEFAULT_CITIES: tuple[CityConfig, ...] = (
    CityConfig("Delhi"),
    CityConfig("Nagpur"),
)

GEOCODING_API_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_API_URL = "https://api.open-meteo.com/v1/forecast"

OPEN_METEO_ATTRIBUTION = "Weather data by Open-Meteo.com"


def get_env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    return value.strip()


def required_env(name: str) -> str:
    value = get_env(name)
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def get_email_provider() -> EmailProvider:
    explicit = get_env("EMAIL_PROVIDER", "").lower()
    if explicit == "sendgrid":
        return "sendgrid"
    if explicit in {"smtp", "gmail"}:
        return "smtp"
    if get_env("SENDGRID_API_KEY"):
        return "sendgrid"
    if get_env("SMTP_USER") and get_env("SMTP_PASS"):
        return "smtp"
    raise ValueError(
        "Email is not configured. Create c:\\SB\\MCP\\.env with either:\n"
        "  Option A (Gmail): SMTP_USER, SMTP_PASS (App Password), FROM_EMAIL\n"
        "  Option B (SendGrid): SENDGRID_API_KEY, FROM_EMAIL (verified sender)"
    )


def get_sendgrid_api_key() -> str:
    return required_env("SENDGRID_API_KEY")


def get_from_email() -> str:
    # Prefer FROM_EMAIL; for Gmail/SMTP fall back to SMTP_USER.
    value = get_env("FROM_EMAIL") or get_env("SMTP_USER")
    if not value:
        raise ValueError(
            "Missing required environment variable: FROM_EMAIL "
            "(or set SMTP_USER when using Gmail SMTP)"
        )
    return value


def get_to_email() -> str:
    return get_env("TO_EMAIL", "amol.eng@gmail.com") or "amol.eng@gmail.com"


def get_smtp_config() -> SmtpConfig:
    return SmtpConfig(
        host=get_env("SMTP_HOST", "smtp.gmail.com") or "smtp.gmail.com",
        port=int(get_env("SMTP_PORT", "587") or "587"),
        user=required_env("SMTP_USER"),
        password=required_env("SMTP_PASS"),
        secure=get_env("SMTP_SECURE", "false").lower() == "true",
    )


def get_digest_timezone() -> str:
    return get_env("DIGEST_TIMEZONE", "Asia/Kolkata") or "Asia/Kolkata"


def should_send_live_email() -> bool:
    return get_env("SEND_LIVE_EMAIL", "0") == "1"


def get_whatsapp_phone() -> str:
    """Return phone in international format without + (default: India 9604423793)."""
    raw = get_env("WHATSAPP_PHONE", "919604423793") or "919604423793"
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) == 10:
        digits = f"91{digits}"
    return digits


def get_whatsapp_api_key() -> str:
    return required_env("WHATSAPP_APIKEY")


def is_whatsapp_enabled() -> bool:
    return bool(get_env("WHATSAPP_APIKEY"))


def ensure_log_dir() -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    return LOG_DIR
