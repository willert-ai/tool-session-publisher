#!/usr/bin/env python3
"""
thread.py — narrative-thread + reaction recap from <notes>/posts/x/.

The notes directory is resolved from the `SESSION_PUBLISHER_NOTES_DIR`
environment variable; falls back to `~/personal-notes` when unset.

Lists every post file modified within the last N days (default 7), parses
its frontmatter (created_at, session_source, status, x_url, reactions,
notes), and returns the result as JSON for SKILL.md Stage 2 to render.

Reaction recap: limited to the most-recent 3 posts; only included when at
least one of those posts has a non-empty `reactions:` list (SPEC §6.q).

Stdout: JSON object with `posts` (oldest-first), `reaction_recap`
(most-recent 3 posts with annotations, or empty list when no annotations
have been entered yet — Stage 2 prints the "no annotations yet" note).

Smoke tests:
    python3 thread.py --days 7
    python3 thread.py --days 14 --today 2026-05-12
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

NOTES_BASE = Path(
    os.environ.get("SESSION_PUBLISHER_NOTES_DIR", str(Path.home() / "personal-notes"))
)
POSTS_X_DIR = NOTES_BASE / "posts" / "x"

FILENAME_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2})_post-(\d{3})\.md$")
FRONTMATTER_DELIM = "---"


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Return (frontmatter_dict, body). Minimal YAML — no PyYAML dep.

    Handles:
        - scalar `key: value`
        - list `key:` followed by `  - item` lines

    Does NOT handle (acceptable for v0):
        - quoted strings with embedded colons → first colon wins; downstream
          consumers see a truncated value
        - multi-line block scalars (`>`, `|`)
        - nested mappings

    The post frontmatter is operator-authored from a known template
    (save.py output), so the constraints above never surface in practice.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != FRONTMATTER_DELIM:
        return {}, text
    # find closing delimiter
    try:
        end_idx = next(
            i for i, ln in enumerate(lines[1:], start=1) if ln.strip() == FRONTMATTER_DELIM
        )
    except StopIteration:
        return {}, text

    fm: dict = {}
    current_list_key: str | None = None
    for raw in lines[1:end_idx]:
        line = raw.rstrip()
        # list item under current_list_key
        if current_list_key and line.lstrip().startswith("- "):
            item = line.lstrip()[2:].strip()
            if item:
                fm[current_list_key].append(item)
            continue
        # new key
        if ":" in line and not line.startswith(" "):
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            if value == "":
                # could be a list — initialise; if no list items follow,
                # caller sees an empty list which still serializes cleanly
                fm[key] = []
                current_list_key = key
            else:
                fm[key] = value
                current_list_key = None
    body = "\n".join(lines[end_idx + 1 :]).lstrip("\n")
    return fm, body


def load_posts(within_days: int, today: date) -> list[dict]:
    """Return posts whose filename-date is within the window, oldest-first."""
    if not POSTS_X_DIR.exists():
        return []
    cutoff = today - timedelta(days=within_days)
    posts = []
    for path in sorted(POSTS_X_DIR.glob("*.md")):
        m = FILENAME_PATTERN.match(path.name)
        if not m:
            continue
        try:
            d = datetime.strptime(m.group(1), "%Y-%m-%d").date()
        except ValueError:
            continue
        if not (cutoff <= d <= today):
            continue
        try:
            raw = path.read_text()
        except OSError:
            continue
        fm, body = parse_frontmatter(raw)
        posts.append(
            {
                "filename": path.name,
                "date": m.group(1),
                "post_number": int(m.group(2)),
                "created_at": fm.get("created_at", ""),
                "session_source": fm.get("session_source", ""),
                "status": fm.get("status", ""),
                "x_url": fm.get("x_url", "") or "",
                "reactions": fm.get("reactions", []) or [],
                "notes": fm.get("notes", "") or "",
                "body_excerpt": (body[:160] + "...") if len(body) > 160 else body,
            }
        )
    return posts


def build_reaction_recap(posts: list[dict]) -> list[dict]:
    """Most-recent 3 posts that have non-empty `reactions:` entries."""
    most_recent_3 = sorted(posts, key=lambda p: (p["date"], p["post_number"]))[-3:]
    return [
        {
            "date": p["date"],
            "filename": p["filename"],
            "body_excerpt": p["body_excerpt"],
            "reactions": p["reactions"],
        }
        for p in most_recent_3
        if p["reactions"]
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Window size in days (default 7)",
    )
    parser.add_argument(
        "--today",
        type=str,
        default=None,
        help="Override today's date (YYYY-MM-DD); for smoke tests",
    )
    args = parser.parse_args()

    today = (
        datetime.strptime(args.today, "%Y-%m-%d").date()
        if args.today
        else date.today()
    )

    posts = load_posts(args.days, today)
    recap = build_reaction_recap(posts)

    output = {
        "today": today.isoformat(),
        "window_days": args.days,
        "posts_count": len(posts),
        "posts": posts,
        "reaction_recap": recap,
        "reactions_annotated": bool(recap),
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
