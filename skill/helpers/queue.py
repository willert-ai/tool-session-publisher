#!/usr/bin/env python3
"""
queue.py — the x-comms-engine queue contract.

The queue lives OUTSIDE this repo, under the operator's notes directory:

    $SESSION_PUBLISHER_NOTES_DIR/posts/x/queue/
        q_YYYY-MM-DD_HHMMSS.md   one entry per file, actionable entries only
        .ledger.jsonl            append-only event ledger
        .archive/                terminal-state entries

Subcommands implemented here:

    add         anti-leak gate + <=280 gate + schema write + `drafted` ledger line
    --validate  exit 0 on an empty or fully valid queue, 1 otherwise
    expire      queued entries older than 14 days, or over the capacity of 10,
                move to .archive/ and append an `expired` ledger line
    list        machine-readable view of the actionable queue
    review      the operator's interactive loop, one entry at a time:
                [a]pprove [e]dit [k]ill [c]opy [s]kip [q]uit
    approve     flip queued -> approved, measure edit_distance, append the body
                to the Stage-5.5 corpus
    kill        archive an entry the operator does not want
    copy        put the body on the clipboard, stamp posted_at, archive — and
                approve first if the entry is still queued

`review` is a thin terminal shell over `approve`/`kill`/`copy`: every state
change goes through the same three functions, so the interactive path and the
scriptable path cannot drift.

The entry schema is the drafting engine's contract: every field the engine
writes is written by this helper, and `--validate` is the only thing that gets
to say an entry is well-formed. `body_drafted` freezes the engine's original
body at add time — it is the anchor edit_distance is later measured against, so
nothing in this file ever rewrites it.

Approval is zero-LLM by design (D5). The seven corpus axes and guide_compliance
were judged once, at draft time, and validated against examples-template.md's
vocabulary before the entry was ever written; approval only copies them across.
When the operator edits a body hard enough that those tags may no longer
describe it (edit_distance > 0.2 x the drafted body's length), the corpus row is
appended with a `retag: pending` marker rather than silently re-tagged.

Corpus appends obey the F17 blockquote law: every body line is written as
"> line" and a blank line as a bare ">", because mirror.py reads a body as a
*contiguous* run of `>` lines and stops at the first line that is not one. The
writer proves it rather than asserting it — the rendered file is parsed back
through mirror.py and the new entry's body compared byte-for-byte before the
write lands.

Ledger concurrency: writers append one whole line via a single O_APPEND write,
which is what keeps two ticks from interleaving mid-line. Readers tolerate a
torn tail line and report it rather than crashing; callers that must not act on
a partial view (the miner's dedup pass) use `read_ledger(strict=True)` and fail
closed on an unreadable ledger.

Stdout is JSON on every machine-facing path. Rejections additionally write a
reason-coded, body-free line to stderr so a launchd tick log records *why* a
draft was dropped without ever recording the draft. `review` is the one
exception: it is an operator-facing terminal loop, so it renders cards to stdout
and prints a JSON summary of the session when it exits.

NAME HAZARD — this file shadows the stdlib `queue` module. Any script run from
this directory gets it at `sys.path[0]`, so a sibling helper doing `import queue`
lands here. `concurrent.futures.thread` imports stdlib `queue` internally, so a
thread pool in a sibling helper dies with a confusing `module 'queue' has no
attribute 'SimpleQueue'`. `subprocess.run(..., timeout=...)` is unaffected and is
the right tool for a headless call. The filename is fixed by the queue contract.

Environment:
    SESSION_PUBLISHER_NOTES_DIR   notes root (default ~/personal-notes)
    SESSION_PUBLISHER_TZ          timestamp zone for every stamp written here
    X_COMMS_HANDLE                X handle for corpus rows; when unset the handle
                                  is read off the corpus's own last entry, so a
                                  seeded corpus needs no configuration
    X_COMMS_CORPUS                override examples.local.md (testing)
    EDITOR / VISUAL               editor launched by `review`'s [e]dit action

Smoke tests:
    python3 queue.py --validate
    python3 queue.py add --source manual --pillar P1 --seed-ref "2026-08-25 - x" \\
        --tags-json '{"tone_register": "clinical-peer", ...}' --body "hello"
    python3 queue.py expire --max-age-days 14 --capacity 10
    python3 queue.py list --queue-dir /tmp/q
    python3 queue.py approve q_2026-08-26_073104 --queue-dir /tmp/q
    python3 queue.py copy q_2026-08-26_073104 --queue-dir /tmp/q --no-clipboard
    python3 queue.py review --queue-dir /tmp/q
"""

from __future__ import annotations

import os
import sys

# Same guard draft.py and mine.py already carry, needed here from this commit on:
# running this file as a script puts its own directory at sys.path[0], and `review`
# shells out ($EDITOR, pbcopy) via `subprocess`, which pulls in `selectors` ->
# `import select` -> the sibling session-selection helper instead of the stdlib
# module. Dropping our own directory is a no-op when a sibling imports us by file
# path (draft.py and mine.py both did it first) and is what keeps a direct
# `python3 queue.py review` from dying on an unrelated helper's filename.
_HELPERS_DIR = os.path.dirname(os.path.realpath(__file__))
sys.path[:] = [p for p in sys.path if os.path.realpath(p or os.getcwd()) != _HELPERS_DIR]

import argparse  # noqa: E402
import hashlib  # noqa: E402
import importlib.util  # noqa: E402
import json  # noqa: E402
import re  # noqa: E402
import shlex  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
from datetime import datetime, timedelta  # noqa: E402
from pathlib import Path  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

NOTES_BASE = Path(
    os.environ.get("SESSION_PUBLISHER_NOTES_DIR", str(Path.home() / "personal-notes"))
)
QUEUE_DIR = NOTES_BASE / "posts" / "x" / "queue"
TZ = ZoneInfo(os.environ.get("SESSION_PUBLISHER_TZ", "UTC"))

HELPERS_DIR = Path(_HELPERS_DIR)
PROMPTS_DIR = HELPERS_DIR.parent / "prompts"
EXAMPLES_TEMPLATE = PROMPTS_DIR / "examples-template.md"
PRIVATE_TERMS = PROMPTS_DIR / "private-terms.local.md"
# Overridable so the append path can be exercised end to end without writing into
# the operator's real corpus — same testing idiom as draft.py's X_COMMS_CLI.
CORPUS = Path(
    os.environ.get("X_COMMS_CORPUS") or PROMPTS_DIR / "examples.local.md"
).expanduser()
MIRROR_HELPER = HELPERS_DIR / "mirror.py"

LEDGER_NAME = ".ledger.jsonl"
ARCHIVE_NAME = ".archive"
ENTRY_GLOB = "q_*.md"
ENTRY_ID = re.compile(r"^q_\d{4}-\d{2}-\d{2}_\d{6}$")

MAX_BODY_CHARS = 280
DEFAULT_CAPACITY = 10
DEFAULT_MAX_AGE_DAYS = 14

# D5/F20: past this share of the drafted body's length the pre-computed corpus
# tags describe a body the operator has since rewritten, so the appended row is
# marked for the next curation pass instead of being trusted.
RETAG_RATIO = 0.2

SOURCES = ("miner", "backlog", "voice", "manual")
PILLARS = ("P1", "P2", "P3", "P4")
STATUSES = ("queued", "approved", "posted", "killed", "expired")
TERMINAL_STATUSES = ("posted", "killed", "expired")
# Statuses the operator can still act on — what `review` and `list` walk. An
# approved entry stays in the queue directory precisely because it still has an
# action outstanding: the copy that carries it to X.
ACTIONABLE_STATUSES = ("queued", "approved")
LEDGER_EVENTS = ("drafted", "approved", "posted", "killed", "expired")

# Tried in order; the first one that exists and exits 0 wins.
CLIPBOARD_COMMANDS = (["pbcopy"], ["xclip", "-selection", "clipboard"], ["wl-copy"])

# Written in this order so a queue file always reads the same way.
SCALAR_FIELDS = (
    "id",
    "created_at",
    "drafted_by",
    "source",
    "seed_key",
    "seed_ref",
    "pillar",
    "status",
    "decision_at",
    "edit_distance",
    "posted_at",
    "body_chars",
)
ARC_FIELDS = ("arc_id", "arc_pos", "arc_of", "arc_note")
REQUIRED_FIELDS = SCALAR_FIELDS  # arc_* are optional; omitted by non-arc entries

TAG_AXES = (
    "tone_register",
    "hook_structure",
    "sentence_rhythm",
    "topic_ownership",
    "constraint_disclosure",
    "topic_area",
    "length",
    "guide_compliance",
)
# guide_compliance is an integer range, not a value list — every other axis is
# enum-checked against the template vocabulary.
ENUM_AXES = tuple(a for a in TAG_AXES if a != "guide_compliance")

