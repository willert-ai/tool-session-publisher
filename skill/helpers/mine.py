#!/usr/bin/env python3
"""
mine.py — the ambient miner: scan SESSION_INDEX + git logs, emit scored seeds.

Reads <notes>/SESSION_INDEX.md, windows it to `--days` (inclusive cutoff, same
arithmetic as select.py's own `--days` — N+1 calendar days including today),
drops anything already handled (a post already saved for it, or any ledger
event ever recorded for it), scores what survives, and prints the winners as
seed JSON draft.py can read straight off stdin:

    python3 mine.py --days 3 | python3 draft.py --seeds-stdin

Note on that pipe: draft.py's normalise_seeds treats an *empty* seed list as
a hard failure (`input:no_seeds`, exit 1) — a quiet day where every mined
candidate is already posted or ledgered is a normal outcome here (mine.py
still exits 0 with `"seeds": []`), but the naive pipe surfaces it downstream
as draft.py's failure exit. A caller composing the two (C6's run.sh) should
check mine.py's own JSON rather than rely on draft.py's exit code to tell
"nothing to draft" apart from "the miner is broken".

Dedup is the anti-re-emission contract (C3's blocker shape, repeated here):
a seed that already produced a queue entry — queued, approved, posted,
killed or expired — must never be re-emitted, or a killed draft the operator
already rejected comes back next tick. That means `mine.py` reads the ledger
with `strict=True` and **fails closed**: an unreadable ledger is not "treat
everything as fresh", it is "emit nothing this tick" (exit 1). One dedup gap
this cannot close: a seed draft.py *rejects* (an anti-voice/anti-leak gate,
or the model declining) never reaches `queue.py add`, so no ledger event is
ever written for it — the ledger only records what got as far as a queue
entry. Such a seed is indistinguishable from a never-tried one and will be
re-mined every tick until it ages out of the window. Closing that gap needs
a ledger event for rejections too, which is a `draft.py`/`queue.py` change,
out of scope here.

`text` — the only place draft.py's number gate lets numbers come from — is
built from two sources, matching the component diagram: the SESSION_INDEX
row itself (outcome/insight are already number-dense in this operator's
index) and, best-effort, `git log` subjects from a same-day match in a
locally scanned repo. A miss on the git side just means a plainer `text`;
it is enrichment, not the contract, and never turns into a failure.

SESSION_INDEX schema: 8 positional columns, no header — same parse contract
`select.py` documents. Duplicated here rather than imported: `select.py`
shadows the stdlib `select` module (see AGENTS.md), and this file shells out
to `git`, which needs `select` via `subprocess` -> `selectors`.

Environment:
    SESSION_PUBLISHER_NOTES_DIR   notes root (default ~/personal-notes)
    SESSION_PUBLISHER_TZ          ledger timestamp zone (read by queue.py)
    X_COMMS_REPO_DIRS             colon-separated parent dirs scanned for
                                   git-log enrichment (default
                                   ~/tools:~/apps:~/scripts:~/reference)

Smoke tests:
    python3 mine.py --days 14
    python3 mine.py --days 3 --today 2026-08-25

`--index` and `--queue-dir` isolate SESSION_INDEX and the ledger for testing,
but posts/ dedup always reads the real $NOTES_DIR/posts/x/ — there is no
separate override for it. A fully isolated test run needs
SESSION_PUBLISHER_NOTES_DIR pointed at a scratch dir too:

    SESSION_PUBLISHER_NOTES_DIR=/tmp/notes \\
        python3 mine.py --days 14 --index /tmp/SESSION_INDEX.md --queue-dir /tmp/q
"""

from __future__ import annotations

import os
import sys

# Same fix as draft.py, same reason: running this file puts its own directory
# at sys.path[0], and `git log` enrichment shells out via `subprocess`, which
# pulls in `selectors` -> `import select` -> resolves to the sibling
# select.py instead of the stdlib module. Drop our own directory first.
_HELPERS_DIR = os.path.dirname(os.path.realpath(__file__))
sys.path[:] = [p for p in sys.path if os.path.realpath(p or os.getcwd()) != _HELPERS_DIR]

import argparse  # noqa: E402
import importlib.util  # noqa: E402
import json  # noqa: E402
import re  # noqa: E402
import subprocess  # noqa: E402
from datetime import datetime, timedelta  # noqa: E402
from pathlib import Path  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

