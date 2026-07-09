"""Fetch James Clear 3-2-1 emails and store ideas, quotes, and questions locally."""

from __future__ import annotations

import email
import email.header
import email.utils
import imaplib
import json
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email.message import Message
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable, Literal
from urllib.parse import urlparse

import httpx

from config import PROJECT_ROOT, get_env, get_smtp_config

QUOTES_DB_PATH = PROJECT_ROOT / "data" / "james_clear_quotes.json"
DEFAULT_SENDER = "james@jamesclear.com"
DEFAULT_SUBJECT_MARKER = "3-2-1:"
DEFAULT_AUTHOR = "James Clear"
DEFAULT_SOURCE = "James Clear 3-2-1"
ARCHIVE_URL = "https://jamesclear.com/3-2-1"
HTTP_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; WeatherDigest/1.0)"}

EntryKind = Literal["idea", "quote", "question"]


@dataclass(frozen=True)
class StoredQuote:
    id: str
    text: str
    author: str
    source: str
    email_subject: str
    email_date: str
    message_id: str
    idea_index: int
    kind: EntryKind = "idea"


class _HTMLToText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        if lowered in {"script", "style"}:
            self._skip = True
        elif lowered in {"br", "p", "div", "tr", "li", "h1", "h2", "h3", "h4"}:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style"}:
            self._skip = False
        elif tag.lower() in {"p", "div", "tr", "li", "h1", "h2", "h3", "h4"}:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self._parts.append(data)

    def get_text(self) -> str:
        return "".join(self._parts)


def _decode_header(value: str | None) -> str:
    if not value:
        return ""
    parts: list[str] = []
    for chunk, charset in email.header.decode_header(value):
        if isinstance(chunk, bytes):
            parts.append(chunk.decode(charset or "utf-8", errors="replace"))
        else:
            parts.append(chunk)
    return "".join(parts).strip()


def _html_to_text(html: str) -> str:
    parser = _HTMLToText()
    parser.feed(html)
    parser.close()
    return parser.get_text()


def _message_body_text(msg: Message) -> str:
    plain_parts: list[str] = []
    html_parts: list[str] = []

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition") or "")
            if "attachment" in disposition.lower():
                continue
            payload = part.get_payload(decode=True)
            if not isinstance(payload, bytes):
                continue
            charset = part.get_content_charset() or "utf-8"
            text = payload.decode(charset, errors="replace")
            if content_type == "text/plain":
                plain_parts.append(text)
            elif content_type == "text/html":
                html_parts.append(_html_to_text(text))
    else:
        payload = msg.get_payload(decode=True)
        if isinstance(payload, bytes):
            charset = msg.get_content_charset() or "utf-8"
            text = payload.decode(charset, errors="replace")
            if msg.get_content_type() == "text/html":
                html_parts.append(_html_to_text(text))
            else:
                plain_parts.append(text)

    raw = "\n".join(plain_parts) if plain_parts else "\n".join(html_parts)
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    raw = re.sub(r"[ \t]+\n", "\n", raw)
    raw = re.sub(r"\n{3,}", "\n\n", raw)
    return raw.strip()


def _strip_invisible(text: str) -> str:
    return (
        text.replace("\u200b", "")
        .replace("\u200c", "")
        .replace("\u200d", "")
        .replace("\ufeff", "")
        .replace("\xa0", " ")
    )