# --- D6 anti-leak gate ------------------------------------------------------
# Only *shapes* live here. Operator-specific literals (machine names, private
# repo names, family and third-party names) belong in private-terms.local.md,
# which is gitignored — this file is public.
LEAK_SHAPES = (
    ("leak:abs_path", re.compile(r"/Users/")),
    ("leak:op_ref", re.compile(r"op://")),
    (
        "leak:tailnet_ip",
        # CGNAT range only (100.64.0.0/10). A bare `100.` would false-positive on
        # the ordinary numbers the drafting guide asks for.
        re.compile(r"\b100\.(?:6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])\.\d{1,3}\.\d{1,3}\b"),
    ),
    ("leak:email", re.compile(r"\b[\w.%+-]+@[\w-]+\.[A-Za-z]{2,}\b")),
    ("leak:ts_hostname", re.compile(r"\b[\w-]+\.ts\.net\b")),
    # Six colon-separated hex pairs. Timestamps top out at three groups, so this cannot
    # collide with a duration the drafting guide asks for.
    ("leak:mac_address", re.compile(r"\b(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}\b")),
)


class QueueError(Exception):
    """Operator-visible failure carrying a reason code."""

    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.message = message


class LedgerUnreadable(Exception):
    """The ledger exists but cannot be read — callers must fail closed."""


# --- paths ------------------------------------------------------------------


def seed_key_for(seed_ref: str) -> str:
    """The one formula that turns a `seed_ref` into a ledger `seed_key`.

    `cmd_add` always derives it fresh from `seed_ref` rather than trusting a
    caller-supplied value — this is the single place that formula lives, so
    a caller checking ledger dedup ahead of a write (mine.py) can compute the
    same key `cmd_add` will, instead of keeping its own copy that silently
    stops matching if this ever changes.
    """
    return hashlib.sha1(seed_ref.encode("utf-8")).hexdigest()


def resolve_queue_dir(override: str | None) -> Path:
    return Path(override).expanduser() if override else QUEUE_DIR


def ledger_path(queue_dir: Path) -> Path:
    return queue_dir / LEDGER_NAME


def archive_dir(queue_dir: Path) -> Path:
    return queue_dir / ARCHIVE_NAME


# --- vocabulary + denylist loading -----------------------------------------


def load_tag_vocabulary(template: Path = EXAMPLES_TEMPLATE) -> dict[str, tuple[str, ...]]:
    """Parse the allowed corpus_tags values out of examples-template.md.

    The template is the single source of truth for the tag vocabulary; parsing it
    keeps this helper from drifting into a second, silently divergent copy.

    Two line shapes carry values, so both are read: the `— one of: a, b, c` form
    used by six axes, and `length`'s `— `shortform` (…) or `longform` (…)` form.
    Every backticked token after the em dash is taken as a value.

    Returns an empty dict when the template is unreadable. Validation treats a
    missing axis as a problem rather than a skipped check — a vocabulary that
    fails to load must not silently disable the enum gate.
    """
    axis_line = re.compile(r"^- `([a-z_]+)` — (.+)$")
    vocab: dict[str, tuple[str, ...]] = {}
    try:
        text = template.read_text(encoding="utf-8")
    except OSError:
        return vocab
    for line in text.splitlines():
        match = axis_line.match(line.strip())
        if not match:
            continue
        axis, raw = match.group(1), match.group(2)
        if axis not in ENUM_AXES:
            continue
        values = tuple(re.findall(r"`([^`]+)`", raw))
        if values:
            vocab[axis] = values
    return vocab


def load_private_terms(path: Path = PRIVATE_TERMS) -> tuple[str, ...]:
    """Read operator-specific denylist terms from the gitignored local file.

    Absent is a legitimate state — the file is authored in a later commit, and a
    missing denylist must not stop the shape-based gate from running.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ()
    terms = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("- "):
            continue
        term = line[2:].strip().strip("`").strip()
        if term:
            terms.append(term)
    return tuple(terms)


def scan_for_leaks(text: str, *, private_terms: bool = True) -> tuple[str, str] | None:
    """Return (reason_code, matched_pattern_name) for the first leak found.

    `private_terms=False` runs the shape patterns only. That mode exists for text
    which is stored but never published: the operator denylist names the private
    estate on purpose, so applying it to private-by-design text rejects almost
    everything (see cmd_add).
    """
    for reason_code, pattern in LEAK_SHAPES:
        if pattern.search(text):
            return reason_code, pattern.pattern
    if not private_terms:
        return None
    for term in load_private_terms():
        if re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text, re.IGNORECASE):
            # The term itself is private — report the rule, never the match.
            return "leak:private_term", "private-terms.local.md"
    return None


# --- entry serialisation ----------------------------------------------------


def _fmt(value) -> str:
    return "" if value is None else str(value)


def render_entry(fields: dict, body: str) -> str:
    """Render a queue entry file: frontmatter block, then the post body."""
    lines = ["---"]
    for key in SCALAR_FIELDS:
        lines.append(f"{key}: {_fmt(fields.get(key))}".rstrip())
    for key in ARC_FIELDS:
        if fields.get(key) not in (None, ""):
            lines.append(f"{key}: {_fmt(fields[key])}")
    lines.append("body_drafted: |")
    for body_line in fields["body_drafted"].split("\n"):
        lines.append(f"  {body_line}".rstrip())
    lines.append("corpus_tags:")
    for axis in TAG_AXES:
        lines.append(f"  {axis}: {_fmt(fields['corpus_tags'].get(axis))}")
    lines.append("---")
    lines.append("")
    lines.append(body)
    return "\n".join(lines) + "\n"


def parse_entry(path: Path) -> tuple[dict, str]:
    """Parse a queue entry file into (fields, body)."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise QueueError("schema:unreadable", f"cannot read {path.name}: {exc.strerror}") from exc
    return parse_text(text, label=path.name)


def parse_text(text: str, label: str) -> tuple[dict, str]:
    """Parse queue entry text into (fields, body).

    Raises QueueError with a schema:* reason code when the text is not a queue
    entry at all. Field-level problems are left to validate_fields. Error
    messages carry a line number, never the offending line — a bad line can hold
    a verbatim seed reference, and these messages reach the tick log.
    """
    if not text.startswith("---\n"):
        raise QueueError("schema:no_frontmatter", f"{label}: missing frontmatter")
    rest = text[4:]
    end = rest.find("\n---\n")
    if end == -1:
        raise QueueError("schema:unterminated", f"{label}: unterminated frontmatter")
    front, body = rest[:end], rest[end + 5 :]

    fields: dict = {"corpus_tags": {}}
    mode = None  # None | "body_drafted" | "corpus_tags"
    drafted: list[str] = []
    for lineno, line in enumerate(front.split("\n"), start=2):
        if mode == "body_drafted" and (line.startswith("  ") or not line.strip()):
            # A blank line inside the block is a blank line of the body — the
            # renderer strips trailing whitespace, so it arrives here empty.
            drafted.append(line[2:] if line.startswith("  ") else "")
            continue
        if line.startswith("  ") and mode == "corpus_tags":
            key, _, value = line[2:].partition(":")
            fields["corpus_tags"][key.strip()] = value.strip()
            continue
        if line.strip() == "body_drafted: |":
            mode = "body_drafted"
            continue
        if line.strip() == "corpus_tags:":
            mode = "corpus_tags"
            continue
        if not line.strip():
            continue
        mode = None
        key, sep, value = line.partition(":")
        if not sep:
            raise QueueError("schema:bad_line", f"{label}: unparseable line {lineno}")
        fields[key.strip()] = value.strip()
    fields["body_drafted"] = "\n".join(drafted).rstrip("\n")
    return fields, body.lstrip("\n").rstrip("\n")