HELPERS_DIR = Path(_HELPERS_DIR)

NOTES_BASE = Path(
    os.environ.get("SESSION_PUBLISHER_NOTES_DIR", str(Path.home() / "personal-notes"))
)
SESSION_INDEX = NOTES_BASE / "SESSION_INDEX.md"
POSTS_X_DIR = NOTES_BASE / "posts" / "x"
# Same variable queue.py reads for ledger timestamps and git_log_subjects reads
# for day-boundary enrichment — "today" has to mean the same day everywhere in
# this pipeline, not whatever zone the host happens to be set to.
TZ = ZoneInfo(os.environ.get("SESSION_PUBLISHER_TZ", "UTC"))

DEFAULT_REPO_PARENTS = ("~/tools", "~/apps", "~/scripts", "~/reference")
GIT_TIMEOUT = 4
MAX_GIT_SUBJECTS = 5
DEFAULT_MAX_SEEDS = 12

# Match a SESSION row: pipe + space + ISO date + space + pipe — same contract
# select.py parses against (session_source_key format: "YYYY-MM-DD - <title>").
ROW_PATTERN = re.compile(r"^\| \d{4}-\d{2}-\d{2} \|")


class EngineError(Exception):
    """A run-level failure: nothing was mined, so nothing should be printed as ok."""

    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.message = message


# --- queue module (ledger read only) ----------------------------------------


_QUEUE_MODULE = None


def queue_module():
    """Load (once) the sibling queue.py by explicit path — see draft.py for why
    a bare `import queue` cannot be trusted here."""
    global _QUEUE_MODULE
    if _QUEUE_MODULE is None:
        spec = importlib.util.spec_from_file_location("x_comms_queue", HELPERS_DIR / "queue.py")
        if spec is None or spec.loader is None:  # pragma: no cover — packaging accident
            raise EngineError("engine:queue_missing", "cannot load queue.py")
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as exc:  # queue.py mid-edit, syntax error, etc. — fail closed, not a traceback
            raise EngineError("engine:queue_load_failed", str(exc)) from exc
        _QUEUE_MODULE = module
    return _QUEUE_MODULE


# --- SESSION_INDEX parsing ---------------------------------------------------


def parse_session_index(text: str) -> list[dict]:
    """Parse SESSION_INDEX.md into session dicts, oldest-first as written.

    8 positional columns: date, title, type, outcome, insight, ledger, asana,
    tags. Malformed rows (fewer than 8 cells) are skipped silently — same
    behaviour as select.py, so the two tools never disagree about what a row
    is.
    """
    sessions = []
    for line in text.splitlines():
        if not ROW_PATTERN.match(line):
            continue
        parts = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(parts) < 8:
            continue
        date_str, title, type_, outcome, insight, ledger, asana, tags = parts[:8]
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


def session_source_key(session: dict) -> str:
    """`seed_ref` / `session_source` identifier — MUST match select.py's and
    save.py's format exactly, or posts/ dedup and future save.py writes
    silently stop agreeing on what a session is."""
    return f"{session['date']} - {session['title']}"


def already_posted_sources() -> set[str]:
    """`session_source:` frontmatter values from every post already saved
    under <notes>/posts/x/ — same scan select.py runs, duplicated for the
    same reason the SESSION_INDEX parser is duplicated."""
    sources: set[str] = set()
    if not POSTS_X_DIR.exists():
        return sources
    for post in POSTS_X_DIR.glob("*.md"):
        try:
            body = post.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            # One unreadable/mis-encoded stray file in posts/x/ must not crash
            # the whole miner — worst case that one post's dedup is missed.
            continue
        for line in body.splitlines():
            if line.startswith("session_source:"):
                value = line.split(":", 1)[1].strip()
                if value:
                    sources.add(value)
                break
    return sources


# --- git-log enrichment (best-effort; a miss never fails the tick) ----------


