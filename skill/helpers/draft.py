#!/usr/bin/env python3
"""Drafting engine — turn seeds into finished post bodies and file them in the queue.

This is the "drafts unasked" half of the x-comms engine. It runs headless, with no
Claude Code session open and no operator in the loop, so every failure mode here
resolves to *skip this seed and say why in a reason code* — never to a crash, and
never to a silent pass.

Pipeline per tick:

    seeds (JSON) -> prompt assembly -> `claude -p` -> parse -> deterministic gates
                 -> queue.py add (D6 anti-leak, <=280, schema write, ledger)

Two modes:

    single  one call per seed, one standalone post each (the daily ambient tick)
    arc     ONE call for all seeds, returning an ordered set (the Sunday deep tick).
            Every arc member must stand alone; see engine/task-arc.md.

Nothing here logs a post body. Skips and errors carry a reason code and, at most, a
seed_key — the tick log is the operator's only view of an unattended run, and it is
kept publishable so it can be read anywhere.

Environment:
    X_COMMS_CLI           path to the headless CLI (default `claude`). launchd has a
                          minimal PATH, so C6 must set this to an absolute path.
    X_COMMS_MODEL         model passed to `--model` (D7). Unset = CLI default.
    X_COMMS_TIMEOUT       per-call timeout in seconds (default 300).
    X_COMMS_FORCE_SEED    `1` loads the fixture seeds instead of reading a seed file.
    X_COMMS_SEED_FIXTURE  override the single-seed fixture path.
    X_COMMS_ARC_FIXTURE   override the arc fixture path.
    SESSION_PUBLISHER_NOTES_DIR / SESSION_PUBLISHER_TZ  read by queue.py.

Smoke tests:
    python3 skill/helpers/draft.py --dry-run --seeds-file <seeds.json>
    X_COMMS_FORCE_SEED=1 python3 skill/helpers/draft.py --queue-dir /tmp/q
    X_COMMS_FORCE_SEED=1 python3 skill/helpers/draft.py --mode arc --queue-dir /tmp/q
"""

from __future__ import annotations

import os
import sys

# This directory shadows two stdlib modules: `queue.py` (documented) and `select.py`
# (not, until now). Running this file as a script puts its own directory at
# sys.path[0], so `import subprocess` -> `selectors` -> `import select` resolves to the
# session-selection helper and dies with `module 'select' has no attribute 'select'`.
# Dropping our own directory from the import path fixes both at once and costs nothing:
# draft.py imports no sibling by name — queue.py is loaded by explicit file path below.
_HELPERS_DIR = os.path.dirname(os.path.realpath(__file__))
sys.path[:] = [p for p in sys.path if os.path.realpath(p or os.getcwd()) != _HELPERS_DIR]

import argparse  # noqa: E402
import importlib.util  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import re  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
from contextlib import redirect_stdout  # noqa: E402
from datetime import datetime  # noqa: E402
from pathlib import Path  # noqa: E402

HELPERS_DIR = Path(_HELPERS_DIR)
SKILL_DIR = HELPERS_DIR.parent
ENGINE_DIR = SKILL_DIR / "engine"
PROMPTS_DIR = SKILL_DIR / "prompts"
FIXTURES_DIR = SKILL_DIR / "tests" / "fixtures"

PROMPT_TEMPLATE = ENGINE_DIR / "draft-prompt.md"
TASK_TEMPLATES = {"single": ENGINE_DIR / "task-single.md", "arc": ENGINE_DIR / "task-arc.md"}
PERSONA = PROMPTS_DIR / "persona.local.md"
GUIDE = PROMPTS_DIR / "drafting-guide.md"
INSIGHTS = PROMPTS_DIR / "insights.local.md"  # D14 — included iff it exists

DEFAULT_TIMEOUT = 300
DEFAULT_MAX_DRAFTS = {"single": 2, "arc": 3}
DEFAULT_CAPACITY = 10

SKIP_REASONS = (
    "gate:reader",
    "gate:pillar",
    "gate:provenance",
    "gate:confidentiality",
    "gate:register",
    "gate:guide",
    "gate:shape",
    "gate:thin",
)

