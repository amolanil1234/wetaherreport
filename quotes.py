"""Fetch a fresh random inspirational quote from the internet each time."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass

import httpx

# ZenQuotes /api/today is the same all day — use /api/random only.
ZENQUOTES_RANDOM_URL = "https://zenquotes.io/api/random"

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


def fetch_live_quote() -> Quote:
    """Fetch a new random quote on every call (ZenQuotes only + local fallback)."""
    bust = str(int(time.time() * 1000))
    try:
        with httpx.Client(timeout=15.0, headers={"Cache-Control": "no-cache"}) as client:
            response = client.get(
                ZENQUOTES_RANDOM_URL,
                params={"_t": bust + str(random.randint(1, 9999))},
            )
            response.raise_for_status()
            quote = _parse_zenquotes(response.json())
            if quote:
                return quote
    except Exception:
        pass

    text, author = random.choice(FALLBACK_QUOTES)
    return Quote(text=text, author=author, source="local")