def _normalize_text(text: str) -> str:
    text = _strip_invisible(text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"-{3,}", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    text = text.strip(" \n\t\"'“”‘’")
    lines = [line.strip(" \t\"'“”‘’") for line in text.split("\n") if line.strip()]
    cleaned = " ".join(lines).strip(" \t\"'“”‘’")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = re.sub(r"\s*\(\s*\)\s*", " ", cleaned).strip()
    return cleaned


_ROMAN_OR_NUM = r"(?:I{1,3}|IV|V|VI|VII|VIII|IX|X|\d+)"
_ITEM_MARKER = re.compile(rf"(?im)^\s*{_ROMAN_OR_NUM}\s*[.)]\s*$")
_SECTION_IDEAS = re.compile(r"(?im)^\s*3\s+ideas\s+from\s+me\s*$")
_SECTION_QUOTES = re.compile(r"(?im)^\s*2\s+quotes\s+from\s+others\s*$")
_SECTION_QUESTION = re.compile(r"(?im)^\s*1\s+question\s+for\s+you\s*$")
_SHARE_OR_SIGN_OFF = re.compile(
    r"(?im)^\s*(?:want to share this issue|until next week|james clear)\b"
)


def _slice_section(body: str, start_re: re.Pattern[str], end_res: list[re.Pattern[str]]) -> str:
    start = start_re.search(body)
    if not start:
        return ""
    rest = body[start.end() :]
    end_pos = len(rest)
    for end_re in end_res:
        match = end_re.search(rest)
        if match and match.start() < end_pos:
            end_pos = match.start()
    section = rest[:end_pos]
    section = re.sub(r"(?m)^\s*-{3,}\s*$", "", section).strip()
    return section


def _split_numbered_chunks(section: str) -> list[str]:
    if not section:
        return []
    chunks = _ITEM_MARKER.split(section)
    items: list[str] = []
    for chunk in chunks:
        cleaned = _normalize_text(chunk)
        if len(cleaned) < 12:
            continue
        lowered = cleaned.lower()
        if lowered.startswith("here are") or lowered.startswith("this week"):
            continue
        if set(cleaned) <= {"-", " "}:
            continue
        items.append(cleaned)
    return items


def extract_ideas_from_me(body: str) -> list[str]:
    body = _strip_invisible(body)
    section = _slice_section(body, _SECTION_IDEAS, [_SECTION_QUOTES, _SECTION_QUESTION])
    return _split_numbered_chunks(section)[:3]


def _author_from_quote_intro(chunk: str) -> tuple[str, str]:
    """
    Split an 'others' quote chunk into (author, quote_text).
    Typical shape: Intro naming the person... then a quoted passage.
    """
    raw = _strip_invisible(chunk)
    raw = re.sub(r"(?im)^\s*source:.*$", "", raw)
    raw = re.sub(r"https?://\S+", "", raw).strip()

    quote_match = re.search(r"[\"“](.+?)[\"”]\s*$", raw, flags=re.S)
    if not quote_match:
        quote_match = re.search(r"[\"“](.+?)[\"”]", raw, flags=re.S)

    if quote_match:
        quote_text = _normalize_text(quote_match.group(1))
        intro = raw[: quote_match.start()]
    else:
        quote_text = _normalize_text(raw)
        intro = ""

    author = DEFAULT_AUTHOR
    intro_clean = _normalize_text(intro)
    intro_clean = re.sub(r"(?i)\bsource:.*$", "", intro_clean).strip()
    if intro_clean:
        # Proper name (optional initials) right before ",", "on", "reminds", etc.
        name_re = (
            r"((?:[A-Z][A-Za-z]*\.\s*)*[A-Z][A-Za-z.'\-]+"
            r"(?:\s+[A-Z][A-Za-z.'\-]+){0,3})"
        )
        patterns = [
            rf"{name_re}\s*,",
            rf"{name_re}\s+(?:on|reminds|about|writes|said|says|notes)\b",
            rf"(?i)(?:from|poet|author|writer|historian|philosopher|coach)\s+{name_re}",
        ]
        for pattern in patterns:
            match = re.search(pattern, intro_clean)
            if match:
                candidate = match.group(1).strip(" ,:")
                candidate = re.sub(
                    r"(?i)^(poet|author|writer|historian|philosopher|coach|"
                    r"artist|critic|movie critic)\s+",
                    "",
                    candidate,
                ).strip()
                if candidate:
                    author = candidate
                break

    quote_text = re.sub(r"(?i)\bsource:.*$", "", quote_text).strip()
    return author, quote_text


def extract_quotes_from_others(body: str) -> list[tuple[str, str]]:
    body = _strip_invisible(body)
    section = _slice_section(body, _SECTION_QUOTES, [_SECTION_QUESTION, _SHARE_OR_SIGN_OFF])
    chunks = _ITEM_MARKER.split(section)
    quotes: list[tuple[str, str]] = []
    for chunk in chunks:
        if not chunk.strip():
            continue
        author, text = _author_from_quote_intro(chunk)
        if len(text) < 12:
            continue
        quotes.append((author, text))
        if len(quotes) >= 2:
            break
    return quotes


def extract_question_for_you(body: str) -> str | None:
    body = _strip_invisible(body)
    section = _slice_section(body, _SECTION_QUESTION, [_SHARE_OR_SIGN_OFF])
    if not section:
        return None

    # Prefer the actual question sentence(s).
    cleaned_lines: list[str] = []
    for line in section.split("\n"):
        line = line.strip()
        if not line or set(line) <= {"-", " "}:
            continue
        if re.match(r"(?i)^(want to share|until next week|james clear|source:)", line):
            break
        cleaned_lines.append(line)

    text = _normalize_text("\n".join(cleaned_lines))
    if not text:
        return None

    # If multiple sentences, keep from the first question mark sentence if present.
    if "?" in text:
        parts = re.split(r"(?<=[?])\s+", text)
        question_parts = [p for p in parts if "?" in p]
        if question_parts:
            # Keep short lead-in + the question when lead-in is brief.
            lead = parts[0] if parts and "?" not in parts[0] and len(parts[0]) < 180 else ""
            joined = " ".join(([lead] if lead else []) + question_parts[:1]).strip()
            return joined or question_parts[0]
    return text


def entries_from_body(
    message_id: str,
    subject: str,
    date_iso: str,
    body: str,
) -> list[StoredQuote]:
    entries: list[StoredQuote] = []

    for index, idea in enumerate(extract_ideas_from_me(body), start=1):
        entries.append(
            StoredQuote(
                id=f"{message_id}#idea#{index}",
                text=idea,
                author=DEFAULT_AUTHOR,
                source=DEFAULT_SOURCE,
                email_subject=subject,
                email_date=date_iso,
                message_id=message_id,
                idea_index=index,
                kind="idea",
            )
        )

    for index, (author, quote_text) in enumerate(extract_quotes_from_others(body), start=1):
        entries.append(
            StoredQuote(
                id=f"{message_id}#quote#{index}",
                text=quote_text,
                author=author,
                source=DEFAULT_SOURCE,
                email_subject=subject,
                email_date=date_iso,
                message_id=message_id,
                idea_index=index,
                kind="quote",
            )
        )

    question = extract_question_for_you(body)
    if question:
        entries.append(
            StoredQuote(
                id=f"{message_id}#question#1",
                text=question,
                author=DEFAULT_AUTHOR,
                source=DEFAULT_SOURCE,
                email_subject=subject,
                email_date=date_iso,
                message_id=message_id,
                idea_index=1,
                kind="question",
            )
        )

    return entries


def _imap_credentials() -> tuple[str, int, str, str]:
    host = get_env("IMAP_HOST", "imap.gmail.com") or "imap.gmail.com"
    port = int(get_env("IMAP_PORT", "993") or "993")
    user = get_env("IMAP_USER") or get_env("SMTP_USER")
    password = get_env("IMAP_PASS") or get_env("SMTP_PASS")
    if not user or not password:
        smtp = get_smtp_config()
        user = user or smtp.user
        password = password or smtp.password
    if not user or not password:
        raise ValueError(
            "IMAP credentials missing. Set IMAP_USER/IMAP_PASS "
            "or SMTP_USER/SMTP_PASS (Gmail App Password)."
        )
    return host, port, user, password


def _search_criteria(sender: str, subject_marker: str) -> str:
    return f'(FROM "{sender}" SUBJECT "{subject_marker}")'


def _parse_fetched_message(
    msg_id: bytes, raw: bytes
) -> tuple[str, str, str, str] | None:
    msg = email.message_from_bytes(raw)
    message_id = (_decode_header(msg.get("Message-ID")) or msg_id.decode()).strip()
    subject = _decode_header(msg.get("Subject")).replace("\r\n", " ").replace("\n", " ")
    subject = re.sub(r"\s+", " ", subject).strip()
    date_header = msg.get("Date") or ""
    try:
        date_tuple = email.utils.parsedate_to_datetime(date_header)
        if date_tuple.tzinfo is None:
            date_tuple = date_tuple.replace(tzinfo=timezone.utc)
        date_iso = date_tuple.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError, IndexError, OverflowError):
        date_iso = datetime.now(timezone.utc).isoformat()
    body = _message_body_text(msg)
    return message_id, subject, date_iso, body


