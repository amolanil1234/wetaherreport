"""Fetch a fresh inspirational quote — prefer James Clear 3-2-1 ideas, else ZenQuotes."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass

import httpx

from james_clear import list_stored_quotes

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


def _quote_from_james_clear() -> Quote | None:
    # Prefer James Clear's own ideas; fall back to quotes-from-others in the DB.
    ideas = list_stored_quotes(kinds={"idea"})
    pool = ideas or list_stored_quotes(kinds={"quote"})
    if not pool:
        return None
    pick = random.choice(pool)
    return Quote(text=pick.text, author=pick.author, source=pick.source)


def fetch_live_quote() -> Quote:
    """Prefer James Clear DB entries; else ZenQuotes; else local fallback."""
    local = _quote_from_james_clear()
    if local:
        return local

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