def build_repo_index(parents_env: str | None) -> dict[str, Path]:
    """Map lowercase repo dirname -> path, plus a tool-/app-/scripts-/ref-
    stripped alias where unambiguous.

    Full dirnames and stripped aliases are tracked separately so an alias
    collision (`tool-x` and `app-x` both stripping to "x") can only ever
    drop the ambiguous *alias* — it must never shadow a real repo that is
    literally named `x`, which is an exact, unambiguous match on its own.
    """
    parents = (parents_env or ":".join(DEFAULT_REPO_PARENTS)).split(":")
    by_name: dict[str, Path] = {}
    by_alias: dict[str, Path | None] = {}
    for raw in parents:
        raw = raw.strip()
        if not raw:
            continue
        parent = Path(raw).expanduser()
        if not parent.is_dir():
            continue
        try:
            children = list(parent.iterdir())
        except OSError:
            continue
        for child in children:
            if not child.is_dir() or not (child / ".git").exists():
                continue
            name = child.name.lower()
            by_name[name] = child
            for prefix in ("tool-", "app-", "scripts-", "ref-"):
                if name.startswith(prefix):
                    stripped = name[len(prefix) :]
                    if stripped in by_alias and by_alias[stripped] != child:
                        by_alias[stripped] = None
                    else:
                        by_alias.setdefault(stripped, child)
    index = {k: v for k, v in by_alias.items() if v is not None}
    index.update(by_name)  # an exact dirname always wins over a stripped alias
    return index


def match_repo(session: dict, repo_index: dict[str, Path]) -> Path | None:
    """Exact match only: a tag's whole slug against a repo dirname (or its
    tool-/app-/scripts-/ref- stripped form). Kebab-case project tags like
    `voice-discovery` or `x-comms-engine` are the identifier, and splitting
    them on `-` (as a generic word-tokenizer would) turns "voice-discovery"
    into "voice" + "discovery" — "voice" alone then substring-matches
    unrelated repos like `voice-capture-rag`, silently attributing another
    project's commits to this session. Whole-tag equality only."""
    if not repo_index:
        return None
    candidates = re.split(r"[,\s]+", session["tags"].strip().lower())
    for token in candidates:
        token = token.strip()
        if token and token != "-" and token in repo_index:
            return repo_index[token]
    return None


def git_log_subjects(repo: Path, day: str) -> list[str]:
    """Commit subjects from `repo` on `day`. Any failure (no git binary, not
    a repo anymore, timeout) returns [] — this is enrichment, not a gate.

    `--since`/`--until` are resolved by git in the process's `TZ`, not in
    SESSION_INDEX's own timezone — set `TZ` from `SESSION_PUBLISHER_TZ` (same
    variable queue.py reads for ledger timestamps) so a day boundary here
    means the same day it means everywhere else in this pipeline.
    """
    env = dict(os.environ)
    env["TZ"] = os.environ.get("SESSION_PUBLISHER_TZ", "UTC")
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "log",
                f"--since={day} 00:00:00",
                f"--until={day} 23:59:59",
                "--format=%s",
            ],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()][:MAX_GIT_SUBJECTS]


# --- scoring (explainable: every point traces to a named reason) -----------


def score_session(session: dict, git_hits: list[str]) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    outcome = session["outcome"]
    if outcome and outcome != "-":
        score += 2
        reasons.append("outcome:present(+2)")
        if re.search(r"\d", outcome):
            score += 2
            reasons.append("outcome:has_numbers(+2)")
        if len(outcome) >= 120:
            score += 1
            reasons.append("outcome:detailed(+1)")
    if session["insight"] and session["insight"] != "-":
        score += 1
        reasons.append("insight:present(+1)")
    tag_list = [t for t in re.split(r"[,\s]+", session["tags"]) if t and t != "-"]
    if len(tag_list) >= 3:
        score += 1
        reasons.append("tags:>=3(+1)")
    if "implementation" in session["type"].lower():
        score += 1
        reasons.append("type:implementation(+1)")
    if git_hits:
        score += 2
        reasons.append(f"git:{len(git_hits)}_commits(+2)")
    return score, reasons


def build_text(session: dict, git_hits: list[str]) -> str:
    parts = []
    if session["outcome"] and session["outcome"] != "-":
        parts.append(f"Outcome: {session['outcome']}")
    if session["insight"] and session["insight"] != "-":
        parts.append(f"Insight: {session['insight']}")
    if session["tags"] and session["tags"] != "-":
        parts.append(f"Tags: {session['tags']}")
    if git_hits:
        parts.append("Commits: " + "; ".join(git_hits))
    if not parts:
        parts.append(session["title"])
    return "\n".join(parts)


# --- the run ------------------------------------------------------------