def validate_fields(fields: dict, body: str, vocab: dict[str, tuple[str, ...]]) -> list[str]:
    """Return a list of human-readable schema problems (empty = valid)."""
    problems = []

    for key in REQUIRED_FIELDS:
        if key not in fields:
            problems.append(f"missing field `{key}`")

    status = fields.get("status", "")
    if status not in STATUSES:
        problems.append(f"status `{status}` not in {list(STATUSES)}")
    if fields.get("source", "") not in SOURCES:
        problems.append(f"source `{fields.get('source')}` not in {list(SOURCES)}")
    if fields.get("pillar", "") not in PILLARS:
        problems.append(f"pillar `{fields.get('pillar')}` not in {list(PILLARS)}")

    for key in ("id", "created_at", "drafted_by", "seed_key", "seed_ref"):
        if not fields.get(key):
            problems.append(f"field `{key}` must not be empty")

    for key in ("created_at", "decision_at", "posted_at"):
        if fields.get(key) and parse_ts(fields[key]) is None:
            problems.append(f"{key} `{fields[key]}` is not an ISO timestamp")

    # Every status but `queued` is the record of a decision, so it has to say when.
    if status in STATUSES and status != "queued" and not fields.get("decision_at"):
        problems.append(f"status `{status}` without a decision_at")
    if fields.get("posted_at") and status != "posted":
        problems.append(f"posted_at is set but status is `{status}`")

    raw_distance = fields.get("edit_distance")
    if raw_distance not in (None, ""):
        try:
            if int(raw_distance) < 0:
                problems.append(f"edit_distance `{raw_distance}` is negative")
        except (TypeError, ValueError):
            problems.append(f"edit_distance `{raw_distance}` is not an integer")

    if not body.strip():
        problems.append("body is empty")
    if len(body) > MAX_BODY_CHARS:
        problems.append(f"body is {len(body)} chars, over the {MAX_BODY_CHARS} limit")
    try:
        if int(fields.get("body_chars", "")) != len(body):
            problems.append(f"body_chars {fields.get('body_chars')} != actual {len(body)}")
    except (TypeError, ValueError):
        problems.append(f"body_chars `{fields.get('body_chars')}` is not an integer")

    if not fields.get("body_drafted", "").strip():
        problems.append("body_drafted is empty — the edit_distance anchor is missing")

    tags = fields.get("corpus_tags", {})
    for axis in TAG_AXES:
        value = tags.get(axis, "")
        if not value:
            problems.append(f"corpus_tags.{axis} is missing")
            continue
        if axis == "guide_compliance":
            try:
                if not 1 <= int(value) <= 5:
                    problems.append(f"corpus_tags.guide_compliance `{value}` outside 1–5")
            except ValueError:
                problems.append(f"corpus_tags.guide_compliance `{value}` is not an integer")
            continue
        allowed = vocab.get(axis)
        if allowed is None:
            # Fail closed: no vocabulary means the enum gate is not running.
            problems.append(f"corpus_tags.{axis} unverifiable — vocabulary for `{axis}` not loaded")
        elif value not in allowed:
            problems.append(f"corpus_tags.{axis} `{value}` not in examples-template vocabulary")
    for axis in tags:
        if axis not in TAG_AXES:
            problems.append(f"corpus_tags.{axis} is not a known axis")

    arc_present = [k for k in ARC_FIELDS if fields.get(k)]
    if arc_present and not all(fields.get(k) for k in ("arc_id", "arc_pos", "arc_of")):
        problems.append("partial arc metadata — arc_id, arc_pos and arc_of travel together")
    if arc_present:
        # C5 orders an arc by arc_pos; as strings "10" would sort before "2".
        positions = {}
        for key in ("arc_pos", "arc_of"):
            raw = fields.get(key, "")
            if not raw:
                continue
            try:
                positions[key] = int(raw)
            except ValueError:
                problems.append(f"{key} `{raw}` is not an integer")
        if positions.get("arc_pos", 1) < 1:
            problems.append(f"arc_pos `{fields.get('arc_pos')}` must be 1 or greater")
        if "arc_pos" in positions and "arc_of" in positions:
            if positions["arc_pos"] > positions["arc_of"]:
                problems.append(
                    f"arc_pos {positions['arc_pos']} exceeds arc_of {positions['arc_of']}"
                )

    return problems


def reject_multiline_scalars(fields: dict) -> None:
    """Refuse any scalar carrying a newline.

    A scalar is rendered as one `key: value` line, so an embedded newline would
    inject arbitrary frontmatter — a two-line `arc_note` from the drafting model,
    or a `seed_ref` quoting a wrapped row, is enough to smuggle in a second
    `status:` line. Rejecting at the write boundary keeps every later consumer
    from having to defend against it.
    """
    for key in SCALAR_FIELDS + ARC_FIELDS:
        value = fields.get(key)
        if isinstance(value, str) and ("\n" in value or "\r" in value):
            raise QueueError("input:newline", f"field `{key}` must be a single line")


def parse_ts(raw: str) -> datetime | None:
    """Parse an ISO timestamp; naive values are read as local TZ."""
    try:
        parsed = datetime.fromisoformat(raw.strip())
    except (TypeError, ValueError):
        return None
    return parsed.replace(tzinfo=TZ) if parsed.tzinfo is None else parsed


# --- ledger -----------------------------------------------------------------


def append_ledger(queue_dir: Path, event: dict) -> None:
    """Append one whole JSON line with a single O_APPEND write."""
    path = ledger_path(queue_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(event, separators=(",", ":"), ensure_ascii=False) + "\n"
    data = line.encode("utf-8")
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        # One O_APPEND write is atomic at these sizes, but a short write would
        # itself create the torn line readers have to defend against — drain it.
        while data:
            data = data[os.write(fd, data) :]
    finally:
        os.close(fd)


def read_ledger(queue_dir: Path, strict: bool = False) -> tuple[list[dict], int]:
    """Return (events, torn_line_count).

    Tolerant callers get the events that survived plus a count. `strict=True`
    raises LedgerUnreadable on an I/O error *or* on any torn line, because a torn
    line means events are missing: the next append glues onto the partial line,
    so one tear destroys two events. A caller whose correctness depends on a
    complete view — the miner's dedup pass — must fail closed on that, or a
    killed seed loses its `killed` record and gets re-queued.
    """
    path = ledger_path(queue_dir)
    if not path.exists():
        return [], 0
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        if strict:
            raise LedgerUnreadable(str(exc)) from exc
        return [], 0
    events, torn = [], 0
    for line in raw.splitlines():
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            torn += 1
    if strict and torn:
        raise LedgerUnreadable(f"{torn} torn line(s) — events are missing")
    return events, torn


def ledger_event(entry_id: str, seed_key: str, event: str, **extra) -> dict:
    if event not in LEDGER_EVENTS:
        raise QueueError("ledger:bad_event", f"unknown ledger event `{event}`")
    payload = {
        "ts": datetime.now(TZ).isoformat(timespec="seconds"),
        "id": entry_id,
        "seed_key": seed_key,
        "event": event,
    }
    payload.update({k: v for k, v in extra.items() if v is not None})
    return payload


# --- queue reads ------------------------------------------------------------


def entry_paths(queue_dir: Path) -> list[Path]:
    if not queue_dir.is_dir():
        return []
    return sorted(p for p in queue_dir.glob(ENTRY_GLOB) if p.is_file())


def validate_rendered(rendered: str, vocab: dict[str, tuple[str, ...]]) -> list[str]:
    """Parse rendered entry text back and validate it, as a reader would see it."""
    try:
        fields, body = parse_text(rendered, label="<rendered>")
    except QueueError as exc:
        return [f"rendered entry does not parse back: {exc.message}"]
    return validate_fields(fields, body, vocab)


def write_entry_atomic(path: Path, text: str) -> None:
    """Write via a same-directory temp file + rename.

    The queue sits in a cloud-synced directory; a rename means a sync client
    never sees a half-written entry.
    """
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def all_entry_paths(queue_dir: Path) -> list[Path]:
    """Queue entries plus archived ones — the whole history of an arc."""
    return entry_paths(queue_dir) + entry_paths(archive_dir(queue_dir))


def load_entry(queue_dir: Path, entry_id: str) -> tuple[Path, dict, str]:
    """Read one entry fresh off disk, by id.

    Every state change re-reads through here immediately before it writes.
    `expire` is a second mover over the same directory and may have archived the
    entry since the operator saw it on screen, so a review card is a snapshot,
    never a lock. The id is shape-checked before it touches the filesystem: it
    arrives from the command line and is otherwise a path fragment.
    """
    if not ENTRY_ID.match(entry_id):
        raise QueueError("input:bad_id", f"`{entry_id}` is not a queue entry id")
    path = queue_dir / f"{entry_id}.md"
    if not path.is_file():
        raise QueueError("state:gone", f"no queue entry `{entry_id}` (already archived?)")
    fields, body = parse_entry(path)
    return path, fields, body


def stage_entry(path: Path, fields: dict, body: str, vocab: dict[str, tuple[str, ...]]) -> Path:
    """Run every check, then write the bytes to a same-directory temp file.

    Split out from `save_entry` so a caller with an *irreversible* side effect —
    the corpus append — can prove the entry write will succeed before it fires.
    Everything that can reject happens here; `os.replace` afterwards is the only
    step left, and it is atomic.

    The round-trip is the point: this file is a contract other commits parse, so
    a writer that only checks its in-memory dict can ship an entry nothing can
    read back. Everything here goes through the same gate `add` uses.
    """
    fields["body_chars"] = len(body)
    reject_multiline_scalars(fields)
    problems = validate_fields(fields, body, vocab)
    if problems:
        raise QueueError("schema:invalid", "; ".join(problems))
    rendered = render_entry(fields, body)
    round_tripped = validate_rendered(rendered, vocab)
    if round_tripped:
        raise QueueError("schema:round_trip", "; ".join(round_tripped))
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(rendered, encoding="utf-8")
    return tmp


def save_entry(path: Path, fields: dict, body: str, vocab: dict[str, tuple[str, ...]]) -> None:
    """Validate, render, parse the rendered bytes back, then write atomically."""
    os.replace(stage_entry(path, fields, body, vocab), path)


def check_not_archived(queue_dir: Path, path: Path) -> None:
    """Refuse to act on an entry `expire` has already moved out from under us.

    D3 names expiry the single mover so review never races it, but a mover that
    *renames* and a transition that *rewrites the same path* are not mutually
    exclusive: the rewrite happily re-creates a file the mover just unlinked,
    leaving one id in two files with contradicting statuses — and `--validate`
    calls that healthy, because an `approved` entry in the queue is legitimate.
    """
    if (archive_dir(queue_dir) / path.name).exists():
        raise QueueError("state:raced", f"`{path.stem}` was archived by another process")


def archive_entry(
    queue_dir: Path, path: Path, fields: dict, body: str, vocab: dict[str, tuple[str, ...]]
) -> Path:
    """Move a terminal entry out of the actionable queue (D3).

    Written to `.archive/` first and unlinked second: the reverse order would
    leave a window where the entry exists nowhere.
    """
    target = archive_dir(queue_dir)
    target.mkdir(parents=True, exist_ok=True)
    destination = target / path.name
    save_entry(destination, fields, body, vocab)
    path.unlink(missing_ok=True)
    return destination


# --- edit distance ----------------------------------------------------------


def edit_distance(before: str, after: str) -> int:
    """Character-level Levenshtein distance between the drafted and final body.

    D11's quality signal, measured against `body_drafted` (F10) — the engine's
    original, frozen at add time — rather than against whatever the body happened
    to be a moment ago. Bodies are capped at 280 characters, so the quadratic
    table is at most 280x280 and the two-row form is plenty.
    """
    if before == after:
        return 0
    if not before:
        return len(after)
    if not after:
        return len(before)
    previous = list(range(len(after) + 1))
    for i, left in enumerate(before, start=1):
        current = [i]
        for j, right in enumerate(after, start=1):
            current.append(
                min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (left != right))
            )
        previous = current
    return previous[-1]


