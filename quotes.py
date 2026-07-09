"""Fetch a live inspirational quote from the internet."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

ZENQUOTES_TODAY_URL = "https://zenquotes.io/api/today"
ZENQUOTES_RANDOM_URL = "https://zenquotes.io/api/random"

FALLBACK_QUOTE = (
    "Wherever you go, go with all your heart.",
    "Confucius",
)


@dataclass(frozen=True)
class Quote:
    text: str
    author: str
    source: str = "ZenQuotes"


def fetch_live_quote() -> Quote:
    """Fetch today's quote; fall back to random, then a local default."""
    for url in (ZENQUOTES_TODAY_URL, ZENQUOTES_RANDOM_URL):
        try:
            with httpx.Client(timeout=15.0) as client:
                response = client.get(url)
                response.raise_for_status()
                data = response.json()
            if isinstance(data, list) and data:
                item = data[0]
                text = str(item.get("q") or "").strip()
                author = str(item.get("a") or "Unknown").strip()
                if text:
                    return Quote(text=text, author=author, source="ZenQuotes")
        except Exception:
            continue

    text, author = FALLBACK_QUOTE
    return Quote(text=text, author=author, source="local")