# The seven axes the model judges. `length` is derived from the body — asking for it
# only adds a way for a good draft to die on a mechanical field.
MODEL_TAG_AXES = (
    "tone_register",
    "hook_structure",
    "sentence_rhythm",
    "topic_ownership",
    "constraint_disclosure",
    "topic_area",
    "guide_compliance",
)


# --- queue module -----------------------------------------------------------
# Loaded by explicit path rather than `import queue`: a bare import resolves to our
# sibling only while this directory happens to be sys.path[0], and to the stdlib
# module otherwise. The queue contract is too load-bearing to leave to path order.


_QUEUE_MODULE = None


def queue_module():
    """Load (once) and return the sibling queue module.

    Everything the queue contract defines — sources, pillars, the 280 ceiling, the leak
    shapes, the tag vocabulary loader — is read from here rather than restated, so this
    file cannot drift into a second, silently divergent copy of the contract.
    """
    global _QUEUE_MODULE
    if _QUEUE_MODULE is None:
        spec = importlib.util.spec_from_file_location("x_comms_queue", HELPERS_DIR / "queue.py")
        if spec is None or spec.loader is None:  # pragma: no cover — packaging accident
            raise EngineError("engine:queue_missing", "cannot load queue.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _QUEUE_MODULE = module
    return _QUEUE_MODULE


class EngineError(Exception):
    """A run-level failure: the engine could not start, so nothing was drafted."""

    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.message = message


# --- deterministic anti-voice gates ----------------------------------------
# Every pattern names itself in its reason code. A draft killed here is invisible to
# the operator except through the tick log, so the log has to say which rule fired —
# an over-broad rule that reports only "rejected" is undiagnosable by construction.

EMOJI = re.compile(
    "["
    "\U0001f000-\U0001f0ff"  # playing cards, mahjong
    "\U0001f100-\U0001faff"  # enclosed alphanumerics, flags, pictographs, emoticons
    "☀-⛿"  # miscellaneous symbols
    "✀-➿"  # dingbats
    "⬀-⯿"  # arrows and stars used as emoji
    "️"  # variation selector-16
    "]"
)
# Apostrophes are normalised before matching: a model is at least as likely to emit
# U+2019 as the ASCII form, and a denylist that only knows one of them is half a gate.
SLOP_PHRASES = (
    "game-changer",
    "game changer",
    "here's the thing",
    "let that sink in",
    "delve",
    "excited to",
    "proud to",
    "thrilled",
    "the future of",
)
ANTI_VOICE = (
    ("gate:anti_voice:emoji", EMOJI),
    ("gate:anti_voice:hashtag", re.compile(r"(?:^|\s)#\w")),
    ("gate:anti_voice:url", re.compile(r"https?://|\bwww\.", re.IGNORECASE)),
    ("gate:anti_voice:exclamation", re.compile(r"!")),
    ("gate:anti_voice:first_person_plural", re.compile(r"\b(?:we|we'?re|we'?ve|our|ours)\b", re.I)),
    ("gate:anti_voice:not_just", re.compile(r"\bnot just\b[^.]{0,60}\bit'?s\b", re.IGNORECASE)),
    ("gate:anti_voice:slop_phrase", re.compile("|".join(re.escape(p) for p in SLOP_PHRASES), re.I)),
)


def normalise_apostrophes(text: str) -> str:
    return text.replace("’", "'").replace("ʼ", "'")


def reader_directed_question(body: str) -> bool:
    """A question aimed at the reader. Questions quoted to oneself are the signature.

    Split on sentence ends, not on `?` alone: splitting only at question marks glues
    every preceding sentence onto the interrogative one, so a "you" anywhere earlier in
    the body condemns a question that was never aimed at the reader. That would discard
    exactly the quoted-question-to-self the voice profile calls the signature device.
    """
    for sentence in re.split(r"(?<=[.!?])\s+", body):
        if "?" in sentence and re.search(r"\byou\b|\byour\b|\byourself\b", sentence, re.IGNORECASE):
            return True
    return False


# Digits bound into a product or version name are identity, not measurement. The guide
# asks for exactly these ("Opus 5", "Python 3.11"), and the corpus is *weaker* than the
# guide on specificity — a gate that forbids naming the model would push it weaker still.
IDENTIFIER_NUMBER = re.compile(
    r"\b(?:v|version|GPT|Claude|Opus|Sonnet|Haiku|Fable|Gemini|Llama|Mistral|Python|"
    r"macOS|iOS|HTTP|CSS|ES)[-\s]?\d+(?:\.\d+)*",
    re.IGNORECASE,
)


def unsourced_numbers(body: str, source: str) -> list[str]:
    """Digit runs in the body that do not appear as digit runs in the seed's source.

    Deliberately strict on quantities: `1` is not sourced by `10`, and a derived figure
    — a percentage computed from two seed numbers, a rounded duration — is a fabrication
    under the operator's first system never. No source number, no number.

    Version and model identifiers are exempt, because they are names.
    """
    measured = IDENTIFIER_NUMBER.sub(" ", body)
    seen = set(re.findall(r"\d+", source))
    return sorted({n for n in re.findall(r"\d+", measured) if n not in seen})


def anti_voice_failures(body: str) -> str | None:
    body = normalise_apostrophes(body)
    for reason, pattern in ANTI_VOICE:
        if pattern.search(body):
            return reason
    if reader_directed_question(body):
        return "gate:anti_voice:reader_question"
    if body.count("—") > 2:
        return "gate:anti_voice:em_dash_run"
    return None


# --- seeds ------------------------------------------------------------------

SEED_REQUIRED = ("source", "seed_ref", "seed_key", "text")


def normalise_seeds(raw) -> list[dict]:
    """Accept `{"seeds": [...]}` or a bare list; validate the shared seed contract.

    The schema is fixed by the queue contract and reused verbatim by the out-of-chain
    voice intake, so a seed that does not carry it is rejected here rather than
    half-drafted downstream.
    """
    if isinstance(raw, dict):
        raw = raw.get("seeds", [])
    if not isinstance(raw, list):
        raise EngineError("input:seeds_shape", "seeds must be a list or {\"seeds\": [...]}")
    seeds = []
    for index, seed in enumerate(raw):
        if not isinstance(seed, dict):
            raise EngineError("input:seeds_shape", f"seed {index} is not an object")
        missing = [k for k in SEED_REQUIRED if not str(seed.get(k, "")).strip()]
        if missing:
            raise EngineError("input:seed_fields", f"seed {index} missing: {', '.join(missing)}")
        # `source` is a measurement field (D11) and the out-of-chain voice intake writes
        # against this same schema. Silently rewriting an unrecognised value to `miner`
        # would record a provenance that never happened.
        if seed["source"] not in queue_module().SOURCES:
            raise EngineError("input:seed_source", f"seed {index} has unknown source")
        seeds.append(seed)
    if not seeds:
        raise EngineError("input:no_seeds", "no seeds provided")
    keys = [s["seed_key"] for s in seeds]
    if len(set(keys)) != len(keys):
        raise EngineError("input:seed_keys", "seed_key values must be unique within a run")
    return seeds


def load_seeds(args, mode: str) -> list[dict]:
    if os.environ.get("X_COMMS_FORCE_SEED") == "1" and not args.seeds_file and not args.seeds_stdin:
        default = FIXTURES_DIR / ("arc_fixture.json" if mode == "arc" else "seed_fixture.json")
        env_key = "X_COMMS_ARC_FIXTURE" if mode == "arc" else "X_COMMS_SEED_FIXTURE"
        path = Path(os.environ.get(env_key, str(default))).expanduser()
        try:
            return normalise_seeds(json.loads(path.read_text(encoding="utf-8")))
        except OSError as exc:
            raise EngineError("input:fixture_missing", f"cannot read fixture: {exc.strerror}") from exc
        except json.JSONDecodeError as exc:
            raise EngineError("input:fixture_json", f"fixture is not valid JSON: {exc}") from exc
    if args.seeds_stdin:
        text = sys.stdin.read()
    elif args.seeds_file:
        try:
            text = Path(args.seeds_file).expanduser().read_text(encoding="utf-8")
        except OSError as exc:
            raise EngineError("input:seeds_file", f"cannot read seeds file: {exc.strerror}") from exc
    else:
        raise EngineError("input:no_seeds", "one of --seeds-file, --seeds-stdin or X_COMMS_FORCE_SEED=1 is required")
    try:
        return normalise_seeds(json.loads(text))
    except json.JSONDecodeError as exc:
        raise EngineError("input:seeds_json", f"seeds are not valid JSON: {exc}") from exc


# --- prompt assembly --------------------------------------------------------


def read_required(path: Path, reason: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise EngineError(reason, f"cannot read {path.name}: {exc.strerror}") from exc


def render_vocabulary(vocab: dict[str, tuple[str, ...]]) -> str:
    lines = []
    for axis in MODEL_TAG_AXES:
        if axis == "guide_compliance":
            continue
        values = vocab.get(axis)
        if not values:
            # Fail closed rather than prompt for a free-text value that add would reject.
            raise EngineError("engine:vocab", f"tag vocabulary for `{axis}` did not load")
        lines.append(f"- `{axis}` — one of: " + ", ".join(f"`{v}`" for v in values))
    return "\n".join(lines)


def fence_for(text: str) -> str:
    """A backtick fence longer than any run inside `text`.

    Seed `text` is real source material, not a summary — since 2026-08-28 it
    carries a session document's narrative sections, which routinely embed
    their own fenced code blocks. A fixed ``` fence would be closed by the
    first one, dumping the rest of the seed into the prompt as instructions
    rather than as quoted source.
    """
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    return "`" * max(3, longest + 1)


def render_seeds(seeds: list[dict]) -> str:
    blocks = []
    for seed in seeds:
        text = str(seed["text"]).strip()
        fence = fence_for(text)
        blocks.append(
            "\n".join(
                [
                    f"### seed {seed['seed_key']}",
                    "",
                    f"- `source`: {seed['source']}",
                    f"- `seed_ref`: {seed['seed_ref']}",
                    f"- `pillar_hint`: {seed.get('pillar_hint') or 'none'}",
                    "",
                    "`text` (the only source of numbers, tense and causation):",
                    "",
                    fence,
                    text,
                    fence,
                ]
            )
        )
    return "\n\n".join(blocks)


def assemble_prompt(seeds: list[dict], mode: str, vocab: dict) -> str:
    template = read_required(PROMPT_TEMPLATE, "engine:template")
    task = read_required(TASK_TEMPLATES[mode], "engine:template")
    persona = read_required(PERSONA, "engine:persona")
    guide = read_required(GUIDE, "engine:guide")

    # D14 — the performance loop writes this file later. Absent is the normal state
    # today and must leave no trace in the prompt, not an empty heading.
    insights = ""
    if INSIGHTS.exists():
        insights = "## B2. Performance insights from posted entries\n\n" + INSIGHTS.read_text(
            encoding="utf-8"
        )

    values = {
        "PERSONA": persona,
        "GUIDE": guide,
        "INSIGHTS": insights,
        "TAG_VOCABULARY": render_vocabulary(vocab),
        "SEEDS": render_seeds(seeds),
        "TASK": task,
    }

    # ONE pass over the template, with substituted text never rescanned. Both
    # halves of that matter now that seed `text` is a whole session document
    # rather than a few index columns:
    #
    #   - a `{{REPO_NAME}}` quoted inside a document (repo-bootstrap sessions
    #     carry these — `github-ops` mandates a `grep -r "{{"` check, so they
    #     keep being written) is indistinguishable from an unfilled template
    #     slot once it is in the assembled string. A post-substitution leftover
    #     scan reads it as a template fault and kills the whole tick, and since
    #     the seed never reaches `queue.py add` no ledger event is written, so
    #     it is re-mined and re-kills every tick until it ages out.
    #   - a seed containing the literal `{{TASK}}` would, under sequential
    #     replace, have the real task instructions substituted INTO it.
    #
    # Substituting via one `re.sub` callback closes both: the pattern walks the
    # template's own text, and whatever the callback returns is output, not input.
    missing: list[str] = []

    def substitute(match: re.Match) -> str:
        name = match.group(1)
        if name not in values:
            missing.append(name)
            return match.group(0)
        return values[name]

    filled = re.sub(r"\{\{([A-Z_]+)\}\}", substitute, template)
    if missing:
        raise EngineError("engine:template", f"unfilled placeholders: {', '.join(sorted(set(missing)))}")
    return filled


# --- headless invocation ----------------------------------------------------


def call_cli(prompt: str, model: str | None, timeout: int, stub: Path | None) -> tuple[str | None, str | None]:
    """Run the headless CLI. Returns (text, reason_code) — exactly one is non-None.

    Every failure is a reason code, never an exception: one unusable answer must not
    take down the rest of the tick.
    """
    if stub is not None:
        try:
            return stub.read_text(encoding="utf-8"), None
        except OSError:
            return None, "engine:stub_missing"

    cli = os.environ.get("X_COMMS_CLI", "claude")
    # `--tools ""` disables every built-in tool. The prompt asks for no tool use too,
    # but an unattended run cannot afford to rely on that: one tool attempt burns the
    # whole timeout and returns nothing.
    cmd = [cli, "-p", "--output-format", "json", "--strict-mcp-config", "--tools", ""]
    if model:
        cmd += ["--model", model]

    # A neutral working directory keeps project CLAUDE.md files out of the prompt, so
    # what the model sees is exactly what was assembled above.
    with tempfile.TemporaryDirectory(prefix="x-comms-") as workdir:
        try:
            completed = subprocess.run(
                cmd,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=workdir,
                check=False,
            )
        except FileNotFoundError:
            return None, "engine:cli_missing"
        except subprocess.TimeoutExpired:
            return None, "engine:timeout"
        except OSError:
            return None, "engine:cli_error"

    if completed.returncode != 0:
        return None, f"engine:exit_{completed.returncode}"
    try:
        envelope = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return None, "engine:envelope"
    if not isinstance(envelope, dict) or envelope.get("is_error"):
        return None, "engine:cli_reported_error"
    result = envelope.get("result")
    if not isinstance(result, str) or not result.strip():
        return None, "engine:empty_result"
    return result, None


def parse_response(text: str) -> tuple[dict | None, str | None]:
    """Pull one JSON object out of the model's reply.

    Tolerates a markdown fence and surrounding prose, because a model that adds a
    sentence has still done the work. Anything else is malformed and skipped.
    """
    stripped = text.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)\s*```", stripped, re.DOTALL)
    if fence:
        stripped = fence.group(1).strip()
    start, end = stripped.find("{"), stripped.rfind("}")
    if start == -1 or end <= start:
        return None, "engine:malformed"
    try:
        parsed = json.loads(stripped[start : end + 1])
    except json.JSONDecodeError:
        return None, "engine:malformed"
    if not isinstance(parsed, dict):
        return None, "engine:malformed"
    return parsed, None


# --- draft validation -------------------------------------------------------


def normalise_skip_reason(raw) -> str:
    reason = str(raw or "").strip()
    return reason if reason in SKIP_REASONS else "gate:unspecified"


def validate_draft(post: dict, seed: dict, queue_mod, vocab: dict) -> tuple[dict | None, str | None]:
    """Run every deterministic gate. Returns (validated, reason_code)."""
    body = post.get("body")
    if not isinstance(body, str) or not body.strip():
        return None, "schema:body_missing"
    body = body.strip("\n")

    if len(body) > queue_mod.MAX_BODY_CHARS:
        return None, "len:over_280"

    pillar = str(post.get("pillar", "")).strip()
    if pillar not in queue_mod.PILLARS:
        return None, "schema:pillar"

    tags_raw = post.get("corpus_tags")
    if not isinstance(tags_raw, dict):
        return None, "schema:tags_missing"
    tags = {}
    for axis in MODEL_TAG_AXES:
        value = str(tags_raw.get(axis, "")).strip()
        if not value:
            return None, f"schema:tag_missing:{axis}"
        if axis == "guide_compliance":
            try:
                if not 1 <= int(value) <= 5:
                    return None, "schema:tag_range:guide_compliance"
            except ValueError:
                return None, "schema:tag_type:guide_compliance"
        elif value not in vocab.get(axis, ()):
            return None, f"schema:tag_enum:{axis}"
        tags[axis] = value
    # Derived, never asked for: the 280 gate above already settled it.
    tags["length"] = "shortform"

    reason = anti_voice_failures(body)
    if reason:
        return None, reason

    unsourced = unsourced_numbers(body, f"{seed['text']}\n{seed['seed_ref']}")
    if unsourced:
        # The digits themselves are the diagnosis and they are not private —
        # they came from a body the operator will never see otherwise.
        return None, "gate:unsourced_number:" + ",".join(unsourced[:3])

    # D6 pre-write. queue.py add runs this again as the backstop; running it here
    # turns a hard rejection into an ordinary skip that the rest of the tick survives.
    leak = queue_mod.scan_for_leaks(body)
    if leak:
        return None, leak[0]

    # Everything below is a check `cmd_add` would also make. It has to run *here*,
    # before arc numbering, or a member can pass validation, be given a position, and
    # then be refused at the write — leaving an arc that claims a member it does not
    # have. seed_ref gets the shape gate only: it never leaves the private queue file
    # and is expected to name private work (queue.py cmd_add makes the same split).
    seed_ref = str(seed["seed_ref"])
    if "\n" in seed_ref or "\r" in seed_ref:
        return None, "input:newline"
    leak = queue_mod.scan_for_leaks(seed_ref, private_terms=False)
    if leak:
        return None, leak[0]

    return {"body": body, "pillar": pillar, "tags": tags}, None


# --- queue write ------------------------------------------------------------


def queue_add(queue_mod, args, validated: dict, seed: dict, model: str | None, arc: dict | None):
    """Write one entry through queue.py's own add path.

    Reusing cmd_add rather than re-implementing the schema keeps a single writer for
    the contract. Its stdout is captured so this script's stdout stays one JSON
    summary line, which is what the tick log reads.
    """
    namespace = argparse.Namespace(
        queue_dir=args.queue_dir,
        body=validated["body"],
        body_file=None,
        body_stdin=False,
        source=seed["source"],
        seed_ref=seed["seed_ref"],
        pillar=validated["pillar"],
        drafted_by=f"x-comms-engine/1.0 (claude -p {model or 'default'})",
        tags_json=json.dumps(validated["tags"]),
        tag=None,
        arc_id=(arc or {}).get("arc_id"),
        arc_pos=(arc or {}).get("arc_pos"),
        arc_of=(arc or {}).get("arc_of"),
        arc_note=(arc or {}).get("arc_note"),
    )
    captured = io.StringIO()
    try:
        with redirect_stdout(captured):
            queue_mod.cmd_add(namespace)
    except queue_mod.QueueError as exc:
        return None, exc.reason_code
    except OSError:
        return None, "io:error"
    try:
        return json.loads(captured.getvalue().strip().splitlines()[-1]), None
    except (ValueError, IndexError):  # pragma: no cover — add printed something else
        return {"status": "added"}, None


def queued_count(queue_mod, queue_dir) -> int:
    total = 0
    for path in queue_mod.entry_paths(queue_dir):
        try:
            fields, _ = queue_mod.parse_entry(path)
        except queue_mod.QueueError:
            continue
        if fields.get("status") == "queued":
            total += 1
    return total


# --- run --------------------------------------------------------------------


def arc_identifier(queue_mod) -> str:
    """A run-unique arc id.

    The ISO week alone is not unique: a re-run after a partial failure, or C6's forced
    kickstart smoke test, would reuse the id with restarting positions, and the review
    surface groups by arc_id — it would render one arc holding two sets of members.
    """
    now = datetime.now(queue_mod.TZ)
    return "arc_{}-W{:02d}_{}".format(*now.isocalendar()[:2], now.strftime("%H%M%S"))


def run_single(seeds, args, queue_mod, vocab, model, timeout, stub, report) -> None:
    for seed in seeds[: args.max_drafts]:
        prompt = assemble_prompt([seed], "single", vocab)
        text, reason = call_cli(prompt, model, timeout, stub)
        if reason:
            report["errors"].append({"seed_key": seed["seed_key"], "reason": reason})
            continue
        parsed, reason = parse_response(text)
        if reason:
            report["errors"].append({"seed_key": seed["seed_key"], "reason": reason})
            continue
        if parsed.get("decision") != "draft":
            report["skipped"].append(
                {"seed_key": seed["seed_key"], "reason": normalise_skip_reason(parsed.get("reason"))}
            )
            continue
        validated, reason = validate_draft(parsed, seed, queue_mod, vocab)
        if reason:
            report["skipped"].append({"seed_key": seed["seed_key"], "reason": reason})
            continue
        written, reason = queue_add(queue_mod, args, validated, seed, model, None)
        if reason:
            report["skipped"].append({"seed_key": seed["seed_key"], "reason": reason})
            continue
        report["drafted"].append({"seed_key": seed["seed_key"], "id": written.get("id")})


def run_arc(seeds, args, queue_mod, vocab, model, timeout, stub, report) -> None:
    """One call, one ordered set (D15).

    Members that fail a gate are dropped and the survivors renumbered contiguously, so
    a queue never carries an arc with a hole in it. A one-member survivor loses its arc
    metadata entirely — an arc of one is a single, and calling it otherwise would show
    the operator connective tissue that connects to nothing.
    """
    by_key = {seed["seed_key"]: seed for seed in seeds}
    prompt = assemble_prompt(seeds, "arc", vocab)
    text, reason = call_cli(prompt, model, timeout, stub)
    if reason:
        report["errors"].append({"seed_key": None, "reason": reason})
        return
    parsed, reason = parse_response(text)
    if reason:
        report["errors"].append({"seed_key": None, "reason": reason})
        return
    if parsed.get("decision") != "draft":
        for seed in seeds:
            report["skipped"].append(
                {"seed_key": seed["seed_key"], "reason": normalise_skip_reason(parsed.get("reason"))}
            )
        return

    for entry in parsed.get("skipped") or []:
        if isinstance(entry, dict) and entry.get("seed_key") in by_key:
            report["skipped"].append(
                {"seed_key": entry["seed_key"], "reason": normalise_skip_reason(entry.get("reason"))}
            )

    posts = parsed.get("posts")
    if not isinstance(posts, list) or not posts:
        report["errors"].append({"seed_key": None, "reason": "engine:no_posts"})
        return

    survivors = []
    used = set()
    for post in posts[: args.max_drafts]:
        if not isinstance(post, dict):
            report["errors"].append({"seed_key": None, "reason": "engine:malformed_post"})
            continue
        key = str(post.get("seed_key", "")).strip()
        if key not in by_key or key in used:
            report["errors"].append({"seed_key": None, "reason": "engine:seed_key_unmatched"})
            continue
        used.add(key)
        validated, reason = validate_draft(post, by_key[key], queue_mod, vocab)
        if reason:
            report["skipped"].append({"seed_key": key, "reason": reason})
            continue
        survivors.append((key, validated))

    unaccounted = [s["seed_key"] for s in seeds if s["seed_key"] not in used]
    accounted = {e["seed_key"] for e in report["skipped"]}
    for key in unaccounted:
        if key not in accounted:
            report["skipped"].append({"seed_key": key, "reason": "gate:unspecified"})

    arc_note = parsed.get("arc_note")
    arc_note = re.sub(r"\s+", " ", str(arc_note)).strip() if arc_note else None
    arc_id = arc_identifier(queue_mod) if len(survivors) > 1 else None

    for position, (key, validated) in enumerate(survivors, start=1):
        arc = None
        if arc_id:
            arc = {
                "arc_id": arc_id,
                "arc_pos": str(position),
                "arc_of": str(len(survivors)),
                "arc_note": arc_note,
            }
        written, reason = queue_add(queue_mod, args, validated, by_key[key], model, arc)
        if reason:
            # Positions were allocated before this write, so the arc is now short a
            # member. Everything a gate can catch was caught before numbering; what is
            # left is I/O. Say so in the report rather than leave the review surface to
            # render a sibling that does not exist.
            report["skipped"].append({"seed_key": key, "reason": reason})
            if arc_id:
                report["arc_incomplete"] = arc_id
            continue
        report["drafted"].append(
            {"seed_key": key, "id": written.get("id"), "arc_pos": position if arc_id else None}
        )


def run(args) -> int:
    mode = args.mode
    queue_mod = queue_module()
    vocab = queue_mod.load_tag_vocabulary()
    seeds = load_seeds(args, mode)
    model = args.model or os.environ.get("X_COMMS_MODEL") or None
    try:
        # C6 sets this from the plist, which is exactly where a typo lands — and a
        # traceback here would print this file's absolute path into the tick log.
        timeout = args.timeout or int(os.environ.get("X_COMMS_TIMEOUT", DEFAULT_TIMEOUT))
    except ValueError:
        raise EngineError("input:timeout", "X_COMMS_TIMEOUT is not an integer") from None
    stub = Path(args.stub_response).expanduser() if args.stub_response else None
    if args.max_drafts is None:
        args.max_drafts = DEFAULT_MAX_DRAFTS[mode]

    report = {
        "status": "ok",
        "mode": mode,
        "model": model or "cli-default",
        "seeds": len(seeds),
        "drafted": [],
        "skipped": [],
        "errors": [],
    }

    if args.dry_run:
        prompt = assemble_prompt(seeds if mode == "arc" else seeds[:1], mode, vocab)
        report["dry_run"] = {
            "prompt_chars": len(prompt),
            "insights_included": INSIGHTS.exists(),
            "max_drafts": args.max_drafts,
        }
        print(json.dumps(report, ensure_ascii=False))
        return 0

    queue_dir = queue_mod.resolve_queue_dir(args.queue_dir)
    in_queue = queued_count(queue_mod, queue_dir)
    if in_queue >= args.capacity:
        # D8: a full queue is a correct outcome, not a failure. Drafting into it would
        # only feed the expiry pass.
        report["skipped"] = [{"seed_key": s["seed_key"], "reason": "queue:at_capacity"} for s in seeds]
        report["queued_before"] = in_queue
        print(json.dumps(report, ensure_ascii=False))
        return 0

    if mode == "arc":
        run_arc(seeds, args, queue_mod, vocab, model, timeout, stub, report)
    else:
        run_single(seeds, args, queue_mod, vocab, model, timeout, stub, report)

    print(json.dumps(report, ensure_ascii=False))
    # Exit 2 == the engine itself never produced a usable answer for any seed. The tick
    # ran, so this is not a crash, but run.sh needs to tell "nothing was postable" from
    # "the headless call is broken".
    if report["errors"] and not report["drafted"] and not report["skipped"]:
        return 2
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--mode", choices=("single", "arc"), default="single")
    parser.add_argument("--seeds-file", help="JSON file of seeds")
    parser.add_argument("--seeds-stdin", action="store_true", help="read seeds JSON from stdin")
    parser.add_argument("--queue-dir", help="override the queue directory (testing)")
    parser.add_argument("--max-drafts", type=int, help="cap seeds attempted this run")
    parser.add_argument("--capacity", type=int, default=DEFAULT_CAPACITY, help="skip when the queue holds this many queued entries")
    parser.add_argument("--model", help="override the drafting model (else X_COMMS_MODEL)")
    parser.add_argument("--timeout", type=int, help="per-call timeout in seconds")
    parser.add_argument("--dry-run", action="store_true", help="assemble the prompt, call nothing")
    parser.add_argument(
        "--stub-response",
        help="test hook: read the model reply from a file instead of calling the CLI",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except EngineError as exc:
        print(f"draft.py: failed reason={exc.reason_code} detail={exc.message}", file=sys.stderr)
        print(json.dumps({"status": "failed", "reason_code": exc.reason_code}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
