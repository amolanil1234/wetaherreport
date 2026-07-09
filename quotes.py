"""Fetch a fresh random inspirational quote from the internet each time."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass

import httpx

# Prefer random endpoints so each digest gets a different quote.
# ZenQuotes /api/today is intentionally the same all day — do not use it.
ZENQUOTES_RANDOM_URL = "https://zenquotes.io/api/random"
QUOTABLE_RANDOM_URL = "https://api.quotable.io/quotes/random"

FALLBACK_QUOTES: tuple[tuple[str, str], ...] = (
    ("Wherever you go, go with all your heart.", "Confucius"),
    ("Be yourself; everyone else is already taken.", "Oscar Wilde"),
    ("The only way to do great work is to love what you do.", "Steve Jobs"),
    ("In the middle of difficulty lies opportunity.", "Albert Einstein"),
    ("Happiness depends upon ourselves.", "Aristotle"),
    ("Do what you can, with what you have, where you are.", "Theodore Roosevelt"),
    ("It always seems impossible until it's done.", "Nelson Mandela"),
    ("Turn your wounds into wisdom.", "Oprah Winfrey"),
)


@dataclass(frozen=True)
class Quote:
    text: str
    author: str
    source: str = "ZenQuotes"


def _parse_zenquotes(data: object) -> Quote | None:
    if not isinstance(data, list) or not data:
        return None
    item = data[0]
    if not isinstance(item, dict):
        return None
    text = str(item.get("q") or "").strip()
    author = str(item.get("a") or "Unknown").strip()
    if not text:
        return None
    return Quote(text=text, author=author, source="ZenQuotes")


def _parse_quotable(data: object) -> Quote | None:
    item: object
    if isinstance(data, list) and data:
        item = data[0]
    else:
        item = data
    if not isinstance(item, dict):
        return None
    text = str(item.get("content") or "").strip()
    author = str(item.get("author") or "Unknown").strip()
    if not text:
        return None
    return Quote(text=text, author=author, source="Quotable")


def _get_json(url: str, params: dict[str, str] | None = None) -> object | None:
    try:
        with httpx.Client(timeout=15.0, headers={"Cache-Control": "no-cache"}) as client:
            response = client.get(url, params=params)
            response.raise_for_status()
            return response.json()
    except Exception:
        return None


def fetch_live_quote() -> Quote:
    """Fetch a new random quote on every call (not the daily fixed quote)."""
    # Cache-buster so CDNs / free tiers are less likely to reuse one response.
    bust = str(int(time.time() * 1000))

    # Try ZenQuotes random a couple of times for variety.
    seen: set[str] = set()
    for _ in range(2):
        data = _get_json(ZENQUOTES_RANDOM_URL, {"_t": bust + str(random.randint(1, 9999))})
        quote = _parse_zenquotes(data) if data is not None else None
        if quote and quote.text not in seen:
            return quote
        if quote:
            seen.add(quote.text)
        time.sleep(0.2)

    # Alternate free API for a different pool of quotes.
    data = _get_json(QUOTABLE_RANDOM_URL, {"_t": bust})
    quote = _parse_quotable(data) if data is not None else None
    if quote:
        return quote

    text, author = random.choice(FALLBACK_QUOTES)
    return Quote(text=text, author=author, source="local")