def needs_retag(distance: int, drafted: str) -> bool:
    """True when the operator edited past the point the draft-time tags describe."""
    return distance > RETAG_RATIO * max(len(drafted), 1)


# --- Stage 5.5 corpus writer ------------------------------------------------
# Loaded by explicit path for the same reason draft.py loads this file that way:
# `import mirror` only resolves to the sibling while this directory happens to be
# on sys.path, and the guard at the top of this file removes it on purpose.

_MIRROR_MODULE = None


def mirror_module():
    """Load (once) and return the sibling mirror module.

    The corpus format is mirror.py's to define. Rather than restate its parser
    here, the writer renders a candidate file and asks mirror.py to read it back —
    if the two ever disagree, the append fails instead of silently truncating an
    entry at its first paragraph.
    """
    global _MIRROR_MODULE
    if _MIRROR_MODULE is None:
        spec = importlib.util.spec_from_file_location("x_comms_mirror", MIRROR_HELPER)
        if spec is None or spec.loader is None:  # pragma: no cover — packaging accident
            raise QueueError("corpus:mirror_missing", "cannot load mirror.py")
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as exc:  # noqa: BLE001 — a broken sibling must not traceback
            raise QueueError("corpus:mirror_missing", f"cannot load mirror.py: {exc}") from exc
        _MIRROR_MODULE = module
    return _MIRROR_MODULE


CORPUS_HEADER = """# Examples corpus — operator's own approved bodies

**Local-only, gitignored (LD11 Class B).** Schema reference: `examples-template.md`.
Created by `helpers/queue.py` on the first approval; read by `helpers/mirror.py`
at Stage 5.5.

**F17 blockquote law — do not hand-edit a body.** Every body line carries `"> "`; a
blank line inside a body is written as a bare `">"`. `mirror.py` reads a body as a
*contiguous* run of `>` lines and stops at the first line that is not one.

---
"""


def quote_body(body: str) -> str:
    """Render a post body as an F17-safe blockquote."""
    return "\n".join(">" if not line else f"> {line}" for line in body.split("\n"))


def read_corpus() -> str:
    try:
        return CORPUS.read_text(encoding="utf-8")
    except FileNotFoundError:
        return CORPUS_HEADER
    except OSError as exc:
        raise QueueError("corpus:unreadable", f"cannot read the corpus: {exc.strerror}") from exc


def corpus_headings(text: str) -> list[str]:
    """Every `### <id>` heading in file order, parsed or not.

    Numbering reads from here rather than from mirror.py's parsed entries: a
    malformed entry mirror.py drops still owns its number, and reusing it would
    put two rows with the same id in one file.
    """
    heading = mirror_module().ENTRY_HEADING
    return [m.group(1) for m in (heading.match(line) for line in text.splitlines()) if m]


def corpus_identity(text: str, entries: list[dict]) -> tuple[str, str, int]:
    """Return (handle, id prefix, next number) for the row about to be appended.

    Derived from the corpus rather than hard-coded: this file is public and the
    operator's handle is not. `X_COMMS_HANDLE` wins when set; otherwise the handle
    of the corpus's last parsed entry is reused, which makes a seeded corpus
    self-perpetuating and a fresh one fall back to a neutral placeholder.

    The id prefix is taken from the last numbered id belonging to *that same
    handle*, never from whichever id happens to come first in the file. A corpus
    holding reference bloggers alongside the operator's own posts is the designed
    state (examples-template.md says so), and a first-id-wins rule would file
    every future approval under someone else's id namespace — eventually
    colliding with a real entry of theirs.
    """
    handle = os.environ.get("X_COMMS_HANDLE", "").strip()
    if not handle:
        for entry in reversed(entries):
            if entry.get("handle"):
                handle = str(entry["handle"])
                break
    handle = handle or "operator"

    ids = corpus_headings(text)
    own = {str(e.get("id")) for e in entries if e.get("handle") == handle}

    prefix = ""
    for entry_id in reversed(ids):
        match = re.match(r"^(.*)-(\d+)$", entry_id)
        if match and entry_id in own:
            prefix = match.group(1)
            break
    if not prefix:
        prefix = re.sub(r"[^a-z0-9]+", "-", handle.lower()).strip("-")[:12] or "own"

    highest = 0
    for entry_id in ids:
        match = re.match(r"^(.*)-(\d+)$", entry_id)
        if match and match.group(1) == prefix:
            highest = max(highest, int(match.group(2)))
    return handle, prefix, highest + 1


def corpus_body_for(text: str, entries: list[dict], entry_id: str) -> tuple[str, str] | None:
    """Find the corpus row a queue entry already produced, as (corpus_id, body).

    Walks headings and `- source_entry:` lines together, because the marker is
    curation metadata mirror.py does not carry into its output.
    """
    marker = re.compile(rf"^- source_entry:\s*{re.escape(entry_id)}\s*$")
    heading = mirror_module().ENTRY_HEADING
    current = ""
    for line in text.splitlines():
        match = heading.match(line)
        if match:
            current = match.group(1)
        elif current and marker.match(line):
            for entry in entries:
                if entry.get("id") == current:
                    return current, str(entry.get("body", ""))
            return current, ""
    return None


def render_corpus_entry(
    entry_id: str,
    handle: str,
    tags: dict,
    body: str,
    *,
    source_entry: str,
    captured_at: str,
    distance: int,
    retag: bool,
) -> str:
    """Render one `examples.local.md` block.

    `post_url`, `approx_likes` and `approx_reposts` are written empty on purpose:
    at approval the post does not exist yet. A zero in the engagement fields would
    be a measurement nobody took — mirror.py's `coerce_int` reads an empty value
    back as null, which is the honest answer. (`post_url` is a string field, so it
    round-trips as `""` rather than null; nothing reads it in v1.)
    """
    lines = [f"### {entry_id}", ""]
    meta = [
        ("handle", handle),
        ("post_url", ""),
        ("captured_at", captured_at),
        ("approx_likes", ""),
        ("approx_reposts", ""),
    ]
    # The seven register axes plus guide_compliance, exactly as the engine judged
    # them at draft time — approval adds no judgement of its own (D5).
    for axis in TAG_AXES:
        meta.append((axis, tags.get(axis, "")))
    meta.append(
        (
            "personality_fit_note",
            f'"x-comms-engine: captured at approval; edit_distance {distance} '
            f'of {len(body)} chars"',
        )
    )
    meta.append(("source_entry", source_entry))
    if retag:
        # F20: the tags above describe the drafted body, not this one.
        meta.append(("retag", "pending"))
    for key, value in meta:
        lines.append(f"- {key}: {value}".rstrip())
    lines.extend(["", quote_body(body), "", "---", ""])
    return "\n".join(lines)


def append_to_corpus(
    entry_id: str, tags: dict, body: str, distance: int, *, retag: bool, when: datetime
) -> dict:
    """Append an approved body to the Stage-5.5 corpus, proving the round-trip.

    Idempotent by `source_entry`: an approval that fails after this point can be
    retried without putting the same body in the corpus twice.

    Trailing whitespace on the body's final line is dropped, because mirror.py
    rstrips the joined body and byte-equality could not otherwise hold. Nothing
    else about the body is touched — mid-body trailing spaces survive, and one
    seeded entry depends on that.
    """
    mirror = mirror_module()
    text = read_corpus()
    before_entries, before_malformed = mirror.parse_examples(text)
    corpus_body = body.rstrip()
    if not corpus_body:
        raise QueueError("corpus:empty_body", "refusing to append an empty body")

    existing = corpus_body_for(text, before_entries, entry_id)
    if existing is not None:
        # A retry after a partial failure. Same body: nothing to do. Different
        # body — the operator fixed the problem and edited on the way back
        # through — reporting success would leave the corpus teaching a body
        # neither the queue nor the operator still stands behind.
        if existing[1] != corpus_body:
            raise QueueError(
                "corpus:body_conflict",
                f"`{existing[0]}` already records a different body for this entry",
            )
        return {"appended": False, "reason": "already_present", "corpus_id": existing[0]}

    handle, prefix, number = corpus_identity(text, before_entries)
    corpus_id = f"{prefix}-{number:03d}"

    block = render_corpus_entry(
        corpus_id,
        handle,
        tags,
        corpus_body,
        source_entry=entry_id,
        captured_at=when.date().isoformat(),
        distance=distance,
        retag=retag,
    )
    base = text.rstrip("\n")
    if not base.endswith("---"):
        base += "\n\n---"
    candidate = f"{base}\n\n{block}"

    # Read back what we are about to write, through the parser that will read it
    # for real. Two things have to hold: the new body survives byte-for-byte, and
    # no existing entry changed shape because of the append.
    after_entries, after_malformed = mirror.parse_examples(candidate)
    written = next((e for e in after_entries if e.get("id") == corpus_id), None)
    if written is None:
        raise QueueError("corpus:round_trip", f"appended entry `{corpus_id}` does not parse back")
    if written.get("body") != corpus_body:
        raise QueueError("corpus:round_trip", f"appended body for `{corpus_id}` did not survive")
    if after_malformed != before_malformed:
        raise QueueError("corpus:round_trip", "the append changed how existing entries parse")
    if [e.get("id") for e in after_entries[:-1]] != [e.get("id") for e in before_entries]:
        raise QueueError("corpus:round_trip", "the append disturbed the existing entry list")
    for old, new in zip(before_entries, after_entries):
        if old.get("body") != new.get("body"):
            raise QueueError("corpus:round_trip", f"the append altered entry `{old.get('id')}`")

    CORPUS.parent.mkdir(parents=True, exist_ok=True)
    tmp = CORPUS.with_name(CORPUS.name + ".tmp")
    tmp.write_text(candidate, encoding="utf-8")
    os.replace(tmp, CORPUS)
    return {
        "appended": True,
        "corpus_id": corpus_id,
        "retag_pending": retag,
        "corpus_path": str(CORPUS),
    }