def _html_page_to_text(html: str) -> str:
    parser = _HTMLToText()
    parser.feed(html)
    parser.close()
    raw = parser.get_text()
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    raw = re.sub(r"[ \t]+\n", "\n", raw)
    raw = re.sub(r"\n{3,}", "\n\n", raw)
    return _strip_invisible(raw).strip()


def _slug_to_date_iso(slug: str) -> str:
    """Convert july-2-2026 → ISO date at noon UTC."""
    match = re.fullmatch(
        r"(january|february|march|april|may|june|july|august|september|"
        r"october|november|december)-(\d{1,2})-(\d{4})",
        slug.lower(),
    )
    if not match:
        return datetime.now(timezone.utc).isoformat()
    month_name, day, year = match.groups()
    months = {
        "january": 1,
        "february": 2,
        "march": 3,
        "april": 4,
        "may": 5,
        "june": 6,
        "july": 7,
        "august": 8,
        "september": 9,
        "october": 10,
        "november": 11,
        "december": 12,
    }
    try:
        dt = datetime(int(year), months[month_name], int(day), 12, 0, tzinfo=timezone.utc)
        return dt.isoformat()
    except (ValueError, KeyError):
        return datetime.now(timezone.utc).isoformat()


def _title_from_html(html: str, fallback_slug: str) -> str:
    for pattern in (
        r'property="og:title"\s+content="([^"]+)"',
        r"<h1[^>]*>(.*?)</h1>",
        r"<title>(.*?)</title>",
    ):
        match = re.search(pattern, html, flags=re.I | re.S)
        if not match:
            continue
        title = re.sub(r"<[^>]+>", "", match.group(1))
        title = re.sub(r"\s+", " ", title).strip()
        title = re.sub(r"\s*[-|]\s*James Clear\s*$", "", title, flags=re.I).strip()
        if title.lower().startswith("3-2-1"):
            return title

    parts = fallback_slug.split("-")
    if len(parts) >= 3:
        return f"3-2-1: {parts[0].title()} {parts[1]}, {parts[-1]}"
    return f"3-2-1: {fallback_slug}"


