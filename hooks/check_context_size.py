#!/usr/bin/env python3
"""Size guard for ``## Project context`` in an AGENTS.md (github-ops W2 / D9).

WHAT IT IS
    A read-only measurer. It never edits anything. It reports one of three
    outcomes through its exit status:

        0   ok, or not applicable (a ``SKIP:`` line on stdout)
        3   verdict  — the section, marked state region or whole file is the
                       wrong size or shape, or a baseline boundary was destroyed
        2   could not run — a bad argument, an unreadable input, undecodable
                       bytes, an empty baseline, or an unexpected exception

    Every consumer must treat any other status as "could not run".

WHY THE VERDICT IS 3 AND NOT 1 (github-ops strategy/decisions.md ADR-010)
    CPython owns exit 1. A module that fails at *import* time — a SyntaxError,
    a missing dependency, a raise at module level — exits 1 before a single
    line of this file's own error handling runs, and no ``try/except`` inside
    ``main`` can change that. Putting the verdict on 3, a status the
    interpreter never produces on its own, is what makes "the section is too
    big" distinguishable from "this script is broken". The wrapper at the
    bottom maps an unexpected exception *inside* ``main`` to 2; an import-time
    failure still exits 1, honestly, and the caller reads that as could-not-run.

DEFINITIONS (verbatim from the session-factory's CF-99 check, so the two tools
compute the same answer — LD-W2-3)
    § Project context   the lines AFTER the line ``## Project context``
                        (exclusive) up to the next line beginning ``## ``
                        (exclusive) or EOF. A ``### `` line does not end it.
                        The heading is matched as a WHOLE LINE with trailing
                        whitespace tolerated, never as a substring: this
                        repo's own template quotes headings verbatim inside
                        HTML comments, so a substring match latches onto the
                        comment (ADR-011).
    the markers         ``<!-- fab:state-begin -->`` / ``<!-- fab:state-end -->``,
                        each matched as a whole TRIMMED line, never as a
                        substring — prose may legitimately mention the tokens,
                        and an incidental reindent must not disarm the check.
    well-formed         exactly one of each marker, begin before end, and both
                        inside § Project context.
    the region          the lines strictly BETWEEN the marker lines, each with
                        its line terminator, nothing stripped.
    blank / paragraph   a line is blank iff ``strip()`` is empty; a paragraph is
                        a maximal run of non-blank lines. A whitespace-only
                        separator line therefore splits paragraphs, and leading
                        or trailing blank lines create none.

THE RULES, IN THE ORDER THEY ARE APPLIED (LD-W2-4)
    1. Read each input as raw bytes, ONCE, into memory. Neither input is ever
       stat'd: the baseline normally arrives as a ``/dev/fd/N`` pipe from the
       hook's process substitution, which ``os.stat`` reports as 0 bytes and
       which yields nothing on a second read. Emptiness is decided on the
       length of the bytes actually read. Decode strictly; a failure is
       could-not-run naming the byte offset. A baseline that was given but is
       empty is could-not-run — a failed ``git show`` produces exactly that,
       and it must not be mistaken for "there was no baseline". A candidate
       that is empty while a baseline was given is could-not-run for the same
       reason, so a truncated ``git show`` cannot become a heading verdict.
    2. Heading count. Exactly one continues. None, with a baseline that had
       exactly one, is a ``heading`` verdict — a rename must not be the way the
       check quietly stops running. None, with no such baseline, is a skip.
       More than one is a ``malformed`` verdict.
    3. Section bound: the section's raw UTF-8 bytes, line terminators included.
       Over the bound is a ``section-bytes`` verdict. This bound applies
       WHETHER OR NOT the markers are present (LD-W2-5) — otherwise wrapping a
       small paragraph in markers would exempt the rest of the section from any
       bound, which is the bypass this guard exists to close. There is no floor
       and no warn band (LD-W2-6): the template's own TODO section must pass on
       a repo's first commit.
    4. Markers. If any marker line is present it must be well-formed, else a
       ``markers`` verdict. Then the region must be non-empty, exactly one
       paragraph and within the character bound (``region-shape`` /
       ``region-chars``), and — when the baseline is well-formed — must not have
       grown past the per-commit bound (``region-growth``), unless ``--merge``
       was given. That flag skips ONLY growth; all other rules still apply.
       If the candidate has NO marker line but the baseline is well-formed,
       that is a ``markers`` verdict: the component being checked must not be
       able to switch off its own checker. A candidate with markers whose
       baseline has none is first adoption, and gets no growth check.
    5. Whole file: at or over 32,768 raw candidate bytes, a ``whole-file``
       verdict. This follows every existing rule so section-bytes retains
       precedence. The skip of step 2 returns before this, so a not-applicable
       file stays silent on stderr.
    6. On 0, one ``OK:`` line on stdout carrying the section byte count and,
       when marked, the region character count.

THE BOUNDS (locked; kickoff LD-A / LD-K and the 2026-09-08 amendment)
    section 6,000 bytes · region 3,500 characters · region growth 800
    characters per ordinary commit · whole file strictly under 32,768 bytes.

VERDICT LINES
    Every verdict line goes to stderr and begins with a stable rule key and a
    colon, so a caller can branch on it without parsing prose:

        section-bytes   region-chars   region-growth   region-shape
        markers         heading        malformed       whole-file

    ``OK:`` and ``SKIP:`` go to stdout only; could-not-run messages go to
    stderr and begin ``could not run:``.

COUNTING
    Section size is counted in BYTES of the raw blob: a CRLF file counts both
    its carriage return and its line feed, identically on the file path and on
    the stdin path. There is no newline translation anywhere — no
    ``io.TextIOWrapper``, no ``newline=``. Region size is counted in Unicode
    CODE POINTS (Python ``len``), which differs from the session-factory
    validator's UTF-16 count only for astral characters (LD-W2-20).

ACCEPTED LIMITATIONS, STATED RATHER THAN HIDDEN
    * A line beginning ``## `` inside a fenced code block ends the section
      early. The session-factory validator has the same limitation; the two
      tools agreeing is worth more here than either being cleverer.
    * A section that is BOTH oversized and undecodable reports could-not-run,
      not the size verdict, because decoding necessarily precedes measurement
      (the design record's S-12 trade-off).
    * Marker lines are counted over the WHOLE file, not just the section, so
      that this tool and the factory's validator agree on "exactly one of
      each" (LD-W2-3). The cost is the twin of the fenced-``## `` limitation
      above: a marker token standing alone on its own line anywhere else in
      the file - a fenced block in another section documenting the convention
      - counts, and a healthy marked section then reports ``markers``.
      Indenting that line does NOT help, because the match is on the whole
      TRIMMED line; put the token inside a sentence instead of on a line of
      its own.

PORTABILITY
    Standard library only, and syntax valid on Python 3.9 — Apple's Command
    Line Tools interpreter at /usr/bin/python3, the lowest a git hook launched
    by a GUI app realistically resolves. Runs under whatever ``python3`` is on
    PATH.

USAGE
    check_context_size.py [--merge] [--baseline PATH] [--candidate PATH | CANDIDATE]
    check_context_size.py --help | -h

    CANDIDATE is a file path or ``-`` for stdin; ``--candidate PATH`` is an
    alias for the positional, so the factory can call this with its own
    validator's flag shape. The default candidate is AGENTS.md. ``--baseline``
    names any readable path INCLUDING a ``/dev/fd/N`` pipe — there is
    deliberately no "regular file only" check here (LD-W2-2). ``--merge``
    suppresses only growth against a baseline; without a baseline it is a no-op.
"""

