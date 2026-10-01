#!/usr/bin/env python3
"""
select.py — pick candidate sessions for posting.

Asks the session-close tool for the records (`session_records.py list` — the
generated SESSION_INDEX.md is retired, #129), returns the last N days of sessions
(default 7) that are NOT already referenced by any post in
<notes>/posts/x/*.md (anti-duplicate by `session_source` frontmatter).
Optional focus.yaml filter at repo root.

The notes directory is resolved from the `SESSION_PUBLISHER_NOTES_DIR`
environment variable; falls back to `~/personal-notes` when unset.

SPEC §6.h (anti-duplicate), §6.i (focus filter), §6.j (7-day scope).
The records: one JSON object per record from `session_records.py list` — date,
title, type, outcome and tags each the retired index's cell byte for byte; the
same loader as mine.py.
SESSION_RECORDS_TOOL overrides the tool's path (default
~/.config/agent-rules/procedures/session-close/session_records.py).

Stdout: JSON list of session candidates, oldest first.
Each item: {"date": "YYYY-MM-DD", "title": "...", "tags": "...",
            "session_source": "<date> - <title>"}

Smoke tests:
    python3 select.py --days 7
    python3 select.py --days 7 --today 2026-05-12
    python3 select.py --days 14 --no-filter --include-posted
"""

from __future__ import annotations

import os
import sys

# Same fix as mine.py, same reason: running this file puts its own directory at
# sys.path[0], and `subprocess` pulls in `selectors` -> `import select`, which
# would resolve to this very file instead of the stdlib module.
_HELPERS_DIR = os.path.dirname(os.path.realpath(__file__))
sys.path[:] = [p for p in sys.path if os.path.realpath(p or os.getcwd()) != _HELPERS_DIR]

import argparse  # noqa: E402
import json  # noqa: E402
import subprocess  # noqa: E402
from datetime import date, datetime, timedelta  # noqa: E402
from pathlib import Path  # noqa: E402

NOTES_BASE = Path(
    os.environ.get("SESSION_PUBLISHER_NOTES_DIR", str(Path.home() / "personal-notes"))
)
RECORDS_TOOL = Path(
    os.environ.get(
        "SESSION_RECORDS_TOOL",
        str(Path.home() / ".config/agent-rules/procedures/session-close/session_records.py"),
    )
)
RECORDS_TIMEOUT = 60
POSTS_X_DIR = NOTES_BASE / "posts" / "x"

# Repo root = parent of skill/ dir, which is parent of this file's dir.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FOCUS_YAML = REPO_ROOT / "focus.yaml"

# github-ops type prefixes stripped before substring match (SPEC §6.i).
TYPE_PREFIXES = ("tool-", "app-", "scripts-", "ref-")


class RecordsError(Exception):
    pass


def load_sessions(fero_log: Path, since: str) -> list[dict]:
    """The session records dated `since` or later, oldest first, as session dicts
    (date, title, type, outcome, insight, ledger, asana, tags) — same loader as
    mine.py. Insight and Asana were always '-' in the generated index and stay
    '-'. A missing or failing tool raises RecordsError."""
    if not RECORDS_TOOL.is_file():
        raise RecordsError(f"session records tool not found at {RECORDS_TOOL}")
    if not (fero_log / "sessions").is_dir():
        raise RecordsError(f"no sessions/ folder in {fero_log}")
    command = [sys.executable, str(RECORDS_TOOL), "list", "--fero-log", str(fero_log), "--since", since]
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=RECORDS_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RecordsError(str(exc)) from None
    if done.returncode != 0:
        raise RecordsError(done.stderr.strip()[-300:] or f"exit {done.returncode}")
    sessions = []
    for line in done.stdout.splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            sessions.append(
                {
                    "date": record["date"],
                    "title": record["title"],
                    "type": record["type"],
                    "outcome": record["outcome"],
                    "insight": "-",
                    "ledger": record["ledger"],
                    "asana": "-",
                    "tags": record["tags"],
                }
            )
        except (ValueError, KeyError, TypeError) as exc:
            raise RecordsError(f"unexpected record line: {exc}") from None
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

    Format: "YYYY-MM-DD - <title from session_records.py list>"
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

    today = (
        datetime.strptime(args.today, "%Y-%m-%d").date()
        if args.today
        else date.today()
    )
    cutoff = today - timedelta(days=args.days)

    try:
        sessions = load_sessions(NOTES_BASE, cutoff.isoformat())
    except RecordsError as exc:
        print(json.dumps({"error": "session records unavailable", "detail": str(exc), "tool": str(RECORDS_TOOL)}))
        return 1

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