def list_web_issue_urls(limit: int | None = None) -> list[str]:
    """Return issue URLs from https://jamesclear.com/3-2-1, newest first."""
    with httpx.Client(timeout=30.0, headers=HTTP_HEADERS, follow_redirects=True) as client:
        response = client.get(ARCHIVE_URL)
        response.raise_for_status()
        html = response.text

    urls = sorted(
        set(re.findall(r'href="(https://jamesclear\.com/3-2-1/[^"#?]+)"', html))
    )
    # Prefer date-like slugs and sort by parsed date descending.
    dated: list[tuple[str, str]] = []
    for url in urls:
        slug = url.rstrip("/").rsplit("/", 1)[-1]
        if re.fullmatch(
            r"(january|february|march|april|may|june|july|august|september|"
            r"october|november|december)-\d{1,2}-\d{4}",
            slug.lower(),
        ):
            dated.append((_slug_to_date_iso(slug), url))
    dated.sort(key=lambda item: item[0], reverse=True)
    ordered = [url for _, url in dated]
    if limit is not None:
        return ordered[: max(1, limit)]
    return ordered


def fetch_321_web_messages(
    *,
    limit: int | None = None,
    only_new: bool = False,
    known_message_ids: set[str] | None = None,
) -> list[tuple[str, str, str, str]]:
    """
    Fetch 3-2-1 issues from jamesclear.com as
    (message_id, subject, date_iso, body_text), newest first.
    """
    known = known_message_ids
    if only_new and known is None:
        known = known_message_ids_from_db()

    urls = list_web_issue_urls(limit=None if only_new else limit)
    results: list[tuple[str, str, str, str]] = []

    with httpx.Client(timeout=30.0, headers=HTTP_HEADERS, follow_redirects=True) as client:
        for url in urls:
            message_id = url.rstrip("/")
            if only_new and known and message_id in known:
                continue
            slug = urlparse(message_id).path.rstrip("/").rsplit("/", 1)[-1]
            date_iso = _slug_to_date_iso(slug)
            try:
                response = client.get(url)
                response.raise_for_status()
            except Exception:
                continue
            html = response.text
            subject = _title_from_html(html, slug)
            body = _html_page_to_text(html)
            if not extract_ideas_from_me(body) and not extract_question_for_you(body):
                continue
            results.append((message_id, subject, date_iso, body))
            if limit is not None and len(results) >= max(1, limit):
                break

    results.sort(key=lambda item: item[2], reverse=True)
    return results


