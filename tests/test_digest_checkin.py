"""Unit + optional live checks for James Clear rotation and digest email.

Safe by default (no email, uses a temp quote DB).

Before check-in:

  # 1) Fast unit tests — how rotation works, no email
  python -m unittest tests.test_digest_checkin -v

  # 2) Same tests + actually send one digest to your inbox
  python tests/test_digest_checkin.py --live

  # Or with env:
  #   PowerShell:  $env:SEND_LIVE_EMAIL=\"1\"; python -m unittest tests.test_digest_checkin -v
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import DEFAULT_CITIES, get_digest_timezone, get_to_email, should_send_live_email
from emailer import send_weather_email
from formatter import build_email_subject, format_ist_clock, format_report_text
from james_clear import (
    _issue_identity_key,
    _used_issue_keys,
    get_used_digest_message_ids,
    list_321_issues,
    mark_issue_used_in_digest,
    pick_next_321_issue,
)
from quotes import fetch_digest_inspiration
from weather import build_weather_report


def _entry(
    *,
    message_id: str,
    subject: str,
    date: str,
    kind: str,
    index: int,
    text: str,
) -> dict:
    return {
        "id": f"{message_id}#{kind}#{index}",
        "text": text,
        "author": "James Clear" if kind != "quote" else "Someone",
        "source": "James Clear 3-2-1",
        "email_subject": subject,
        "email_date": date,
        "message_id": message_id,
        "idea_index": index,
        "kind": kind,
    }


def _build_fixture_db() -> dict:
    """Two distinct issues; issue A also has web + email duplicates."""
    subject_a = "3-2-1: Alpha issue about habits"
    subject_b = "3-2-1: Beta issue about focus"
    date_a = "2026-07-02T12:00:00+00:00"
    date_b = "2026-06-25T12:00:00+00:00"
    web_a = "https://jamesclear.com/3-2-1/july-2-2026"
    email_a = "<alpha-issue@convertkit-mail4.com>"
    web_b = "https://jamesclear.com/3-2-1/june-25-2026"

    quotes: list[dict] = []
    questions: list[dict] = []
    for mid, subject, date in (
        (web_a, subject_a, date_a),
        (email_a, subject_a, "2026-07-02T20:16:04+00:00"),
        (web_b, subject_b, date_b),
    ):
        for index in (1, 2, 3):
            quotes.append(
                _entry(
                    message_id=mid,
                    subject=subject,
                    date=date,
                    kind="idea",
                    index=index,
                    text=f"Idea {index} for {subject}",
                )
            )
        questions.append(
            _entry(
                message_id=mid,
                subject=subject,
                date=date,
                kind="question",
                index=1,
                text=f"Question for {subject}?",
            )
        )

    return {
        "updated_at": "2026-07-11T00:00:00+00:00",
        "synced_message_ids": [web_a, email_a, web_b],
        "used_in_digest_message_ids": [],
        "quotes": quotes,
        "questions": questions,
    }


class IstTimeFormatTest(unittest.TestCase):
    def test_format_ist_clock_examples(self) -> None:
        self.assertEqual(format_ist_clock("2026-07-11T09:00"), "9am IST")
        self.assertEqual(format_ist_clock("2026-07-11T09:30"), "9:30am IST")
        self.assertEqual(format_ist_clock("2026-07-11T21:00"), "9pm IST")
        self.assertEqual(format_ist_clock(None), "N/A")

    def test_observed_at_in_weather_report_is_ist(self) -> None:
        report = build_weather_report(DEFAULT_CITIES, get_digest_timezone())
        self.assertIn("IST", report.generated_at)
        for city in report.cities:
            if city.error or not city.current:
                continue
            shown = format_ist_clock(city.current.observed_at)
            self.assertRegex(
                shown,
                r"^\d{1,2}(:\d{2})?(am|pm) IST$",
                f"{city.city_name} observed_at should look like '9am IST', got {shown!r}",
            )


class JamesClearRotationTest(unittest.TestCase):
    """Shows how unused-issue rotation works before check-in."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "james_clear_quotes.json"
        self.db_path.write_text(
            json.dumps(_build_fixture_db(), indent=2) + "\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_prefers_newest_unused_issue(self) -> None:
        first = pick_next_321_issue(self.db_path, mark_used=False)
        self.assertIsNotNone(first)
        assert first is not None
        self.assertIn("Alpha", first.email_subject)
        self.assertTrue(first.message_id.startswith("http"))
        print(f"\n  newest unused → {first.email_subject}")

    def test_consecutive_picks_are_different_after_marking_used(self) -> None:
        first = pick_next_321_issue(self.db_path, mark_used=True)
        second = pick_next_321_issue(self.db_path, mark_used=True)
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        assert first is not None and second is not None

        self.assertIn("Alpha", first.email_subject)
        self.assertIn("Beta", second.email_subject)
        self.assertNotEqual(
            _issue_identity_key(first.email_date, first.email_subject),
            _issue_identity_key(second.email_date, second.email_subject),
        )

        used_keys = _used_issue_keys(self.db_path)
        self.assertIn(
            _issue_identity_key(first.email_date, first.email_subject),
            used_keys,
        )
        self.assertIn(
            _issue_identity_key(second.email_date, second.email_subject),
            used_keys,
        )
        print(f"\n  day1 → {first.email_subject}")
        print(f"  day2 → {second.email_subject}")

    def test_email_message_id_marks_web_copy_as_used(self) -> None:
        """Regression: ConvertKit IDs must block the matching website issue."""
        email_id = "<alpha-issue@convertkit-mail4.com>"
        mark_issue_used_in_digest(email_id, self.db_path)

        used_ids = get_used_digest_message_ids(self.db_path)
        self.assertIn(email_id, used_ids)
        self.assertIn("https://jamesclear.com/3-2-1/july-2-2026", used_ids)

        pick = pick_next_321_issue(self.db_path, mark_used=False)
        self.assertIsNotNone(pick)
        assert pick is not None
        self.assertIn("Beta", pick.email_subject)
        print(f"\n  after email-id used → next is {pick.email_subject}")

    def test_rotation_resets_after_all_issues_used(self) -> None:
        pick_next_321_issue(self.db_path, mark_used=True)
        pick_next_321_issue(self.db_path, mark_used=True)
        # Both issues used → next pick resets and returns newest again.
        again = pick_next_321_issue(self.db_path, mark_used=False)
        self.assertIsNotNone(again)
        assert again is not None
        self.assertIn("Alpha", again.email_subject)
        print(f"\n  after full rotation reset → {again.email_subject}")

    def test_picked_issue_has_three_ideas_and_question(self) -> None:
        issue = pick_next_321_issue(self.db_path, mark_used=False)
        self.assertIsNotNone(issue)
        assert issue is not None
        self.assertEqual(len(issue.ideas), 3)
        self.assertIsNotNone(issue.question)


class LiveDigestEmailTest(unittest.TestCase):
    """Sends one real digest so you can confirm mail arrives before check-in."""

    def setUp(self) -> None:
        if not should_send_live_email():
            self.skipTest(
                "Set SEND_LIVE_EMAIL=1 or pass --live to send a real email"
            )

    def test_send_live_digest_email(self) -> None:
        issues = list_321_issues()
        self.assertTrue(
            issues,
            "No James Clear issues in DB. Run: "
            "python sync_james_clear_quotes.py --source web --limit 5",
        )

        used_before = _used_issue_keys()
        inspiration = fetch_digest_inspiration(mark_used=True)
        self.assertIsNotNone(inspiration)
        assert inspiration is not None
        self.assertTrue(
            inspiration.ideas or inspiration.question,
            "Picked issue had no ideas/question",
        )

        report = build_weather_report(DEFAULT_CITIES, get_digest_timezone())
        self.assertFalse(report.all_failed, "Weather fetch failed; email not sent")

        result = send_weather_email(report, inspiration=inspiration)
        subject = build_email_subject(report)
        preview = format_report_text(report, inspiration).splitlines()[:12]
        used_after = _used_issue_keys()

        print("\n=== LIVE DIGEST SENT ===")
        print(f"To:      {get_to_email()}")
        print(f"Subject: {subject}")
        print(f"3-2-1:   {inspiration.subject}")
        print(f"Ideas:   {len(inspiration.ideas)}")
        print(f"Result:  {result}")
        print(f"Used issues before → after: {len(used_before)} → {len(used_after)}")
        print("--- preview ---")
        print("\n".join(preview))
        print("========================\n")

        self.assertIn("Email sent", result)
        self.assertGreaterEqual(
            len(used_after),
            len(used_before),
            "Expected used-issue tracking to update after send",
        )
        # The picked subject should now be considered used.
        matched = [
            i
            for i in issues
            if i.email_subject == inspiration.subject
            or i.message_id == inspiration.message_id
        ]
        self.assertTrue(matched)
        key = _issue_identity_key(matched[0].email_date, matched[0].email_subject)
        self.assertIn(key, used_after)


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    live = "--live" in argv
    if live:
        argv.remove("--live")
        os.environ["SEND_LIVE_EMAIL"] = "1"
        print("Running unit tests + LIVE email send...")
    else:
        print("Running unit tests only (no email). Pass --live to send one digest.")

    # Avoid unittest interpreting our flags.
    unittest_argv = [sys.argv[0], *argv]
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not live:
        print(
            "\nTip: run with --live to send one real digest to "
            f"{get_to_email()} before check-in."
        )
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
