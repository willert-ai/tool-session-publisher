#!/usr/bin/env python3
"""
select.py — pick candidate sessions for posting.

Reads <notes>/SESSION_INDEX.md, returns the last N days of sessions
(default 7) that are NOT already referenced by any post in
<notes>/posts/x/*.md (anti-duplicate by `session_source` frontmatter).
Optional focus.yaml filter at repo root.

The notes directory is resolved from the `SESSION_PUBLISHER_NOTES_DIR`
environment variable; falls back to `~/personal-notes` when unset.

SPEC §6.h (anti-duplicate), §6.i (focus filter), §6.j (7-day scope).
SESSION_INDEX schema: 8 positional columns, no header.
Single Path.read_text() call (E3 mitigation).

Stdout: JSON list of session candidates, oldest first.
Each item: {"date": "YYYY-MM-DD", "title": "...", "tags": "...",
            "session_source": "<date> - <title>"}

Smoke tests:
    python3 select.py --days 7
    python3 select.py --days 7 --today 2026-05-12
    python3 select.py --days 14 --no-filter --include-posted
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
SESSION_INDEX = NOTES_BASE / "SESSION_INDEX.md"
POSTS_X_DIR = NOTES_BASE / "posts" / "x"

# Repo root = parent of skill/ dir, which is parent of this file's dir.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FOCUS_YAML = REPO_ROOT / "focus.yaml"

# Match a SESSION row: pipe + space + ISO date + space + pipe.
ROW_PATTERN = re.compile(r"^\| \d{4}-\d{2}-\d{2} \|")

# github-ops type prefixes stripped before substring match (SPEC §6.i).
TYPE_PREFIXES = ("tool-", "app-", "scripts-", "ref-")


def parse_session_index(text: str) -> list[dict]:
    """Parse SESSION_INDEX.md into a list of session dicts.

    Returns oldest-first. Each dict has: date, title, type, outcome,
    insight, ledger, asana, tags, filename (reconstructed from date+title).
    """
    sessions = []
    for line in text.splitlines():
        if not ROW_PATTERN.match(line):
            continue
        parts = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(parts) < 8:
            # malformed row — skip silently
            continue
        date_str, title, type_, outcome, insight, ledger, asana, tags = parts[:8]
        # reconstructed filename pattern used by wrap-up skill
        # (SESSION files follow `YYYY-MM-DD - SESSION_<title>.md`).
        # We do not require the filename to exist on disk; it is the
        # canonical key used in `session_source:` frontmatter of posts.
        sessions.append(
            {
                "date": date_str,
                "title": title,
                "type": type_,
                "outcome": outcome,
                "insight": insight,
                "ledger": ledger,
                "asana": asana,
                "tags": tags,
            }
        )
    return sessions


def load_focus_tokens() -> list[str]:
    """Read focus.yaml if present and return lowercase tokens.

    SPEC §6.i — case-insensitive substring match against title + tags,
    with github-ops type prefixes stripped.

    Expected format (flat list, no nesting needed):

        - my-side-project
        - tool-mycli
        - weekly-newsletter

    Lines NOT starting with `- ` are silently ignored. Top-level keys
    like `projects:` are tolerated but have no effect.

    `tool-`, `app-`, `scripts-`, and `ref-` prefixes are stripped before
    matching, so `tool-mycli` also matches sessions tagged just `mycli`.
    No PyYAML dependency.
    """
    if not FOCUS_YAML.exists():
        return []
    tokens = []
    for raw in FOCUS_YAML.read_text().splitlines():
        line = raw.strip()
        if line.startswith("- "):
            token = line[2:].strip().strip("\"'").lower()
            for prefix in TYPE_PREFIXES:
                if token.startswith(prefix):
                    token = token[len(prefix) :]
                    break
            if token:
                tokens.append(token)
    return tokens


def matches_focus(session: dict, tokens: list[str]) -> bool:
    """Case-insensitive substring match against title + tags."""
    if not tokens:
        return True
    haystack = f"{session['title']} {session['tags']}".lower()
    return any(token in haystack for token in tokens)


def already_posted_sources() -> set[str]:
    """Read every *.md under <notes>/posts/x/ and collect the
    `session_source:` frontmatter values that have already been handled.
    """
    sources: set[str] = set()
    if not POSTS_X_DIR.exists():
        return sources
    for post in POSTS_X_DIR.glob("*.md"):
        try:
            body = post.read_text()
        except OSError:
            continue
        # crude frontmatter scan — sufficient for v0
        for line in body.splitlines():
            if line.startswith("session_source:"):
                value = line.split(":", 1)[1].strip()
                if value:
                    sources.add(value)
                break
    return sources


def session_source_key(session: dict) -> str:
    """Canonical `session_source` identifier used in post frontmatter.

    Format: "YYYY-MM-DD - <title from SESSION_INDEX>"
    NO `.md` suffix. NO `SESSION_` prefix.

    This is the contract between select.py (which produces the key) and
    save.py (which writes it into post frontmatter). Anti-duplicate
    matches exact string equality on this key (SPEC §6.h). If you
    change the format here, change save.py CLI docstring too.
    """
    return f"{session['date']} - {session['title']}"


# Back-compat alias — older code referenced session_filename.
session_filename = session_source_key


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Number of past days to consider (default 7)",
    )
    parser.add_argument(
        "--today",
        type=str,
        default=None,
        help="Override today's date (YYYY-MM-DD); useful for smoke tests",
    )
    parser.add_argument(
        "--no-filter",
        action="store_true",
        help="Ignore focus.yaml even if present",
    )
    parser.add_argument(
        "--include-posted",
        action="store_true",
        help="Do not exclude sessions already referenced in posts/x/",
    )
    args = parser.parse_args()

    if not SESSION_INDEX.exists():
        print(
            json.dumps(
                {
                    "error": "SESSION_INDEX.md not found",
                    "path": str(SESSION_INDEX),
                }
            )
        )
        return 1

    today = (
        datetime.strptime(args.today, "%Y-%m-%d").date()
        if args.today
        else date.today()
    )
    cutoff = today - timedelta(days=args.days)

    text = SESSION_INDEX.read_text()  # single read — E3 mitigation
    sessions = parse_session_index(text)

    # window filter
    in_window = []
    for s in sessions:
        try:
            d = datetime.strptime(s["date"], "%Y-%m-%d").date()
        except ValueError:
            continue
        if cutoff <= d <= today:
            in_window.append(s)

    # focus filter
    tokens = [] if args.no_filter else load_focus_tokens()
    focused = [s for s in in_window if matches_focus(s, tokens)]
    # focus fallback (PT4): if filter yields empty set, use unfiltered window
    if tokens and not focused:
        focused = in_window
        focus_fallback = True
    else:
        focus_fallback = False

    # anti-duplicate filter
    posted = set() if args.include_posted else already_posted_sources()
    selected = [s for s in focused if session_source_key(s) not in posted]

    output = {
        "today": today.isoformat(),
        "window_days": args.days,
        "cutoff": cutoff.isoformat(),
        "focus_tokens": tokens,
        "focus_fallback_applied": focus_fallback,
        "already_posted_count": len(posted),
        "candidates": [
            {
                "date": s["date"],
                "title": s["title"],
                "tags": s["tags"],
                "session_source": session_source_key(s),
            }
            for s in selected
        ],
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
