"""James Clear 3-2-1 content for the weather digest (ideas + question)."""

from __future__ import annotations

from dataclasses import dataclass

from james_clear import Latest321Issue, get_latest_321_issue


@dataclass(frozen=True)
class DigestInspiration:
    """Latest 3-2-1 issue content shown in the weather email."""

    subject: str
    ideas: tuple[str, ...]
    question: str | None
    source: str = "James Clear 3-2-1"


def fetch_digest_inspiration() -> DigestInspiration | None:
    """Return the newest synced issue's 3 Ideas From Me + 1 Question For You."""
    issue: Latest321Issue | None = get_latest_321_issue()
    if not issue:
        return None
    if not issue.ideas and not issue.question:
        return None
    return DigestInspiration(
        subject=issue.email_subject,
        ideas=tuple(item.text for item in issue.ideas),
        question=issue.question.text if issue.question else None,
        source="James Clear 3-2-1",
    )


# Keep Quote helpers available for any callers that still expect a single quote.
@dataclass(frozen=True)
class Quote:
    text: str
    author: str
    source: str = "James Clear 3-2-1"


def fetch_live_quote() -> Quote:
    """Fallback single-quote helper (first idea from latest issue)."""
    inspiration = fetch_digest_inspiration()
    if inspiration and inspiration.ideas:
        return Quote(
            text=inspiration.ideas[0],
            author="James Clear",
            source=inspiration.source,
        )
    if inspiration and inspiration.question:
        return Quote(
            text=inspiration.question,
            author="James Clear",
            source=inspiration.source,
        )
    return Quote(
        text="Keep showing up.",
        author="James Clear",
        source="local",
    )
