"""Background watcher for new James Clear 3-2-1 emails."""

from __future__ import annotations

import argparse

from james_clear import sync_james_clear_quotes, watch_james_clear_inbox


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Watch Gmail IMAP and store new 3-2-1 ideas/quotes/questions"
    )
    parser.add_argument(
        "--poll-seconds",
        type=int,
        default=300,
        help="How often to check for new mail (default: 300)",
    )
    parser.add_argument(
        "--full-first",
        action="store_true",
        help="Do a full mailbox sync before watching",
    )
    args = parser.parse_args()

    if args.full_first:
        print(sync_james_clear_quotes(full=True))
    else:
        print(sync_james_clear_quotes(only_new=True))

    watch_james_clear_inbox(poll_seconds=args.poll_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