import collections
import sys

SECTION_CEILING_BYTES = 6000
REGION_CEILING_CHARS = 3500
REGION_GROWTH_CHARS = 800
WHOLE_FILE_CEILING_BYTES = 32768

HEADING = "## Project context"
MARKER_BEGIN = "<!-- fab:state-begin -->"
MARKER_END = "<!-- fab:state-end -->"

EXIT_OK = 0
EXIT_COULD_NOT_RUN = 2
EXIT_VERDICT = 3

DEFAULT_CANDIDATE = "AGENTS.md"
STDIN_PATH = "-"

EMPTY_BASELINE_MESSAGE = (
    "the baseline is empty - a failed 'git show' produces exactly this, and an "
    "empty baseline must not be read as 'there was no baseline'"
)
EMPTY_CANDIDATE_MESSAGE = (
    "the candidate is empty while a baseline was given - a failed or truncated "
    "'git show' must not become a missing-heading verdict"
)

_Line = collections.namedtuple("_Line", ("raw_length", "text", "raw_text"))
_MarkerState = collections.namedtuple(
    "_MarkerState", ("present", "well_formed", "reason", "begin", "end")
)
_View = collections.namedtuple(
    "_View", ("lines", "headings", "section", "markers", "region")
)
_Options = collections.namedtuple("_Options", ("candidate", "baseline", "skip_growth", "help"))


