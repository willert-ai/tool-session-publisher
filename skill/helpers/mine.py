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
built from the session's own **document** where one can be resolved, and
falls back to the SESSION_INDEX row when it cannot.

That split is the whole point of this file, so it is worth stating plainly.
The index row is written by the wrap-up skill to answer *"what did I do this
week"*: it is an engineering conclusion with the journey already compressed
out. Feeding it to a drafting model asks that model to answer a different
question — *"what here would be worth telling someone"* — from material that
cannot support it, and the measured result was nine drafts about tests,
reviews and defect counts, all rejected. The document beside it holds the
story: what was tried, what was ruled out, what was still open. So `text`
now carries the document's narrative sections, and the row survives as
`seed_ref` only — which is what it is good for, being the ledger dedup key
and a stable operator-facing reference.

Three sources, in order:
  1. the session document's narrative sections (see `extract_narrative`),
     resolved from the row by date + fuzzy title/slug match;
  2. the SESSION_INDEX row's own outcome/insight columns, **iff** no
     document could be resolved — a missing or ambiguous document degrades
     to the pre-2026-08-28 behaviour and never fails the tick;
  3. best-effort `git log` subjects from a same-day match in a locally
     scanned repo, appended either way. A miss there just means a plainer
     `text`; it is enrichment, not the contract.

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

`--index` and `--queue-dir` isolate SESSION_INDEX and the ledger for testing.
Session-document lookup follows `--index` (documents live beside the index, so
its parent directory is the notes root), but posts/ dedup always reads the real
$NOTES_DIR/posts/x/ — there is no separate override for it, and those two
therefore diverge under a bare `--index`. A fully isolated test run needs
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

# --- session-document resolution + narrative extraction ---------------------

# Session documents live flat in the notes root as
# "YYYY-MM-DD - SESSION_<verb-slug>.md". The slug is NOT a deterministic
# transform of the index title — the wrap-up skill invents a shortened,
# verb-led one, and it drops, reorders and truncates words freely:
#   "Closed RUNBOOK § 8, disproved the 390px defect, and turned off LiveKit
#    observability"            -> closed-runbook-8-and-disabled-livekit-observability
#   "Hardened a copy-audit instrument after two refute rounds"
#                              -> hardened-copy-audit-instrument
# So resolution is a scored token match, not string surgery, and it refuses
# rather than guesses: a wrong document would attribute one session's story
# to another session's seed_ref, which is worse than the thin row.
SESSION_DOC_MARKER = "SESSION_"
SESSION_DOC_MIN_SCORE = 0.6

# Dropped from `_slug_tokens` on both sides — they carry no discriminating
# signal and their presence/absence is exactly what the slug varies on.
SLUG_STOPWORDS = frozenset(
    """a an the and or of to for on in at by with from into onto its it this that then
    than as is was were be been are against across after before not but""".split()
)

# Sections dropped from the narrative extract, matched as a normalised prefix
# of the heading text so suffixed variants ("Session Output — recruiting
# drafts, unposted") are covered.
#
# Three different reasons, worth keeping distinct:
#   - inventory, not narrative: files touched, entities, sources, deliverables
#     (tables of paths and names; token-heavy, story-free)
#   - already the seed's own framing: transferable insight is the same
#     distilled conclusion the index row's `insight` column carries, and
#     feeding it back prominently re-creates the exact compression this
#     change exists to undo
#   - instructions addressed to an agent: a handover context or transition
#     boot prompt is imperative text aimed at whoever reads it next. Passing
#     that into a headless drafting call hands the model a second, competing
#     set of orders. Dropping it is a safety call as much as a cost one.
# Matched as a prefix of the NORMALISED heading (see `_norm_heading`, which
# strips a leading section number — the wrap-up skill has emitted both
# "## Handover Context" and "## 9. Handover Context"). Prefix rather than
# containment on purpose: "Open Threads (handover to architect session)" is a
# section worth keeping, and containment would eat it.
NARRATIVE_DENY_PREFIXES = (
    "files touched",
    "entities mentioned",
    "external sources",
    "deliverables",  # also "Deliverables Created", "Concrete Deliverables"
    "concrete deliverables",
    "transferable insight",
    "handover",  # also "Handover Context", "Handover Prompts"
    "transition boot prompt",
    "continuity",  # also "Continuity Ledger", "Continuity Method"
    "references",
    "session output",
)

# Per-heading cap on that heading's own body, and a cap on the whole extract.
# Measured on the fixture-grade document (2026-08-26 warming-up, 22,757 bytes
# total): the kept set is ~13.7 KB and its largest single section ~5.4 KB, so
# neither cap bites on a typical document. They exist so one runaway section
# cannot starve the later ones, and so a pathological document cannot blow up
# a headless call's input.
NARRATIVE_SECTION_CHARS = 6000
NARRATIVE_TOTAL_CHARS = 20000

FRONTMATTER_MAX_LINES = 60

HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(\S.*)$")