def run(args) -> int:
    index_path = Path(args.index).expanduser() if args.index else SESSION_INDEX
    if not index_path.exists():
        raise EngineError("input:index_missing", f"SESSION_INDEX not found at {index_path}")
    try:
        text = index_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise EngineError("input:index_unreadable", str(exc)) from exc

    if args.max_seeds < 1:
        raise EngineError("input:max_seeds", "--max-seeds must be >= 1")
    try:
        today = datetime.strptime(args.today, "%Y-%m-%d").date() if args.today else datetime.now(TZ).date()
    except ValueError as exc:
        raise EngineError("input:today", f"--today is not a valid date: {exc}") from exc
    # Same cutoff arithmetic as select.py's `--days`: inclusive on both ends,
    # so `--days N` actually spans N+1 calendar days including today. Kept
    # identical on purpose — the two tools share the flag name and disagreeing
    # about what it means would be worse than either convention alone.
    window_start = today - timedelta(days=args.days)

    sessions = parse_session_index(text)
    in_window = [s for s in sessions if window_start.isoformat() <= s["date"] <= today.isoformat()]

    posted = already_posted_sources()

    queue_mod = queue_module()
    queue_dir = queue_mod.resolve_queue_dir(args.queue_dir)
    try:
        events, _torn = queue_mod.read_ledger(queue_dir, strict=True)
    except queue_mod.LedgerUnreadable as exc:
        # Fail closed: a partial ledger view is a guess about what was
        # already drafted/killed, and a guess here means re-emitting a
        # rejected seed. Emit nothing rather than emit on a guess.
        raise EngineError("input:ledger_unreadable", str(exc)) from None
    ledgered_keys = {event.get("seed_key") for event in events if event.get("seed_key")}

    repo_index = build_repo_index(os.environ.get("X_COMMS_REPO_DIRS"))

    report = {
        "status": "ok",
        "scanned": len(sessions),
        "in_window": len(in_window),
        "skipped_posted": 0,
        "skipped_ledgered": 0,
        "skipped_duplicate": 0,
        "seeds": [],
    }

    candidates = []
    git_cache: dict[tuple[Path, str], list[str]] = {}
    seen_refs: set[str] = set()
    for session in in_window:
        ref = session_source_key(session)
        if ref in posted:
            report["skipped_posted"] += 1
            continue
        key = queue_mod.seed_key_for(ref)
        if key in ledgered_keys:
            report["skipped_ledgered"] += 1
            continue
        if ref in seen_refs:
            # A duplicate SESSION_INDEX row (manual edit, merge artifact)
            # would otherwise emit two seeds sharing a seed_key — draft.py's
            # normalise_seeds rejects the *whole* run on that, dropping every
            # other legitimate seed this tick along with the duplicate.
            report["skipped_duplicate"] += 1
            continue
        seen_refs.add(ref)
        repo = match_repo(session, repo_index)
        git_hits = []
        if repo:
            # Several sessions on the same day commonly tag the same repo —
            # cache by (repo, day) so each distinct pair shells out once.
            cache_key = (repo, session["date"])
            if cache_key not in git_cache:
                git_cache[cache_key] = git_log_subjects(repo, session["date"])
            git_hits = git_cache[cache_key]
        score, reasons = score_session(session, git_hits)
        candidates.append(
            {
                "source": "miner",
                "seed_ref": ref,
                "seed_key": key,
                "text": build_text(session, git_hits),
                "score": score,
                "score_reasons": reasons,
            }
        )

    # Score desc primary, `seed_ref` (date-prefixed, so this is recency) desc
    # as the tiebreak — one composite key, no reliance on sort stability.
    candidates.sort(key=lambda c: (c["score"], c["seed_ref"]), reverse=True)

    report["seeds"] = candidates[: args.max_seeds]
    print(json.dumps(report, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--days", type=int, default=7, help="window size in days (default 7)")
    parser.add_argument("--today", help="override today's date (YYYY-MM-DD); test hook")
    parser.add_argument("--index", help="override the SESSION_INDEX.md path; test hook")
    parser.add_argument("--queue-dir", help="override the queue directory; test hook")
    parser.add_argument(
        "--max-seeds",
        type=int,
        default=DEFAULT_MAX_SEEDS,
        help=f"cap on emitted seeds (default {DEFAULT_MAX_SEEDS})",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except EngineError as exc:
        print(f"mine.py: failed reason={exc.reason_code} detail={exc.message}", file=sys.stderr)
        print(json.dumps({"status": "failed", "reason_code": exc.reason_code}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