def fetch_321_messages(
    *,
    limit: int | None = None,
    only_new: bool = False,
    known_message_ids: set[str] | None = None,
    sender: str | None = None,
    subject_marker: str | None = None,
    mailbox: str | None = None,
) -> list[tuple[str, str, str, str]]:
    """
    Return matching emails as (message_id, subject, date_iso, body_text), newest first.

    - limit=None → all matching emails
    - only_new=True → skip message IDs already in known_message_ids / DB
    """
    sender = sender or get_env("JAMES_CLEAR_SENDER", DEFAULT_SENDER) or DEFAULT_SENDER
    subject_marker = (
        subject_marker
        or get_env("JAMES_CLEAR_SUBJECT_MARKER", DEFAULT_SUBJECT_MARKER)
        or DEFAULT_SUBJECT_MARKER
    )
    mailbox = mailbox or get_env("IMAP_MAILBOX", "INBOX") or "INBOX"
    known = known_message_ids
    if only_new and known is None:
        known = known_message_ids_from_db()

    host, port, user, password = _imap_credentials()
    results: list[tuple[str, str, str, str]] = []

    with imaplib.IMAP4_SSL(host, port) as client:
        client.login(user, password)
        status, _ = client.select(mailbox, readonly=True)
        if status != "OK":
            raise RuntimeError(f"Could not open mailbox: {mailbox}")

        status, data = client.search(None, _search_criteria(sender, subject_marker))
        if status != "OK" or not data or not data[0]:
            return []

        ids = data[0].split()
        # Newest last in IMAP search order.
        ordered = list(reversed(ids))
        if limit is not None:
            ordered = ordered[: max(1, limit)]

        for msg_id in ordered:
            status, fetched = client.fetch(msg_id, "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID)])")
            header_message_id = ""
            if status == "OK" and fetched and fetched[0]:
                header_raw = fetched[0][1]
                if isinstance(header_raw, bytes):
                    header_message_id = _decode_header(
                        email.message_from_bytes(header_raw).get("Message-ID")
                    ).strip()

            if only_new and known and header_message_id and header_message_id in known:
                continue

            status, fetched = client.fetch(msg_id, "(RFC822)")
            if status != "OK" or not fetched or not fetched[0]:
                continue
            raw = fetched[0][1]
            if not isinstance(raw, bytes):
                continue
            parsed = _parse_fetched_message(msg_id, raw)
            if not parsed:
                continue
            message_id, subject, date_iso, body = parsed
            if only_new and known and message_id in known:
                continue
            results.append((message_id, subject, date_iso, body))

    results.sort(key=lambda item: item[2], reverse=True)
    return results


def fetch_recent_321_messages(
    limit: int = 5,
    *,
    sender: str | None = None,
    subject_marker: str | None = None,
    mailbox: str | None = None,
) -> list[tuple[str, str, str, str]]:
    """Backward-compatible helper: newest N emails."""
    return fetch_321_messages(
        limit=limit,
        sender=sender,
        subject_marker=subject_marker,
        mailbox=mailbox,
    )


def entries_from_messages(
    messages: Iterable[tuple[str, str, str, str]],
) -> list[StoredQuote]:
    entries: list[StoredQuote] = []
    for message_id, subject, date_iso, body in messages:
        entries.extend(entries_from_body(message_id, subject, date_iso, body))
    return entries


def quotes_from_messages(
    messages: Iterable[tuple[str, str, str, str]],
) -> list[StoredQuote]:
    """Backward-compatible alias."""
    return entries_from_messages(messages)


