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

`review` and `list` are a later commit and deliberately absent here.

The entry schema is the drafting engine's contract: every field the engine
writes is written by this helper, and `--validate` is the only thing that gets
to say an entry is well-formed. `body_drafted` freezes the engine's original
body at add time — it is the anchor edit_distance is later measured against, so
nothing in this file ever rewrites it.

Ledger concurrency: writers append one whole line via a single O_APPEND write,
which is what keeps two ticks from interleaving mid-line. Readers tolerate a
torn tail line and report it rather than crashing; callers that must not act on
a partial view (the miner's dedup pass) use `read_ledger(strict=True)` and fail
closed on an unreadable ledger.

Stdout is JSON on every path. Rejections additionally write a reason-coded,
body-free line to stderr so a launchd tick log records *why* a draft was
dropped without ever recording the draft.

NAME HAZARD — this file shadows the stdlib `queue` module. Any script run from
this directory gets it at `sys.path[0]`, so a sibling helper doing `import queue`
lands here. `concurrent.futures.thread` imports stdlib `queue` internally, so a
thread pool in a sibling helper dies with a confusing `module 'queue' has no
attribute 'SimpleQueue'`. `subprocess.run(..., timeout=...)` is unaffected and is
the right tool for a headless call. The filename is fixed by the queue contract.

Smoke tests:
    python3 queue.py --validate
    python3 queue.py add --source manual --pillar P1 --seed-ref "2026-08-25 - x" \\
        --tags-json '{"tone_register": "clinical-peer", ...}' --body "hello"
    python3 queue.py expire --max-age-days 14 --capacity 10
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

NOTES_BASE = Path(
    os.environ.get("SESSION_PUBLISHER_NOTES_DIR", str(Path.home() / "personal-notes"))
)
QUEUE_DIR = NOTES_BASE / "posts" / "x" / "queue"
TZ = ZoneInfo(os.environ.get("SESSION_PUBLISHER_TZ", "UTC"))

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
EXAMPLES_TEMPLATE = PROMPTS_DIR / "examples-template.md"
PRIVATE_TERMS = PROMPTS_DIR / "private-terms.local.md"

LEDGER_NAME = ".ledger.jsonl"
ARCHIVE_NAME = ".archive"
ENTRY_GLOB = "q_*.md"

MAX_BODY_CHARS = 280
DEFAULT_CAPACITY = 10
DEFAULT_MAX_AGE_DAYS = 14

SOURCES = ("miner", "backlog", "voice", "manual")
PILLARS = ("P1", "P2", "P3", "P4")
STATUSES = ("queued", "approved", "posted", "killed", "expired")
TERMINAL_STATUSES = ("posted", "killed", "expired")
LEDGER_EVENTS = ("drafted", "approved", "posted", "killed", "expired")

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
    """Return (id, path, created_at), stepping a second on filename collision."""
    while True:
        entry_id = "q_" + created_at.strftime("%Y-%m-%d_%H%M%S")
        path = queue_dir / f"{entry_id}.md"
        if not path.exists():
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
        "seed_key": hashlib.sha1(seed_ref.encode("utf-8")).hexdigest(),
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
