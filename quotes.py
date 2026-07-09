"""James Clear 3-2-1 content for the weather digest (ideas + question)."""

from __future__ import annotations

from dataclasses import dataclass

from james_clear import Latest321Issue, pick_next_321_issue


@dataclass(frozen=True)
class DigestInspiration:
    """One 3-2-1 issue shown in the weather email."""

    subject: str
    ideas: tuple[str, ...]
    question: str | None
    message_id: str = ""
    source: str = "James Clear 3-2-1"


def fetch_digest_inspiration(*, mark_used: bool = True) -> DigestInspiration | None:
    """
    Return the next unused 3-2-1 issue (3 ideas + 1 question).

    Marks the issue as used so the next digest gets a different set.
    After all issues are used once, rotation starts over.
    """
    issue: Latest321Issue | None = pick_next_321_issue(mark_used=mark_used)
    if not issue:
        return None
    if not issue.ideas and not issue.question:
        return None
    return DigestInspiration(
        subject=issue.email_subject,
        ideas=tuple(item.text for item in issue.ideas),
        question=issue.question.text if issue.question else None,
        message_id=issue.message_id,
        source="James Clear 3-2-1",
    )


@dataclass(frozen=True)
class Quote:
    text: str
    author: str
    source: str = "James Clear 3-2-1"


def fetch_live_quote() -> Quote:
    """Fallback single-quote helper (first idea from next unused issue)."""
    inspiration = fetch_digest_inspiration(mark_used=True)
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