def load_quote_db(path: Path | None = None) -> dict:
    db_path = path or QUOTES_DB_PATH
    if not db_path.exists():
        return {
            "updated_at": None,
            "synced_message_ids": [],
            "used_in_digest_message_ids": [],
            "quotes": [],
            "questions": [],
        }
    with db_path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        return {
            "updated_at": None,
            "synced_message_ids": [],
            "used_in_digest_message_ids": [],
            "quotes": [],
            "questions": [],
        }
    if not isinstance(data.get("quotes"), list):
        data["quotes"] = []
    if not isinstance(data.get("questions"), list):
        data["questions"] = []
    if not isinstance(data.get("synced_message_ids"), list):
        data["synced_message_ids"] = []
    if not isinstance(data.get("used_in_digest_message_ids"), list):
        data["used_in_digest_message_ids"] = []
    return data


def save_quote_db(data: dict, path: Path | None = None) -> Path:
    db_path = path or QUOTES_DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with db_path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return db_path


def known_message_ids_from_db(path: Path | None = None) -> set[str]:
    db = load_quote_db(path)
    ids = {str(item) for item in db.get("synced_message_ids") or []}
    for item in list(db.get("quotes") or []) + list(db.get("questions") or []):
        if isinstance(item, dict) and item.get("message_id"):
            ids.add(str(item["message_id"]))
    return ids


def _sort_key(item: dict) -> tuple[str, str, int]:
    return (
        str(item.get("email_date") or ""),
        str(item.get("kind") or ""),
        int(item.get("idea_index") or 0),
    )


def merge_entries(
    existing_quotes: list[dict],
    existing_questions: list[dict],
    incoming: list[StoredQuote],
    *,
    replace_message_ids: set[str] | None = None,
) -> tuple[list[dict], list[dict], int]:
    quote_by_id = {
        str(item.get("id")): item
        for item in existing_quotes
        if isinstance(item, dict)
    }
    question_by_id = {
        str(item.get("id")): item
        for item in existing_questions
        if isinstance(item, dict)
    }

    if replace_message_ids:
        quote_by_id = {
            key: value
            for key, value in quote_by_id.items()
            if str(value.get("message_id") or "") not in replace_message_ids
        }
        question_by_id = {
            key: value
            for key, value in question_by_id.items()
            if str(value.get("message_id") or "") not in replace_message_ids
        }

    added = 0
    for entry in incoming:
        payload = asdict(entry)
        target = question_by_id if entry.kind == "question" else quote_by_id
        if entry.id not in target:
            added += 1
        target[entry.id] = payload

    quotes = sorted(quote_by_id.values(), key=_sort_key, reverse=True)
    questions = sorted(question_by_id.values(), key=_sort_key, reverse=True)
    return quotes, questions, added


