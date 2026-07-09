"""CLI: sync James Clear 3-2-1 ideas, quotes, and questions into the local database."""

from __future__ import annotations

import argparse
import json
import sys

from james_clear import sync_james_clear_quotes, watch_james_clear_inbox


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Sync James Clear 3-2-1 issues into data/james_clear_quotes.json "
            "(default source: https://jamesclear.com/3-2-1)."
        )
    )
    parser.add_argument(
        "--source",
        choices=("web", "email", "auto"),
        default="web",
        help="Where to pull issues from (default: web)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only scan the newest N issues (default: all)",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Rescan all matching issues and refresh stored entries",
    )
    parser.add_argument(
        "--new-only",
        action="store_true",
        help="Only fetch issues not already in the database",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Keep running and poll for new 3-2-1 issues",
    )
    parser.add_argument(
        "--poll-seconds",
        type=int,
        default=300,
        help="Watch poll interval in seconds (default: 300)",
    )
    args = parser.parse_args()

    if args.watch:
        try:
            summary = sync_james_clear_quotes(only_new=True, source=args.source)
            print(json.dumps(summary, indent=2))
        except Exception as exc:
            print(f"Initial sync failed: {exc}", file=sys.stderr)
        watch_james_clear_inbox(poll_seconds=args.poll_seconds)
        return 0

    try:
        summary = sync_james_clear_quotes(
            limit=args.limit,
            only_new=args.new_only,
            full=args.full or (args.limit is None and not args.new_only),
            source=args.source,
        )
    except Exception as exc:
        print(f"Sync failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