# Redacted from the extract before it reaches the headless prompt. The index
# row never carried any of these; a session document does — measured across the
# 86 August documents: `op://` references in 8, absolute `/Users/` paths in 4,
# email addresses in 8, a tailnet address in 1.
#
# This is NOT the D6 gate and does not replace it. D6 inspects the OUTPUT body
# and is the barrier that decides what may be published; this shrinks what the
# model is shown in the first place, which is a different and cheaper thing.
# Redacting rather than skipping the document: these strings appear in ordinary
# prose about the work, and dropping a whole session because one line names a
# path would cost far more material than it protects.
NARRATIVE_REDACTIONS = (
    (re.compile(r"op://\S+"), "[redacted]"),
    (re.compile(r"(?<![\w/])(?:/Users|/home)/[^\s`'\"),]+"), "[path]"),
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "[email]"),
    (re.compile(r"\b100\.(?:6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])\.\d+\.\d+\b"), "[address]"),
    (re.compile(r"\b[\w-]+\.ts\.net\b"), "[host]"),
)


def _slug_tokens(text: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", text.lower()) if t and t not in SLUG_STOPWORDS]


def _doc_slug(path: Path) -> str:
    """The verb-slug part of "YYYY-MM-DD - SESSION_<slug>.md"."""
    stem = path.stem
    marker = stem.find(SESSION_DOC_MARKER)
    return stem[marker + len(SESSION_DOC_MARKER) :] if marker >= 0 else stem


def find_session_doc(session: dict, notes_base: Path) -> Path | None:
    """Resolve the session document for an index row, or None.

    Scores each same-date candidate by what fraction of ITS OWN slug tokens
    the row's title accounts for — asymmetric on purpose, since the slug is a
    lossy abbreviation of the title and never the other way round. Requires a
    clear winner: a tie between two same-date sessions means the row cannot be
    attributed, and None (degrade to the row) beats a coin flip.
    """
    try:
        candidates = sorted(notes_base.glob(f"{session['date']} *{SESSION_DOC_MARKER}*.md"))
    except OSError:
        return None
    if not candidates:
        return None
    title_tokens = set(_slug_tokens(session["title"]))
    if not title_tokens:
        return None
    scored = []
    for path in candidates:
        slug_tokens = set(_slug_tokens(_doc_slug(path)))
        if not slug_tokens:
            continue
        scored.append((len(slug_tokens & title_tokens) / len(slug_tokens), path))
    if not scored:
        return None
    scored.sort(key=lambda pair: (-pair[0], str(pair[1])))
    best_score, best_path = scored[0]
    if best_score < SESSION_DOC_MIN_SCORE:
        return None
    if len(scored) > 1 and scored[1][0] == best_score:
        return None
    return best_path


def _norm_heading(title: str) -> str:
    """Lowercase, punctuation-collapsed, with any leading section number gone.

    The number matters: documents in this corpus carry both `## Handover
    Context` and `## 9. Handover Context`, and a normaliser that keeps the `9`
    silently un-denies the numbered half of them.
    """
    normalised = " ".join(re.split(r"[^a-z0-9]+", title.lower())).strip()
    return re.sub(r"^\d+ ", "", normalised)


def _is_denied(level: int, title: str) -> bool:
    """Deny applies from level 2 down.

    A level-1 heading is the document's `# SESSION: <title>` line and the
    ancestor of everything below it, so a title that happens to start with a
    denied word ("Reviewed Overnight Deliverables…", and there is one in the
    corpus) would otherwise deny the entire document to an empty extract — and
    an empty extract degrades silently to the thin index row, which is the
    exact failure this file exists to fix.
    """
    return level >= 2 and _norm_heading(title).startswith(NARRATIVE_DENY_PREFIXES)


def _headings(lines: list[str]) -> list[tuple[int, int, str]]:
    """(line index, level, title) for every heading OUTSIDE a fenced block.

    Fence tracking is not pedantry: session documents embed shell and Python
    blocks whose comment lines start with `#`, and reading those as headings
    would slice a section in half at an arbitrary point.
    """
    heads: list[tuple[int, int, str]] = []
    in_fence = False
    for index, line in enumerate(lines):
        is_fence = line.lstrip().startswith("```")
        if not in_fence and not is_fence:
            match = HEADING_PATTERN.match(line)
            if match:
                heads.append((index, len(match.group(1)), match.group(2).strip()))
        if is_fence:
            in_fence = not in_fence
    return heads


def extract_narrative(doc_text: str) -> str:
    """The story-bearing part of a session document, as plain markdown.

    Keeps every section except the deny list, which means new sections the
    wrap-up skill grows later are included by default rather than silently
    dropped — the failure this whole change is correcting was material that
    existed and was never read.

    A heading's span runs to the next heading of the same-or-shallower level,
    so denying a `##` section drops its `###` children with it, and a section
    that appears nested in one document and top-level in another (the wrap-up
    skill emits `Approaches Ruled Out` both ways) is handled identically.
    """
    lines = doc_text.splitlines()

    # Drop the YAML frontmatter: it carries no narrative and does carry a
    # project path. Guarded on actually looking like frontmatter — a document
    # opening on a markdown horizontal rule would otherwise have everything up
    # to the next `---` eaten as if it were a header block.
    if lines and lines[0].strip() == "---":
        for index in range(1, min(len(lines), FRONTMATTER_MAX_LINES)):
            if lines[index].strip() == "---":
                if any(re.match(r"^[A-Za-z_][\w-]*:", line) for line in lines[1:index]):
                    lines = lines[index + 1 :]
                break

    heads = _headings(lines)
    if not heads:
        return ""

    kept: list[str] = []
    denied_at_level: int | None = None  # deepest open denied section's level
    for position, (start, level, title) in enumerate(heads):
        # A denied section owns every heading below it until one at its own
        # level or shallower closes it. Walking only to the immediate parent
        # would let a grandchild out: `## Handover Context` denies `### Detail`
        # but `### Detail` is not itself denied, so `#### Deeper` would be kept
        # — republishing the tail of a block excluded for being instructions
        # addressed to an agent.
        if denied_at_level is not None and level <= denied_at_level:
            denied_at_level = None
        if denied_at_level is not None:
            continue
        if _is_denied(level, title):
            denied_at_level = level
            continue
        # This heading's OWN body: up to the next heading of any level. Nested
        # sections are emitted by their own iteration, so nothing is doubled.
        end = heads[position + 1][0] if position + 1 < len(heads) else len(lines)
        body = "\n".join(lines[start + 1 : end]).strip("\n")
        if len(body) > NARRATIVE_SECTION_CHARS:
            body = body[:NARRATIVE_SECTION_CHARS].rstrip() + "\n…[section truncated]"
        kept.append(lines[start] if not body else f"{lines[start]}\n\n{body}")

    text = "\n\n".join(kept).strip()
    if len(text) > NARRATIVE_TOTAL_CHARS:
        text = text[:NARRATIVE_TOTAL_CHARS].rstrip() + "\n…[extract truncated]"
    for pattern, replacement in NARRATIVE_REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


def session_narrative(session: dict, notes_base: Path) -> str:
    """`extract_narrative` of the resolved document, or "" — never raises.

    Every failure mode here (no document, ambiguous match, unreadable file,
    a document with no headings) degrades to the empty string and therefore
    to the index-row text. A seed with thinner material is a worse post; a
    tick that died reading a note is no post at all.
    """
    path = find_session_doc(session, notes_base)
    if path is None:
        return ""
    try:
        return extract_narrative(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return ""


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


def build_text(session: dict, git_hits: list[str], narrative: str = "") -> str:
    """The seed's source material — the document's narrative if one resolved,
    the index row's own columns if not.

    The two paths are deliberately NOT merged. On the narrative path the row's
    `outcome`/`insight` columns are left out: they are the pre-compressed
    conclusion, and restating them beside the story they were compressed from
    puts the finished answer at the top of the model's source material. On the
    fallback path they are all there is.
    """
    parts: list[str] = []
    if narrative:
        # No synthetic header line. The document's own `# SESSION: <title>` H1
        # already opens the extract with the title and its `**Tags:**` line
        # carries the tags, so adding them would duplicate — and `text` is
        # declared quotable source to the model, unlike `seed_ref`, so nothing
        # should be promoted into it that is not already there.
        parts.append(narrative)
    else:
        # The pre-2026-08-28 shape, unchanged: when no document resolved, the
        # row's own columns are all there is.
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

    # Session documents live beside SESSION_INDEX.md, so a `--index` override
    # relocates document lookup with it — which is what makes a fully isolated
    # scratch run possible without a second flag.
    notes_base = index_path.parent

    report = {
        "status": "ok",
        "scanned": len(sessions),
        "in_window": len(in_window),
        "skipped_posted": 0,
        "skipped_ledgered": 0,
        "skipped_duplicate": 0,
        "with_document": 0,
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
                "score": score,
                "score_reasons": reasons,
                "_session": session,
                "_git_hits": git_hits,
            }
        )

    # Score desc primary, `seed_ref` (date-prefixed, so this is recency) desc
    # as the tiebreak — one composite key, no reliance on sort stability.
    candidates.sort(key=lambda c: (c["score"], c["seed_ref"]), reverse=True)

    # `text` is built only for the seeds that survive the cut. Scoring does not
    # read the document, so resolving and extracting one per in-window
    # candidate would read (and discard) tens of files per tick — on a deep
    # window that is ~60 documents to emit at most 3.
    seeds = []
    for candidate in candidates[: args.max_seeds]:
        session = candidate.pop("_session")
        git_hits = candidate.pop("_git_hits")
        narrative = session_narrative(session, notes_base)
        if narrative:
            report["with_document"] += 1
        # Its own field, not a `score_reasons` entry: that list's contract is
        # that every element names points scored, and this scores nothing.
        candidate["has_document"] = bool(narrative)
        candidate["text"] = build_text(session, git_hits, narrative)
        seeds.append(candidate)

    report["seeds"] = seeds
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