def sync_james_clear_quotes(
    limit: int | None = None,
    *,
    only_new: bool = False,
    full: bool = False,
    source: str | None = None,
) -> dict:
    """
    Sync 3-2-1 issues into the local JSON DB.

    source:
      - "web" (default): scrape https://jamesclear.com/3-2-1
      - "email": Gmail IMAP
      - "auto": try web first, fall back to email
    """
    if full:
        limit = None
        only_new = False

    preferred = (source or get_env("JAMES_CLEAR_SOURCE", "web") or "web").lower()
    if preferred not in {"web", "email", "auto"}:
        preferred = "web"

    known = known_message_ids_from_db() if only_new else None
    messages: list[tuple[str, str, str, str]] = []
    used_source = preferred
    errors: list[str] = []

    def _fetch(src: str) -> list[tuple[str, str, str, str]]:
        if src == "web":
            return fetch_321_web_messages(
                limit=limit, only_new=only_new, known_message_ids=known
            )
        return fetch_321_messages(
            limit=limit, only_new=only_new, known_message_ids=known
        )

    if preferred == "auto":
        try:
            messages = _fetch("web")
            used_source = "web"
        except Exception as exc:
            errors.append(f"web: {exc}")
            messages = _fetch("email")
            used_source = "email"
    else:
        try:
            messages = _fetch(preferred)
            used_source = preferred
        except Exception as exc:
            if preferred == "web":
                errors.append(f"web: {exc}")
                messages = _fetch("email")
                used_source = "email"
            else:
                raise

    incoming = entries_from_messages(messages)

    db = load_quote_db()
    existing_quotes = list(db.get("quotes") or [])
    existing_questions = list(db.get("questions") or [])
    scanned_ids = {message_id for message_id, _, _, _ in messages}

    # On full/limited resync, replace entries for scanned messages so parser fixes apply.
    replace_ids = scanned_ids if not only_new else None
    quotes, questions, added = merge_entries(
        existing_quotes,
        existing_questions,
        incoming,
        replace_message_ids=replace_ids,
    )

    synced_ids = set(str(item) for item in db.get("synced_message_ids") or [])
    synced_ids.update(scanned_ids)
    for item in quotes + questions:
        if item.get("message_id"):
            synced_ids.add(str(item["message_id"]))

    db["quotes"] = quotes
    db["questions"] = questions
    db["synced_message_ids"] = sorted(synced_ids)
    db["updated_at"] = datetime.now(timezone.utc).isoformat()
    path = save_quote_db(db)

    ideas = sum(1 for item in incoming if item.kind == "idea")
    others = sum(1 for item in incoming if item.kind == "quote")
    qs = sum(1 for item in incoming if item.kind == "question")

    return {
        "source": used_source,
        "mode": "new_only" if only_new else ("full" if limit is None else f"limit:{limit}"),
        "issues_scanned": len(messages),
        "emails_scanned": len(messages),
        "ideas_extracted": ideas,
        "quotes_extracted": others,
        "questions_extracted": qs,
        "entries_added": added,
        "quotes_total": len(quotes),
        "questions_total": len(questions),
        "emails_tracked": len(synced_ids),
        "db_path": str(path),
        "subjects": [subject for _, subject, _, _ in messages],
        "errors": errors,
    }


def _coerce_kind(value: object) -> EntryKind:
    if value == "quote":
        return "quote"
    if value == "question":
        return "question"
    return "idea"


def list_stored_quotes(
    path: Path | None = None,
    *,
    kinds: set[EntryKind] | None = None,
) -> list[StoredQuote]:
    """Return stored inspiration entries (ideas + quotes by default)."""
    db = load_quote_db(path)
    wanted = kinds or {"idea", "quote"}
    rows: list[dict] = []
    if "idea" in wanted or "quote" in wanted:
        rows.extend(item for item in db.get("quotes") or [] if isinstance(item, dict))
    if "question" in wanted:
        rows.extend(item for item in db.get("questions") or [] if isinstance(item, dict))

    quotes: list[StoredQuote] = []
    for item in rows:
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        kind = _coerce_kind(item.get("kind"))
        # Legacy rows without kind are ideas.
        if "kind" not in item:
            kind = "idea"
        if kind not in wanted:
            continue
        quotes.append(
            StoredQuote(
                id=str(item.get("id") or text),
                text=text,
                author=str(item.get("author") or DEFAULT_AUTHOR),
                source=str(item.get("source") or DEFAULT_SOURCE),
                email_subject=str(item.get("email_subject") or ""),
                email_date=str(item.get("email_date") or ""),
                message_id=str(item.get("message_id") or ""),
                idea_index=int(item.get("idea_index") or 0),
                kind=kind,
            )
        )
    return quotes


def list_stored_questions(path: Path | None = None) -> list[StoredQuote]:
    return list_stored_quotes(path, kinds={"question"})


@dataclass(frozen=True)
class Latest321Issue:
    email_subject: str
    email_date: str
    message_id: str
    ideas: tuple[StoredQuote, ...]
    question: StoredQuote | None


def _issue_from_message_id(
    message_id: str,
    ideas: list[StoredQuote],
    questions: list[StoredQuote],
) -> Latest321Issue | None:
    if not message_id:
        return None
    issue_ideas = tuple(
        sorted(
            (item for item in ideas if item.message_id == message_id),
            key=lambda item: item.idea_index,
        )
    )
    issue_question = next(
        (item for item in questions if item.message_id == message_id),
        None,
    )
    if not issue_ideas and not issue_question:
        return None
    subject = (
        issue_ideas[0].email_subject
        if issue_ideas
        else (issue_question.email_subject if issue_question else "")
    )
    email_date = (
        issue_ideas[0].email_date
        if issue_ideas
        else (issue_question.email_date if issue_question else "")
    )
    return Latest321Issue(
        email_subject=subject,
        email_date=email_date,
        message_id=message_id,
        ideas=issue_ideas,
        question=issue_question,
    )


