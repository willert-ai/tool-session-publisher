#!/usr/bin/env python3
"""
save.py — write an approved post to <notes>/posts/x/.

The notes directory is resolved from the `SESSION_PUBLISHER_NOTES_DIR`
environment variable; falls back to `~/personal-notes` when unset.

Output filename: YYYY-MM-DD_post-NNN.md (NNN = next free index for the day).
Frontmatter follows SPEC §4 Stage 6.

Usage:
    python3 save.py <session_source> --body "<text>"
    python3 save.py <session_source> --body-file <path>
    python3 save.py <session_source> --body-stdin   # body read from stdin

Exactly one of --body, --body-file, --body-stdin is required.

The <session_source> key is the canonical SESSION_INDEX row identifier:
"YYYY-MM-DD - <title>" — no .md suffix, no SESSION_ prefix. select.py and
save.py MUST agree on this format for anti-duplicate to work (SPEC §6.h).

Stdout: JSON {"path": "...", "post_number": N, "status": "drafted"}.

Smoke test:
    python3 save.py "2026-05-12 - my session title" --body "test body" --today 2026-05-12
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

NOTES_BASE = Path(
    os.environ.get("SESSION_PUBLISHER_NOTES_DIR", str(Path.home() / "personal-notes"))
)
POSTS_X_DIR = NOTES_BASE / "posts" / "x"
TZ = ZoneInfo(os.environ.get("SESSION_PUBLISHER_TZ", "UTC"))
MAX_POST_LEN = 280  # SPEC §6.k


def next_post_number(day: date) -> int:
    """Return the next free post number for `day` based on existing files."""
    prefix = f"{day.isoformat()}_post-"
    existing = sorted(POSTS_X_DIR.glob(f"{prefix}*.md"))
    if not existing:
        return 1
    last = existing[-1].stem  # e.g. 2026-05-12_post-003
    try:
        return int(last.rsplit("-", 1)[1]) + 1
    except (IndexError, ValueError):
        return len(existing) + 1


def build_frontmatter(session_source: str, created_at: datetime) -> str:
    """Return the frontmatter block (between two `---` lines, inclusive)."""
    return (
        "---\n"
        f"created_at: {created_at.isoformat(timespec='seconds')}\n"
        f"session_source: {session_source}\n"
        "status: drafted\n"
        "x_url:\n"
        "reactions:\n"
        "  - \n"
        "notes:\n"
        "---\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "session_source",
        help="Session_source key — 'YYYY-MM-DD - <title>' (no .md suffix)",
    )
    parser.add_argument(
        "--body",
        type=str,
        default=None,
        help="Post body as a string (≤280 chars)",
    )
    parser.add_argument(
        "--body-file",
        type=Path,
        default=None,
        help="Read post body from this file",
    )
    parser.add_argument(
        "--body-stdin",
        action="store_true",
        help="Read post body from stdin",
    )
    parser.add_argument(
        "--today",
        type=str,
        default=None,
        help="Override today's date (YYYY-MM-DD); for smoke tests. "
        "When set, created_at uses noon of that date.",
    )
    parser.add_argument(
        "--allow-overlength",
        action="store_true",
        help="Skip the 280-character check (use only when intentional)",
    )
    args = parser.parse_args()

    # resolve body — explicit mutual-exclusion check (positionals cannot
    # be combined with argparse.mutually_exclusive_group cleanly).
    body_sources = sum(
        1 for v in (args.body, args.body_file, args.body_stdin) if v
    )
    if body_sources == 0:
        print(json.dumps({"error": "must provide --body, --body-file, or --body-stdin"}))
        return 1
    if body_sources > 1:
        print(json.dumps({"error": "provide only ONE of --body, --body-file, --body-stdin"}))
        return 1

    if args.body_file is not None:
        body = args.body_file.read_text()
    elif args.body_stdin:
        body = sys.stdin.read()
    else:
        body = args.body
    body = (body or "").rstrip("\n")

    if not body.strip():
        print(json.dumps({"error": "post body is empty"}))
        return 1

    if not args.allow_overlength and len(body) > MAX_POST_LEN:
        print(
            json.dumps(
                {
                    "error": "post exceeds 280 chars",
                    "length": len(body),
                    "max": MAX_POST_LEN,
                    "hint": "rewrite or pass --allow-overlength",
                }
            )
        )
        return 1

    # ensure directory (no-op safety net per E1 mitigation)
    POSTS_X_DIR.mkdir(parents=True, exist_ok=True)

    if args.today:
        # Test override — use a fixed noon time to make test output
        # deterministic and to avoid mixing today's clock with another date.
        override_date = datetime.strptime(args.today, "%Y-%m-%d").date()
        now = datetime.combine(
            override_date,
            datetime.min.time().replace(hour=12),
            tzinfo=TZ,
        )
    else:
        now = datetime.now(TZ)
    day = now.date()

    post_number = next_post_number(day)
    filename = f"{day.isoformat()}_post-{post_number:03d}.md"
    out_path = POSTS_X_DIR / filename

    content = build_frontmatter(args.session_source, now) + "\n" + body + "\n"
    out_path.write_text(content)

    print(
        json.dumps(
            {
                "path": str(out_path),
                "post_number": post_number,
                "filename": filename,
                "status": "drafted",
                "body_length": len(body),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