class _InputError(Exception):
    """An input made the check impossible to run (exit 2)."""


class _UsageError(_InputError):
    """The command line itself was wrong (exit 2)."""


def _parse_arguments(argument_list):
    """Hand-rolled so the exit status for a bad flag is ours, not argparse's."""
    baseline_path = None
    candidate_path = None
    skip_growth = False
    show_help = False
    index = 0
    while index < len(argument_list):
        argument = argument_list[index]
        if argument == "--merge":
            skip_growth = True
        elif argument in ("--help", "-h"):
            show_help = True
        elif argument == "--baseline" or argument == "--candidate":
            index += 1
            if index >= len(argument_list):
                raise _UsageError("%s needs a path" % argument)
            value = argument_list[index]
            if argument == "--baseline":
                baseline_path = value
            else:
                candidate_path = value
        elif argument.startswith("--baseline="):
            baseline_path = argument[len("--baseline="):]
        elif argument.startswith("--candidate="):
            candidate_path = argument[len("--candidate="):]
        elif argument == STDIN_PATH or not argument.startswith("-"):
            if candidate_path is not None:
                raise _UsageError("more than one candidate was given")
            candidate_path = argument
        else:
            raise _UsageError("unknown option %s" % argument)
        index += 1
    if candidate_path is None:
        candidate_path = DEFAULT_CANDIDATE
    if candidate_path == "":
        raise _UsageError("the candidate path is empty")
    if baseline_path == "":
        raise _UsageError("the --baseline path is empty")
    return _Options(candidate_path, baseline_path, skip_growth, show_help)


def _read_input(path, label):
    """Read one input exactly once. Never stat it: a pipe stats as 0 bytes."""
    if path == STDIN_PATH:
        try:
            return sys.stdin.buffer.read()
        except OSError as error:
            raise _InputError("could not read the %s from stdin: %s" % (label, error))
    try:
        handle = open(path, "rb")
    except OSError as error:
        raise _InputError("could not open the %s '%s': %s" % (label, path, error.strerror or error))
    try:
        return handle.read()
    except OSError as error:
        raise _InputError("could not read the %s '%s': %s" % (label, path, error.strerror or error))
    finally:
        handle.close()


def _decode(blob, label):
    """The single strict decode. surrogateescape here would hide corrupt input."""
    try:
        return blob.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise _InputError(
            "the %s is not valid UTF-8 at byte offset %d (%s)" % (label, error.start, error.reason)
        )


def _scan_lines(blob, text):
    """Pair each line's decoded text with its raw UTF-8 byte length.

    Lines are split on "\\n" only (LD-W2-7), never on the wider set
    ``str.splitlines`` recognises. A 0x0A byte never occurs inside a multi-byte
    UTF-8 sequence, so the byte split and the text split agree piece for piece
    and the decoded text never has to be re-encoded to learn a byte count.
    """
    raw_pieces = blob.split(b"\n")
    text_pieces = text.split("\n")
    terminated_count = len(raw_pieces) - 1
    if raw_pieces[-1] == b"":
        raw_pieces = raw_pieces[:-1]
        text_pieces = text_pieces[:-1]
    lines = []
    for index in range(len(raw_pieces)):
        newline_bytes = 1 if index < terminated_count else 0
        raw_length = len(raw_pieces[index]) + newline_bytes
        piece = text_pieces[index]
        content = piece[:-1] if piece.endswith("\r") else piece
        raw_text = piece + ("\n" if newline_bytes else "")
        lines.append(_Line(raw_length, content, raw_text))
    return lines


