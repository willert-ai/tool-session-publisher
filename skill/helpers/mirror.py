#!/usr/bin/env python3
"""
mirror.py — load examples corpus for Stage 5.5 (style-applied variants).

Reads <skill>/prompts/examples.local.md, parses entries into JSON,
applies the only deterministic filter the SPEC asserts as mechanical:
drop entries marked `near_duplicate_of: <id>` (operator-asserted
cluster non-representatives).

This helper is intentionally NOT a scorer. SPEC v0.2 §1 originally
called for stdlib tag-overlap math; Phase C overrides that decision
(annotated in the SPEC) because Phase B's "Claude rewrites in
exemplar style" pivot already concedes the no-LLM rationale — the
running Claude is doing semantic work in Stage 5.5 anyway. mirror.py
emits the eligible entries; SKILL.md Stage 5.5 prose instructs Claude
to do the match/select semantically.

Stdout: JSON envelope. On success:
    {
      "status": "ok",
      "corpus_path": "...",
      "entries_total": <int>,
      "entries_eligible": <int after near_duplicate_of filter>,
      "entries_skipped_malformed": <int>,
      "entries": [
        {
          "id": "simonw-001",
          "handle": "simonw",
          "post_url": "...",
          "tone_register": "...",
          "hook_structure": "...",
          "sentence_rhythm": "...",
          "topic_ownership": "...",
          "constraint_disclosure": "...",
          "length": "shortform",
          "topic_area": "ai-tooling",
          "guide_compliance": 5,                # int or null if missing
          "guide_compliance_notes": "...",      # str or null
          "approx_likes": 1562,                 # int or null
          "body": "..."                         # full text, no leading "> "
        }, ...
      ]
    }

On absent / empty / parse failure:
    {"status": "skip", "reason": "<absent|empty|io_error|parse_failed>", "message": "..."}

The helper never raises to the caller. SKILL.md treats any non-ok
status as silent-skip per SPEC §7.

Smoke tests:
    python3 mirror.py
    python3 mirror.py --examples-path /tmp/fixture.md
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

EXAMPLES_PATH = Path(__file__).resolve().parent.parent / "prompts" / "examples.local.md"

ENTRY_HEADING = re.compile(r"^### ([A-Za-z0-9][\w-]*)\s*$")
META_LINE = re.compile(r"^- ([a-z_]+):\s*(.*?)\s*$")
BODY_LINE = re.compile(r"^>(?:\s(.*)|\s*$)")

REQUIRED_AXES = (
    "tone_register",
    "hook_structure",
    "sentence_rhythm",
    "topic_ownership",
    "constraint_disclosure",
    "length",
    "topic_area",
)

INT_FIELDS = ("approx_likes", "approx_reposts", "guide_compliance")


def strip_quoted(value: str) -> str:
    """Strip a single layer of surrounding double-quotes (curation style)."""
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return value[1:-1]
    return value


def coerce_int(value: str):
    """Return int if value parses, else None. Empty / 'null' → None."""
    if value is None:
        return None
    s = value.strip()
    if not s or s.lower() in ("null", "none"):
        return None
    try:
        return int(s)
    except ValueError:
        return None


def parse_entry_block(entry_id: str, block_lines: list[str]) -> dict | None:
    """Parse one entry's metadata + body. Returns None if malformed.

    Malformed = missing any of REQUIRED_AXES, or no body.
    """
    metadata: dict[str, str] = {}
    body_lines: list[str] = []
    in_body = False
    for raw in block_lines:
        if BODY_LINE.match(raw):
            in_body = True
            m = BODY_LINE.match(raw)
            captured = m.group(1) if m and m.group(1) is not None else ""
            body_lines.append(captured)
            continue
        if in_body:
            # body ends at first non-body line
            if raw.strip() == "":
                # tolerate a single trailing blank inside body? no — terminator.
                break
            break
        m = META_LINE.match(raw)
        if m:
            key, value = m.group(1), strip_quoted(m.group(2))
            metadata[key] = value
        # silently ignore other lines (blank, stray text)

    if not body_lines:
        return None
    if not all(axis in metadata for axis in REQUIRED_AXES):
        return None

    entry: dict = {"id": entry_id}
    # carry-through string fields (preserve None for missing optionals)
    for key in (
        "handle",
        "post_url",
        "captured_at",
        "tone_register",
        "hook_structure",
        "sentence_rhythm",
        "topic_ownership",
        "constraint_disclosure",
        "length",
        "topic_area",
        "guide_compliance_notes",
        "personality_fit_note",
        "media_attached",
        "near_duplicate_of",
    ):
        entry[key] = metadata.get(key)
    for key in INT_FIELDS:
        entry[key] = coerce_int(metadata.get(key, ""))

    entry["body"] = "\n".join(body_lines).rstrip()
    return entry


def parse_examples(text: str) -> tuple[list[dict], int]:
    """Walk lines, segment by `### <id>` headings, parse each block.

    Returns (entries, malformed_count). Order preserved.
    """
    entries: list[dict] = []
    malformed = 0
    lines = text.splitlines()
    i = 0
    n = len(lines)
    while i < n:
        m = ENTRY_HEADING.match(lines[i])
        if not m:
            i += 1
            continue
        entry_id = m.group(1)
        i += 1
        block_start = i
        while i < n and not ENTRY_HEADING.match(lines[i]):
            i += 1
        block = lines[block_start:i]
        parsed = parse_entry_block(entry_id, block)
        if parsed is None:
            malformed += 1
        else:
            entries.append(parsed)
    return entries, malformed


def filter_representatives(entries: list[dict]) -> list[dict]:
    """Drop entries with `near_duplicate_of` set (cluster non-representatives)."""
    return [e for e in entries if not e.get("near_duplicate_of")]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--examples-path",
        type=Path,
        default=EXAMPLES_PATH,
        help="Override corpus location (default: skill/prompts/examples.local.md)",
    )
    args = parser.parse_args()

    path: Path = args.examples_path

    if not path.exists():
        print(json.dumps({
            "status": "skip",
            "reason": "absent",
            "message": f"Corpus not found at {path}",
            "corpus_path": str(path),
        }))
        return 0

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(json.dumps({
            "status": "skip",
            "reason": "io_error",
            "message": f"{type(exc).__name__}: {exc}",
            "corpus_path": str(path),
        }))
        return 0

    try:
        entries, malformed = parse_examples(text)
    except Exception as exc:  # noqa: BLE001 — SPEC §7 catastrophic catch-all
        print(json.dumps({
            "status": "skip",
            "reason": "parse_failed",
            "message": f"{type(exc).__name__}: {exc}",
            "corpus_path": str(path),
        }))
        return 0

    eligible = filter_representatives(entries)

    if not eligible:
        print(json.dumps({
            "status": "skip",
            "reason": "empty",
            "message": "No eligible entries after dedup",
            "corpus_path": str(path),
            "entries_total": len(entries),
            "entries_skipped_malformed": malformed,
        }))
        return 0

    output = {
        "status": "ok",
        "corpus_path": str(path),
        "entries_total": len(entries),
        "entries_eligible": len(eligible),
        "entries_skipped_malformed": malformed,
        "entries": eligible,
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