# --- clipboard + editor -----------------------------------------------------


def to_clipboard(text: str) -> bool:
    """Put the body on the system clipboard. False when no clipboard tool works.

    Output is captured rather than inherited: a failing `xclip` or `wl-copy`
    otherwise prints its diagnostics into the middle of a rendered review card.
    """
    for command in CLIPBOARD_COMMANDS:
        try:
            done = subprocess.run(
                command, input=text.encode("utf-8"), timeout=10, check=False, capture_output=True
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if done.returncode == 0:
            return True
    return False


def edit_in_editor(body: str) -> str:
    """Open the body in $EDITOR and return what came back.

    The temp file holds the body and nothing else — an instruction header would
    have to be stripped afterwards, and anything a stripper misses is a line the
    operator publishes by accident.

    $EDITOR must block until the editor exits. A detaching editor (`code` or
    `subl` without `-w`, `open`) returns immediately and the temp file is gone
    before any typing lands; the caller compares the result and says so rather
    than treating the unchanged body as a decision.
    """
    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL") or "vi"
    try:
        command = shlex.split(editor)
    except ValueError as exc:
        raise QueueError("editor:unusable", f"cannot parse $EDITOR: {exc}") from exc
    if not command:
        raise QueueError("editor:unusable", "$EDITOR is empty")

    handle, name = tempfile.mkstemp(prefix="x-comms-", suffix=".txt")
    tmp = Path(name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(body + "\n")
        try:
            subprocess.run(command + [str(tmp)], check=False)
        except OSError as exc:
            raise QueueError("editor:unusable", f"cannot run `{editor}`: {exc.strerror}") from exc
        try:
            return tmp.read_text(encoding="utf-8").strip("\n")
        except (OSError, UnicodeDecodeError) as exc:
            raise QueueError("editor:unreadable", f"cannot read the edited body: {exc}") from exc
    finally:
        tmp.unlink(missing_ok=True)


def check_publishable(body: str) -> None:
    """The gates a body must clear before it can be approved.

    Same three `add` applies, re-applied here because an edited body is a body
    `add` never saw: non-empty, within the ceiling, and clear of the D6 gate. The
    full gate runs — including the operator denylist — because unlike `seed_ref`
    this text is going to X.
    """
    if not body.strip():
        raise QueueError("input:empty_body", "body is empty")
    if len(body) > MAX_BODY_CHARS:
        raise QueueError(
            "len:over_280", f"body is {len(body)} chars, over the {MAX_BODY_CHARS} limit"
        )
    leak = scan_for_leaks(body)
    if leak:
        raise QueueError(leak[0], f"blocked by {leak[1]}")


# --- subcommand: add --------------------------------------------------------


def resolve_body(args) -> str:
    provided = [bool(args.body), bool(args.body_file), bool(args.body_stdin)]
    if sum(provided) != 1:
        raise QueueError(
            "input:body_source",
            "exactly one of --body, --body-file, --body-stdin is required",
        )
    if args.body:
        return args.body
    if args.body_file:
        try:
            return Path(args.body_file).expanduser().read_text(encoding="utf-8")
        except OSError as exc:
            raise QueueError("input:body_file", f"cannot read body file: {exc}") from exc
    return sys.stdin.read()


def resolve_tags(args) -> dict[str, str]:
    tags: dict[str, str] = {}
    if args.tags_json:
        try:
            loaded = json.loads(args.tags_json)
        except json.JSONDecodeError as exc:
            raise QueueError("input:tags_json", f"--tags-json is not valid JSON: {exc}") from exc
        if not isinstance(loaded, dict):
            raise QueueError("input:tags_json", "--tags-json must be a JSON object")
        tags.update({str(k): str(v) for k, v in loaded.items()})
    for pair in args.tag or []:
        key, sep, value = pair.partition("=")
        if not sep:
            raise QueueError("input:tag", f"--tag expects key=value, got {pair!r}")
        tags[key.strip()] = value.strip()
    return tags


def allocate_entry(queue_dir: Path, created_at: datetime) -> tuple[str, Path, datetime]:
    """Return (id, path, created_at), stepping a second on filename collision.

    The archive counts as taken. An id is only unique per second-of-day, so a
    tick that drafts into the same second an earlier entry was created will reuse
    the id once that earlier entry has been archived — and then `archive_entry`
    silently overwrites the older record, while `check_not_archived` reads the
    stale archive file as evidence that the *new* entry was raced and refuses to
    approve it. Both disappear if an archived id is never handed out twice.
    """
    while True:
        entry_id = "q_" + created_at.strftime("%Y-%m-%d_%H%M%S")
        path = queue_dir / f"{entry_id}.md"
        if not path.exists() and not (archive_dir(queue_dir) / path.name).exists():
            return entry_id, path, created_at
        created_at += timedelta(seconds=1)


def cmd_add(args) -> int:
    queue_dir = resolve_queue_dir(args.queue_dir)
    body = resolve_body(args).strip("\n")

    if not body.strip():
        raise QueueError("input:empty_body", "body is empty")
    if len(body) > MAX_BODY_CHARS:
        raise QueueError(
            "len:over_280", f"body is {len(body)} chars, over the {MAX_BODY_CHARS} limit"
        )

    seed_ref = args.seed_ref.strip()
    # The body is the only text that ever reaches X, so it gets the full gate.
    # seed_ref is a verbatim SESSION_INDEX row that never leaves the private queue
    # file and is never copied to the clipboard — it is *expected* to name private
    # repos and internal work, so running the operator denylist over it rejects
    # legitimate seeds wholesale (measured against the last 200 index rows: 76%).
    # It still gets the shape gate, so an `op://` reference, an absolute path or a
    # tailnet address can never be written into a Drive-synced file.
    leak = scan_for_leaks(body)
    if leak is None:
        leak = scan_for_leaks(seed_ref, private_terms=False)
    if leak:
        raise QueueError(leak[0], f"blocked by {leak[1]}")

    tags = resolve_tags(args)
    missing = [axis for axis in TAG_AXES if not tags.get(axis)]
    if missing:
        raise QueueError("schema:tags_missing", f"corpus_tags missing: {', '.join(missing)}")

    queue_dir.mkdir(parents=True, exist_ok=True)
    created_at = datetime.now(TZ).replace(microsecond=0)
    entry_id, path, created_at = allocate_entry(queue_dir, created_at)

    fields = {
        "id": entry_id,
        "created_at": created_at.isoformat(timespec="seconds"),
        "drafted_by": args.drafted_by,
        "source": args.source,
        "seed_key": seed_key_for(seed_ref),
        "seed_ref": seed_ref,
        "pillar": args.pillar,
        "status": "queued",
        "decision_at": None,
        "edit_distance": None,
        "posted_at": None,
        "body_chars": len(body),
        "arc_id": args.arc_id,
        "arc_pos": args.arc_pos,
        "arc_of": args.arc_of,
        "arc_note": args.arc_note,
        # Frozen here and never rewritten: the anchor edit_distance is measured against.
        "body_drafted": body,
        "corpus_tags": tags,
    }

    vocab = load_tag_vocabulary()
    reject_multiline_scalars(fields)
    problems = validate_fields(fields, body, vocab)
    if problems:
        raise QueueError("schema:invalid", "; ".join(problems))

    # Validate the bytes, not just the in-memory dict: the file is the contract
    # every later commit reads, so it has to parse back to what we meant.
    rendered = render_entry(fields, body)
    round_tripped = validate_rendered(rendered, vocab)
    if round_tripped:
        raise QueueError("schema:round_trip", "; ".join(round_tripped))

    # Ledger before the entry becomes visible: a ledger write that fails must
    # not leave a queued entry with no `drafted` line, which is the hole an
    # anti-re-emission contract cannot have.
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(rendered, encoding="utf-8")
    try:
        append_ledger(queue_dir, ledger_event(entry_id, fields["seed_key"], "drafted"))
    except OSError:
        tmp.unlink(missing_ok=True)
        raise
    os.replace(tmp, path)

    print(
        json.dumps(
            {
                "status": "added",
                "id": entry_id,
                "path": str(path),
                "body_chars": len(body),
                "seed_key": fields["seed_key"],
            },
            ensure_ascii=False,
        )
    )
    return 0


# --- subcommand: validate ---------------------------------------------------


def cmd_validate(args) -> int:
    queue_dir = resolve_queue_dir(args.queue_dir)
    vocab = load_tag_vocabulary()
    paths = entry_paths(queue_dir)
    problems: list[dict] = []
    queued = 0

    for path in paths:
        try:
            fields, body = parse_entry(path)
        except QueueError as exc:
            problems.append({"entry": path.name, "problems": [exc.message]})
            continue
        found = validate_fields(fields, body, vocab)
        if fields.get("id") and fields["id"] != path.stem:
            found.append(f"id `{fields['id']}` does not match filename `{path.stem}`")
        if fields.get("status") == "queued":
            queued += 1
        elif fields.get("status") in TERMINAL_STATUSES:
            # D3: the queue dir holds actionable entries only. A terminal entry
            # still here means an archive move failed — expire will not touch it
            # (queued-only), so nothing else would ever notice.
            found.append(f"status `{fields['status']}` is terminal but the entry is not archived")
        if found:
            problems.append({"entry": path.name, "problems": found})

    # Torn lines are tolerated; an unreadable ledger is a queue health failure,
    # because every downstream dedup decision depends on being able to read it.
    ledger_readable = True
    try:
        _, torn = read_ledger(queue_dir, strict=True)
    except LedgerUnreadable as exc:
        ledger_readable = False
        _, torn = read_ledger(queue_dir)  # tolerant re-read, just for the count
        problems.append({"entry": LEDGER_NAME, "problems": [f"ledger unreadable: {exc}"]})

    report = {
        "status": "ok" if not problems else "invalid",
        "queue_dir": str(queue_dir),
        "queue_exists": queue_dir.is_dir(),
        "entries": len(paths),
        "queued": queued,
        "ledger_readable": ledger_readable,
        "ledger_torn_lines": torn,
        "tag_vocabulary_loaded": bool(vocab),
        "private_terms_loaded": PRIVATE_TERMS.exists(),
        "problems": problems,
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if not problems else 1


# --- subcommand: expire -----------------------------------------------------


def cmd_expire(args) -> int:
    """Archive queued entries that are too old or over capacity.

    Only `status: queued` entries are counted and only queued entries are moved
    — a terminal entry is the deciding path's to archive, so this stays the
    single mover for expiry and never races a decision mid-write.
    """
    queue_dir = resolve_queue_dir(args.queue_dir)
    now = datetime.now(TZ)
    cutoff = now - timedelta(days=args.max_age_days)

    candidates = []
    unparseable = []
    for path in entry_paths(queue_dir):
        try:
            fields, _ = parse_entry(path)
        except QueueError as exc:
            unparseable.append({"entry": path.name, "problem": exc.message})
            continue
        if fields.get("status") != "queued":
            continue
        created = parse_ts(fields.get("created_at", "")) or now
        candidates.append((created, path, fields))

    candidates.sort(key=lambda item: item[0])  # oldest first

    doomed: list[tuple[Path, dict, str]] = []
    surviving = []
    for created, path, fields in candidates:
        if created < cutoff:
            doomed.append((path, fields, "age"))
        else:
            surviving.append((path, fields))
    if len(surviving) > args.capacity:
        overflow = surviving[: len(surviving) - args.capacity]
        doomed.extend((path, fields, "capacity") for path, fields in overflow)

    expired = []
    if not args.dry_run and doomed:
        archive_dir(queue_dir).mkdir(parents=True, exist_ok=True)

    skipped = []
    for path, fields, reason in doomed:
        if args.dry_run:
            expired.append({"id": fields.get("id"), "reason": reason, "moved": False})
            continue
        try:
            # Re-render from the parsed fields rather than rewriting raw text:
            # a status line is a field, not a string match, and this is the one
            # place the entry can be stamped with when it left the queue (D11).
            _, body = parse_entry(path)
            fields["status"] = "expired"
            fields["decision_at"] = now.isoformat(timespec="seconds")
            target = archive_dir(queue_dir) / path.name
            write_entry_atomic(target, render_entry(fields, body))
            path.unlink()
        except (OSError, QueueError) as exc:
            # A decision path may have archived this entry between the scan and
            # here. Losing one entry from the pass beats aborting the pass.
            detail = exc.strerror if isinstance(exc, OSError) else exc.reason_code
            skipped.append({"id": fields.get("id"), "reason": reason, "problem": detail})
            continue
        append_ledger(
            queue_dir,
            ledger_event(fields.get("id", path.stem), fields.get("seed_key", ""), "expired"),
        )
        expired.append({"id": fields.get("id"), "reason": reason, "moved": True})

    print(
        json.dumps(
            {
                "status": "ok",
                "queue_dir": str(queue_dir),
                "queued_before": len(candidates),
                "expired": expired,
                "skipped": skipped,
                # On a dry run this is the projection, not the current count.
                "queued_after": len(candidates) - len(expired),
                "unparseable": unparseable,
                "dry_run": args.dry_run,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


# --- transitions ------------------------------------------------------------
# One implementation per transition, called by both the scriptable subcommands and
# the interactive loop. Each one re-reads the entry off disk first: `expire` runs
# over the same directory from a launchd tick and may have archived it since.
#
# All three append their ledger line *after* the state change, the opposite of
# `cmd_add`, which ledgers first so a queued entry can never exist without its
# `drafted` event. The asymmetry is deliberate: `drafted` IS the anti-re-emission
# key, and mine.py dedups on any event carrying that seed_key, so a lost
# `approved`/`killed`/`posted` line costs a D11 measurement, not a re-emitted
# seed. Ledgering first here would instead record decisions that never happened.


def transition_approve(
    queue_dir: Path,
    entry_id: str,
    new_body: str | None,
    vocab: dict[str, tuple[str, ...]],
    now: datetime,
) -> dict:
    """queued -> approved: measure the edit, feed the corpus, flip the entry.

    Order matters in both directions and neither is free:

    * The corpus append must not come *after* the flip. An approved entry whose
      body never reached the corpus is silent starvation of the one loop that
      teaches the engine the operator's voice (D5), and nothing downstream would
      notice.
    * It must not come before a writer that can still reject either — the corpus
      is append-only, so a failure downstream of it permanently records a body
      that was never approved. `save_entry` can refuse for three separate reasons
      (unreadable tag vocabulary, a template edit that retired a tag value, an I/O
      error on a cloud-synced directory), and all three are reachable.

    So the entry is *staged* first — every check run, bytes on disk in a temp
    file — then the corpus is appended, then `os.replace` publishes the flip.
    What is left downstream of the irreversible write is one atomic rename.
    """
    path, fields, body = load_entry(queue_dir, entry_id)
    if fields.get("status") != "queued":
        raise QueueError(
            "state:not_queued", f"`{entry_id}` is `{fields.get('status')}`, not queued"
        )
    if new_body is not None:
        body = new_body.strip("\n")
    check_publishable(body)

    drafted = fields.get("body_drafted", "")
    distance = edit_distance(drafted, body)
    retag = needs_retag(distance, drafted)

    fields["status"] = "approved"
    fields["decision_at"] = now.isoformat(timespec="seconds")
    fields["edit_distance"] = distance
    staged = stage_entry(path, fields, body, vocab)
    try:
        # `expire` is a second mover over this directory and runs on every launchd
        # tick — checked here to keep the window small, and again after the rename.
        check_not_archived(queue_dir, path)
        corpus = append_to_corpus(
            entry_id, fields.get("corpus_tags", {}), body, distance, retag=retag, when=now
        )
    except Exception:
        staged.unlink(missing_ok=True)
        raise
    os.replace(staged, path)
    try:
        check_not_archived(queue_dir, path)
    except QueueError:
        # `expire` archived this entry while the corpus append was running, and the
        # rename above just re-created it in the queue. Undo our half rather than
        # leave one id living in two files with contradicting statuses. The corpus
        # row stays: it records a body the operator did approve.
        path.unlink(missing_ok=True)
        raise
    append_ledger(
        queue_dir,
        ledger_event(entry_id, fields.get("seed_key", ""), "approved", edit_distance=distance),
    )
    return {
        "id": entry_id,
        "status": "approved",
        "edit_distance": distance,
        "body_chars": len(body),
        "retag_pending": retag,
        "corpus": corpus,
    }


def transition_kill(
    queue_dir: Path, entry_id: str, vocab: dict[str, tuple[str, ...]], now: datetime
) -> dict:
    """Archive an entry the operator does not want.

    Allowed from `approved` as well as `queued`. D3 lists only the queued arrow,
    but an approved entry is never touched by `expire` (queued-only, single mover),
    so without this it could never leave the queue directory at all. An already-
    appended corpus row is left alone: it records a body the operator did approve,
    which is exactly what the corpus is for.

    Arc siblings are deliberately untouched — no renumbering, no `arc_of` rewrite.
    D15's rule is that every member stands alone, so a gap in the positions is
    information (the operator dropped one), not damage.
    """
    path, fields, body = load_entry(queue_dir, entry_id)
    status = fields.get("status")
    if status not in ACTIONABLE_STATUSES:
        raise QueueError("state:not_actionable", f"`{entry_id}` is `{status}`")
    fields["status"] = "killed"
    fields["decision_at"] = now.isoformat(timespec="seconds")
    destination = archive_entry(queue_dir, path, fields, body, vocab)
    append_ledger(queue_dir, ledger_event(entry_id, fields.get("seed_key", ""), "killed"))
    return {"id": entry_id, "status": "killed", "archived_to": str(destination)}


def transition_copy(
    queue_dir: Path,
    entry_id: str,
    vocab: dict[str, tuple[str, ...]],
    now: datetime,
    *,
    new_body: str | None = None,
    clipboard: bool = True,
) -> dict:
    """Hand the body to the operator and close the entry out as posted.

    Copy on a still-queued entry implies approve (F8) — otherwise the one action
    the operator actually performs every time would be the one that bypasses the
    corpus loop. The approve half runs first and the clipboard second, so a
    refused approval never leaves a body on the clipboard that the queue then
    disagrees about.

    `new_body` carries an edit the operator made but has not applied yet. Without
    it, copying after an edit publishes whatever is still on disk — a different
    body than the one on screen. It is only accepted while the entry is queued:
    once approved, the corpus already records the earlier body and quietly
    posting a different one would put the two permanently out of step.

    The clipboard is best-effort and the returned dict always carries the body,
    so a machine with no working clipboard tool (a headless shell, an SSH session
    with no DISPLAY, a sandboxed `pbcopy`) leaves the operator with the text
    rather than an archived entry and nothing to paste.
    """
    path, fields, body = load_entry(queue_dir, entry_id)
    status = fields.get("status")
    if status not in ACTIONABLE_STATUSES:
        raise QueueError("state:not_actionable", f"`{entry_id}` is `{status}`")
    if new_body is not None and new_body.strip("\n") != body and status != "queued":
        raise QueueError(
            "state:already_approved",
            f"`{entry_id}` is already approved — its corpus row records the earlier body",
        )

    approved = None
    if status == "queued":
        approved = transition_approve(queue_dir, entry_id, new_body, vocab, now)
        path, fields, body = load_entry(queue_dir, entry_id)

    copied = to_clipboard(body) if clipboard else False
    if clipboard and not copied:
        print(
            "queue.py: no working clipboard tool — the body is in this output under `body`",
            file=sys.stderr,
        )

    fields["status"] = "posted"
    fields["posted_at"] = now.isoformat(timespec="seconds")
    if not fields.get("decision_at"):
        fields["decision_at"] = now.isoformat(timespec="seconds")
    destination = archive_entry(queue_dir, path, fields, body, vocab)
    append_ledger(queue_dir, ledger_event(entry_id, fields.get("seed_key", ""), "posted"))
    return {
        "id": entry_id,
        "status": "posted",
        "clipboard": copied,
        "approved_now": approved,
        "archived_to": str(destination),
        "body_chars": len(body),
        "body": body,
    }


# --- queue views ------------------------------------------------------------


def arc_position(fields: dict) -> int:
    raw = str(fields.get("arc_pos") or "")
    return int(raw) if raw.isdigit() else 0


def arc_siblings(queue_dir: Path, arc_id: str) -> list[dict]:
    """Every member of an arc, queued or archived, ordered by arc_pos (D15)."""
    found = []
    for path in all_entry_paths(queue_dir):
        try:
            fields, _ = parse_entry(path)
        except QueueError:
            continue
        if fields.get("arc_id") == arc_id:
            found.append(fields)
    found.sort(key=arc_position)
    return found


def ordered_actionable(queue_dir: Path) -> tuple[list[tuple[Path, dict, str]], list[dict]]:
    """Actionable entries in review order, plus whatever would not parse.

    Order: oldest first, except that arc members are kept together and sorted by
    arc_pos, so the operator reads a week's arc in the order it was written rather
    than interleaved with unrelated singles.
    """
    items: list[tuple[Path, dict, str]] = []
    unreadable: list[dict] = []
    for path in entry_paths(queue_dir):
        try:
            fields, body = parse_entry(path)
        except QueueError as exc:
            unreadable.append({"entry": path.name, "problem": exc.message})
            continue
        if fields.get("id") != path.stem:
            # Every transition resolves an entry by id, so a card rendered from a
            # file whose id points elsewhere would act on a different entry than
            # the operator is reading. `--validate` reports this; review refuses it.
            unreadable.append(
                {"entry": path.name, "problem": "frontmatter id does not match the filename"}
            )
            continue
        if fields.get("status") in ACTIONABLE_STATUSES:
            items.append((path, fields, body))

    floor = datetime.min.replace(tzinfo=TZ)

    def created(item) -> datetime:
        return parse_ts(item[1].get("created_at", "")) or floor

    arc_start: dict[str, datetime] = {}
    for item in items:
        arc = item[1].get("arc_id")
        if arc:
            arc_start[arc] = min(arc_start.get(arc, created(item)), created(item))

    def sort_key(item):
        arc = item[1].get("arc_id") or ""
        return (arc_start.get(arc, created(item)), arc, arc_position(item[1]), item[0].name)

    items.sort(key=sort_key)
    return items, unreadable


def days_in_queue(fields: dict, now: datetime) -> int | None:
    """Whole days since the entry was created — D11's derived field.

    Clamped at zero: `allocate_entry` steps created_at forward a second whenever
    several entries land inside one tick, so the newest member of a batch can
    carry a timestamp a second or two ahead of the clock. `timedelta.days` floors
    toward negative infinity, which turns that into a "-1d in queue" card.
    """
    created = parse_ts(fields.get("created_at", ""))
    if created is None:
        return None
    return max(0, (now - created).days)


def as_int(value):
    """Numeric field as a JSON number, or None. Entry fields are all strings."""
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def entry_summary(fields: dict, body: str, now: datetime, *, with_body: bool = False) -> dict:
    row = {
        key: (fields.get(key) or None)
        for key in (
            "id",
            "status",
            "source",
            "pillar",
            "created_at",
            "decision_at",
            "posted_at",
        )
    }
    # Numbers come out of the entry file as strings. This view is documented as
    # machine-readable, so a consumer comparing arc_pos or summing body_chars
    # should not have to know that.
    for key in ("edit_distance", "body_chars"):
        row[key] = as_int(fields.get(key))
    # D11 names days_in_queue as derived, never stored.
    row["days_in_queue"] = days_in_queue(fields, now)
    for key in ARC_FIELDS:
        if fields.get(key):
            row[key] = as_int(fields[key]) if key in ("arc_pos", "arc_of") else fields[key]
    if with_body:
        row["body"] = body
    return row


def cmd_list(args) -> int:
    queue_dir = resolve_queue_dir(args.queue_dir)
    now = datetime.now(TZ)
    paths = all_entry_paths(queue_dir) if args.all else entry_paths(queue_dir)
    rows, unreadable = [], []
    counts: dict[str, int] = {}
    for path in paths:
        try:
            fields, body = parse_entry(path)
        except QueueError as exc:
            unreadable.append({"entry": path.name, "problem": exc.message})
            continue
        status = fields.get("status", "?")
        if not args.all and status not in ACTIONABLE_STATUSES:
            continue
        counts[status] = counts.get(status, 0) + 1
        rows.append(entry_summary(fields, body, now, with_body=args.with_body))
    print(
        json.dumps(
            {
                "status": "ok",
                "queue_dir": str(queue_dir),
                "counts": counts,
                "entries": rows,
                "unreadable": unreadable,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


# --- subcommand: review -----------------------------------------------------

RULE = "=" * 72
THIN = "-" * 72
PROMPT = "  [a]pprove  [e]dit  [k]ill  [c]opy  [s]kip  [q]uit > "


def render_card(queue_dir: Path, fields: dict, body: str, position: str, now: datetime) -> str:
    days = days_in_queue(fields, now)
    age = "age unknown" if days is None else f"{days}d in queue"
    # Counted from the body being shown, not from the stored field: after an edit
    # the two differ, and on a 280-character surface that is the one number that
    # must never be stale.
    lines = [
        RULE,
        f"{position}  {fields.get('id')}   {fields.get('status')}   {age}",
        f"      {fields.get('pillar')} · source {fields.get('source')} · {len(body)} chars",
    ]
    if fields.get("edit_distance") not in (None, ""):
        lines.append(f"      edit_distance {fields['edit_distance']} vs the drafted body")

    arc = fields.get("arc_id")
    if arc:
        note = fields.get("arc_note")
        lines.append("")
        lines.append(f"      arc {arc}" + (f" — {note}" if note else ""))
        for sibling in arc_siblings(queue_dir, arc):
            marker = "->" if sibling.get("id") == fields.get("id") else "  "
            lines.append(
                f"      {marker} {arc_position(sibling)}/{sibling.get('arc_of') or '?'}  "
                f"{sibling.get('id')}  {sibling.get('status')}"
            )
        lines.append("      Every member stands alone; killing one leaves the rest intact.")

    lines.extend([THIN, body, THIN])
    return "\n".join(lines)


def cmd_review(args) -> int:
    """The operator's one-action loop over the queue.

    Every state change delegates to the transition functions above, so the
    interactive path cannot acquire semantics the scriptable path lacks.
    """
    if not sys.stdin.isatty():
        raise QueueError(
            "input:not_a_tty", "review needs a terminal — use `list`, `approve`, `kill` or `copy`"
        )
    queue_dir = resolve_queue_dir(args.queue_dir)
    vocab = load_tag_vocabulary()
    items, unreadable = ordered_actionable(queue_dir)

    for problem in unreadable:
        print(f"! {problem['entry']}: {problem['problem']}", file=sys.stderr)
    if not items:
        print(json.dumps({"status": "ok", "reviewed": 0, "actions": [], "unreadable": unreadable}))
        return 0

    actions: list[dict] = []
    quit_early = False
    for index, (_, fields, body) in enumerate(items, start=1):
        entry_id = str(fields.get("id", ""))
        working = body
        while True:
            now = datetime.now(TZ).replace(microsecond=0)
            print(render_card(queue_dir, fields, working, f"[{index}/{len(items)}]", now))
            try:
                choice = input(PROMPT).strip().lower()[:1]
            except (EOFError, KeyboardInterrupt):
                print()
                quit_early = True
                break

            if choice == "q":
                quit_early = True
                break
            if choice == "s" or not choice:
                actions.append({"id": entry_id, "action": "skip"})
                break

            if choice == "e":
                before_edit = working
                try:
                    working = edit_in_editor(working)
                    check_publishable(working)
                except QueueError as exc:
                    # Keep the rejected text as the starting point: making the
                    # operator retype an edit because a gate fired is how a gate
                    # teaches people to work around it.
                    print(f"  edit rejected: {exc.reason_code} — {exc.message}")
                    continue
                if working == before_edit:
                    # A non-blocking $EDITOR (`code` or `subl` without -w, `open`)
                    # returns before the operator has typed anything, and the temp
                    # file is gone by then. Say so rather than approve the original
                    # as though it were a decision.
                    print("  nothing changed — if your editor detaches, add its wait flag")
                choice = "a"  # D4: edit means edit-then-approve

            try:
                pending = working if working != body else None
                if choice == "a":
                    result = transition_approve(queue_dir, entry_id, pending, vocab, now)
                elif choice == "k":
                    # An unapplied edit is irrelevant here — kill discards the body.
                    result = transition_kill(queue_dir, entry_id, vocab, now)
                elif choice == "c":
                    result = transition_copy(queue_dir, entry_id, vocab, now, new_body=pending)
                else:
                    print("  unrecognised — a, e, k, c, s or q")
                    continue
            except QueueError as exc:
                print(f"  {exc.reason_code}: {exc.message}")
                actions.append({"id": entry_id, "action": choice, "error": exc.reason_code})
                break

            summary = {"id": entry_id, "action": choice, **result}
            actions.append(summary)
            if choice == "a":
                print(f"  approved · edit_distance {result['edit_distance']}", end="")
                print(" · retag pending" if result["retag_pending"] else "")
                if not result["corpus"]["appended"]:
                    print("  corpus row already present — not appended twice")
            elif choice == "k":
                print("  killed and archived")
            elif choice == "c":
                print("  copied to the clipboard" if result["clipboard"] else "  no clipboard tool")
                print("  posted and archived — paste it into your X scheduler")
            break
        if quit_early:
            break

    print(
        json.dumps(
            {
                "status": "ok",
                "reviewed": len(actions),
                "actions": actions,
                "unreadable": unreadable,
                "quit_early": quit_early,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


# --- subcommands: approve / kill / copy --------------------------------------


def cmd_approve(args) -> int:
    queue_dir = resolve_queue_dir(args.queue_dir)
    new_body = None
    if args.body is not None and args.body_file is not None:
        raise QueueError("input:body_source", "pass at most one of --body, --body-file")
    if args.body is not None:
        new_body = args.body
    elif args.body_file is not None:
        try:
            new_body = Path(args.body_file).expanduser().read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise QueueError("input:body_file", f"cannot read body file: {exc}") from exc
    result = transition_approve(
        queue_dir, args.id, new_body, load_tag_vocabulary(), datetime.now(TZ).replace(microsecond=0)
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def cmd_kill(args) -> int:
    queue_dir = resolve_queue_dir(args.queue_dir)
    result = transition_kill(
        queue_dir, args.id, load_tag_vocabulary(), datetime.now(TZ).replace(microsecond=0)
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def cmd_copy(args) -> int:
    queue_dir = resolve_queue_dir(args.queue_dir)
    result = transition_copy(
        queue_dir,
        args.id,
        load_tag_vocabulary(),
        datetime.now(TZ).replace(microsecond=0),
        clipboard=not args.no_clipboard,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


# --- cli --------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument(
        "--validate",
        action="store_true",
        help="validate every queue entry; exit 0 on an empty or valid queue",
    )
    parser.add_argument("--queue-dir", help="override the queue directory (testing)")
    sub = parser.add_subparsers(dest="command")

    add = sub.add_parser("add", help="add a drafted entry to the queue")
    add.add_argument("--body", help="post body as a literal string")
    add.add_argument("--body-file", help="read the post body from a file")
    add.add_argument("--body-stdin", action="store_true", help="read the post body from stdin")
    add.add_argument("--source", required=True, choices=SOURCES)
    add.add_argument("--seed-ref", required=True, help="verbatim seed reference")
    add.add_argument("--pillar", required=True, choices=PILLARS)
    add.add_argument("--drafted-by", default="x-comms-engine/1.0", help="engine identifier")
    add.add_argument("--tags-json", help="corpus_tags as a JSON object")
    add.add_argument("--tag", action="append", help="corpus_tags entry as key=value (repeatable)")
    add.add_argument("--arc-id")
    add.add_argument("--arc-pos")
    add.add_argument("--arc-of")
    add.add_argument("--arc-note")
    # SUPPRESS so an unset subcommand flag does not clobber the top-level value.
    add.add_argument(
        "--queue-dir", default=argparse.SUPPRESS, help="override the queue directory (testing)"
    )
    add.set_defaults(func=cmd_add)

    expire = sub.add_parser("expire", help="archive aged or over-capacity queued entries")
    expire.add_argument("--max-age-days", type=int, default=DEFAULT_MAX_AGE_DAYS)
    expire.add_argument("--capacity", type=int, default=DEFAULT_CAPACITY)
    expire.add_argument("--dry-run", action="store_true")
    expire.add_argument(
        "--queue-dir", default=argparse.SUPPRESS, help="override the queue directory (testing)"
    )
    expire.set_defaults(func=cmd_expire)

    def with_queue_dir(sub_parser):
        # SUPPRESS so an unset subcommand flag does not clobber the top-level value.
        sub_parser.add_argument(
            "--queue-dir", default=argparse.SUPPRESS, help="override the queue directory (testing)"
        )
        return sub_parser

    listing = with_queue_dir(sub.add_parser("list", help="machine-readable view of the queue"))
    listing.add_argument(
        "--all", action="store_true", help="include archived entries and every status"
    )
    listing.add_argument("--with-body", action="store_true", help="include each entry's body")
    listing.set_defaults(func=cmd_list)

    review = with_queue_dir(sub.add_parser("review", help="interactive one-action review loop"))
    review.set_defaults(func=cmd_review)

    approve = with_queue_dir(sub.add_parser("approve", help="approve a queued entry"))
    approve.add_argument("id", help="queue entry id, e.g. q_2026-08-26_073104")
    approve.add_argument("--body", help="replacement body (edit-then-approve)")
    approve.add_argument("--body-file", help="read the replacement body from a file")
    approve.set_defaults(func=cmd_approve)

    kill = with_queue_dir(sub.add_parser("kill", help="archive an entry without posting it"))
    kill.add_argument("id", help="queue entry id")
    kill.set_defaults(func=cmd_kill)

    copy = with_queue_dir(sub.add_parser("copy", help="copy the body, stamp posted, archive"))
    copy.add_argument("id", help="queue entry id")
    copy.add_argument(
        "--no-clipboard", action="store_true", help="skip the clipboard (testing)"
    )
    copy.set_defaults(func=cmd_copy)

    return parser


def reject(reason_code: str, detail: str) -> int:
    """Emit a reason-coded, body-free rejection and return the failure code."""
    print(f"queue.py: rejected reason={reason_code} detail={detail}", file=sys.stderr)
    print(json.dumps({"status": "rejected", "reason_code": reason_code}, ensure_ascii=False))
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        if not args.validate:
            parser.print_help()
            return 2
        return cmd_validate(args)

    try:
        return args.func(args)
    except QueueError as exc:
        return reject(exc.reason_code, exc.message)
    except OSError as exc:  # noqa: BLE001 — a traceback here would print the
        # absolute queue path into the tick log; D9 keeps that log reason-coded.
        target = Path(exc.filename).name if exc.filename else "?"
        return reject("io:error", f"{exc.strerror} on {target}")


if __name__ == "__main__":
    sys.exit(main())