def _is_heading(line_text):
    """Whole-line match, trailing whitespace tolerated (LD-W2-3, ADR-011)."""
    return line_text.rstrip() == HEADING


def _is_marker(line_text, marker):
    """Whole-trimmed-line match, never a substring (LD-W2-3, CF-99)."""
    return line_text.strip() == marker


def _heading_indexes(lines):
    return [index for index, line in enumerate(lines) if _is_heading(line.text)]


def _section_range(lines, heading_index):
    """Half-open [start, stop) line range of § Project context."""
    stop = len(lines)
    for index in range(heading_index + 1, len(lines)):
        if lines[index].text.startswith("## "):
            stop = index
            break
    return (heading_index + 1, stop)


def _section_byte_length(lines, section):
    """Raw UTF-8 bytes of the section, terminators included (a CRLF counts both)."""
    start, stop = section
    return sum(line.raw_length for line in lines[start:stop])


def _marker_state(lines, section):
    begins = [index for index, line in enumerate(lines) if _is_marker(line.text, MARKER_BEGIN)]
    ends = [index for index, line in enumerate(lines) if _is_marker(line.text, MARKER_END)]
    if not begins and not ends:
        return _MarkerState(False, False, None, None, None)
    if len(begins) != 1 or len(ends) != 1:
        return _MarkerState(
            True,
            False,
            "found %d fab:state-begin and %d fab:state-end marker lines; exactly one of each is required"
            % (len(begins), len(ends)),
            None,
            None,
        )
    begin_index = begins[0]
    end_index = ends[0]
    if begin_index >= end_index:
        return _MarkerState(
            True, False, "the fab:state-begin marker must come before the fab:state-end marker", None, None
        )
    if section is None or begin_index < section[0] or end_index >= section[1]:
        return _MarkerState(
            True, False, "both fab:state markers must lie inside %s" % HEADING, None, None
        )
    return _MarkerState(True, True, None, begin_index, end_index)


def _region_text(lines, markers):
    """The lines strictly between the markers, terminators included, nothing stripped."""
    return "".join(line.raw_text for line in lines[markers.begin + 1:markers.end])


def _count_paragraphs(lines, markers):
    """Maximal runs of non-blank lines; a whitespace-only line is blank."""
    paragraphs = 0
    inside_paragraph = False
    for line in lines[markers.begin + 1:markers.end]:
        if line.text.strip() == "":
            inside_paragraph = False
        elif not inside_paragraph:
            paragraphs += 1
            inside_paragraph = True
    return paragraphs


def _build_view(blob, text):
    lines = _scan_lines(blob, text)
    headings = _heading_indexes(lines)
    section = _section_range(lines, headings[0]) if len(headings) == 1 else None
    markers = _marker_state(lines, section)
    region = _region_text(lines, markers) if markers.well_formed else None
    return _View(lines, headings, section, markers, region)


def _verdict(rule_key, message):
    return "%s: %s" % (rule_key, message)