def list_321_issues(path: Path | None = None) -> list[Latest321Issue]:
    """All synced issues, newest first (deduped by date + subject; prefer web URLs)."""
    ideas = list_stored_quotes(path, kinds={"idea"})
    questions = list_stored_questions(path)
    if not ideas and not questions:
        return []

    by_id: dict[str, str] = {}
    for item in ideas + questions:
        if not item.message_id:
            continue
        prev = by_id.get(item.message_id, "")
        if item.email_date >= prev:
            by_id[item.message_id] = item.email_date

    # Prefer website URLs over email Message-IDs for the same calendar day.
    ordered_ids = sorted(
        by_id.keys(),
        key=lambda mid: (by_id[mid][:10], mid.startswith("http"), by_id[mid]),
        reverse=True,
    )
    issues: list[Latest321Issue] = []
    seen_keys: set[str] = set()
    for message_id in ordered_ids:
        issue = _issue_from_message_id(message_id, ideas, questions)
        if not issue:
            continue
        key = f"{issue.email_date[:10]}|{issue.email_subject.lower().strip()}"
        if key in seen_keys:
            continue
        seen_keys.add(key)
        issues.append(issue)
    return issues


def get_used_digest_message_ids(path: Path | None = None) -> set[str]:
    db = load_quote_db(path)
    return {str(item) for item in db.get("used_in_digest_message_ids") or []}


def mark_issue_used_in_digest(message_id: str, path: Path | None = None) -> None:
    if not message_id:
        return
    db = load_quote_db(path)
    used = [str(item) for item in db.get("used_in_digest_message_ids") or []]
    if message_id not in used:
        used.append(message_id)
    db["used_in_digest_message_ids"] = used
    save_quote_db(db, path)


def reset_used_digest_message_ids(path: Path | None = None) -> None:
    db = load_quote_db(path)
    db["used_in_digest_message_ids"] = []
    save_quote_db(db, path)


def get_latest_321_issue(path: Path | None = None) -> Latest321Issue | None:
    """Return the newest synced 3-2-1 issue with its 3 ideas and 1 question."""
    issues = list_321_issues(path)
    return issues[0] if issues else None


def pick_next_321_issue(
    path: Path | None = None,
    *,
    mark_used: bool = True,
) -> Latest321Issue | None:
    """
    Pick the next unused 3-2-1 issue (newest unused first).

    Once every issue has been used in a digest, the used list resets and
    rotation starts over so digests never get stuck empty.
    """
    issues = list_321_issues(path)
    if not issues:
        return None

    used = get_used_digest_message_ids(path)
    unused = [issue for issue in issues if issue.message_id not in used]
    if not unused:
        reset_used_digest_message_ids(path)
        unused = issues

    pick = unused[0]
    if mark_used:
        mark_issue_used_in_digest(pick.message_id, path)
    return pick


def watch_james_clear_inbox(poll_seconds: int = 300) -> None:
    """Poll IMAP forever and merge any new 3-2-1 emails into the DB."""
    poll_seconds = max(60, poll_seconds)
    print(f"Watching for new James Clear 3-2-1 emails every {poll_seconds}s...")
    while True:
        try:
            summary = sync_james_clear_quotes(only_new=True)
            scanned = summary.get("emails_scanned", 0)
            if scanned:
                print(
                    f"[{datetime.now().isoformat(timespec='seconds')}] "
                    f"new emails={scanned} added={summary.get('entries_added')} "
                    f"quotes={summary.get('quotes_total')} "
                    f"questions={summary.get('questions_total')}"
                )
            else:
                print(
                    f"[{datetime.now().isoformat(timespec='seconds')}] "
                    "no new 3-2-1 emails"
                )
        except Exception as exc:
            print(
                f"[{datetime.now().isoformat(timespec='seconds')}] "
                f"watch sync failed: {exc}"
            )
        time.sleep(poll_seconds)