def _evaluate(candidate, baseline, skip_growth=False):
    """Return a verdict line, or None when the candidate is within its bounds."""
    if not candidate.headings:
        return _verdict(
            "heading",
            "the '%s' heading present at the baseline is missing from the candidate" % HEADING,
        )
    if len(candidate.headings) > 1:
        return _verdict(
            "malformed",
            "found %d '%s' heading lines; exactly one is required" % (len(candidate.headings), HEADING),
        )

    section_bytes = _section_byte_length(candidate.lines, candidate.section)
    if section_bytes > SECTION_CEILING_BYTES:
        return _verdict(
            "section-bytes",
            "%s is %d bytes, over the %d-byte bound (text outside the fab:state markers counts too)"
            % (HEADING, section_bytes, SECTION_CEILING_BYTES),
        )

    if candidate.markers.present:
        if not candidate.markers.well_formed:
            return _verdict("markers", candidate.markers.reason)
        paragraphs = _count_paragraphs(candidate.lines, candidate.markers)
        if paragraphs == 0:
            return _verdict("region-shape", "the state region is empty")
        if paragraphs != 1:
            return _verdict(
                "region-shape",
                "the state region must be exactly one paragraph (found %d)" % paragraphs,
            )
        region_chars = len(candidate.region)
        if region_chars > REGION_CEILING_CHARS:
            return _verdict(
                "region-chars",
                "the state region is %d characters, over the %d-character bound"
                % (region_chars, REGION_CEILING_CHARS),
            )
        if baseline is not None and baseline.markers.well_formed:
            growth = region_chars - len(baseline.region)
            if not skip_growth and growth > REGION_GROWTH_CHARS:
                return _verdict(
                    "region-growth",
                    "the state region grew by %d characters, over the %d-character per-commit bound"
                    % (growth, REGION_GROWTH_CHARS),
                )
    elif baseline is not None and baseline.markers.well_formed:
        return _verdict(
            "markers", "the fab:state markers present at the baseline are missing from the candidate"
        )
    whole_file_bytes = sum(line.raw_length for line in candidate.lines)
    if whole_file_bytes >= WHOLE_FILE_CEILING_BYTES:
        return _verdict(
            "whole-file",
            "the whole file is %d bytes, at or over the %d-byte bound"
            % (whole_file_bytes, WHOLE_FILE_CEILING_BYTES),
        )
    return None


def _ok_line(candidate):
    section_bytes = _section_byte_length(candidate.lines, candidate.section)
    if candidate.markers.well_formed:
        return "OK: section %d bytes, region %d chars" % (section_bytes, len(candidate.region))
    return "OK: section %d bytes" % section_bytes


def _could_not_run(message):
    sys.stderr.write("could not run: %s\n" % message)
    return EXIT_COULD_NOT_RUN


def _run(argument_list):
    options = _parse_arguments(argument_list)
    if options.help:
        sys.stdout.write(
            "Usage: check_context_size.py [--merge] [--baseline PATH] "
            "[--candidate PATH | CANDIDATE]\n"
            "CANDIDATE defaults to AGENTS.md; use - for stdin.\n"
            "--merge skips only baseline growth; --help / -h shows this usage.\n"
        )
        return EXIT_OK

    candidate_blob = _read_input(options.candidate, "candidate")
    baseline_blob = None
    if options.baseline is not None:
        baseline_blob = _read_input(options.baseline, "baseline")
        if len(baseline_blob) == 0:
            return _could_not_run(EMPTY_BASELINE_MESSAGE)
        if len(candidate_blob) == 0:
            return _could_not_run(EMPTY_CANDIDATE_MESSAGE)

    candidate = _build_view(candidate_blob, _decode(candidate_blob, "candidate"))
    baseline = None
    if baseline_blob is not None:
        baseline = _build_view(baseline_blob, _decode(baseline_blob, "baseline"))

    baseline_had_heading = baseline is not None and len(baseline.headings) == 1
    if not candidate.headings and not baseline_had_heading:
        sys.stdout.write("SKIP: no '%s' heading in the candidate - nothing to measure\n" % HEADING)
        return EXIT_OK

    verdict = _evaluate(candidate, baseline, options.skip_growth)

    if verdict is not None:
        sys.stderr.write("%s\n" % verdict)
        return EXIT_VERDICT

    sys.stdout.write("%s\n" % _ok_line(candidate))
    return EXIT_OK


def main(argument_list):
    """Map every foreseeable failure onto the 0 / 3 / 2 contract.

    ``except Exception`` deliberately does not catch SystemExit, and cannot run
    at all if this module fails at import - that case exits 1 (see ADR-010 in
    the module docstring above).
    """
    try:
        return _run(argument_list)
    except _InputError as error:
        return _could_not_run(str(error))
    except Exception as error:
        return _could_not_run("unexpected %s: %s" % (type(error).__name__, error))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
