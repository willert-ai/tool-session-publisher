#!/bin/bash
#
# run.sh — one ambient tick of the x-comms engine.
#
# A launchd user agent wakes this on a calendar schedule with zero Claude Code
# sessions open. The tick expires the queue, mines seeds, drafts finished post
# bodies headlessly, and writes exactly one structured line to the tick log.
# It never publishes, and it never logs a post body.
#
#     queue.py expire  ->  mine.py  ->  draft.py  ->  queue.py list  ->  tick line
#
# One calendar entry drives both cadences: Sunday is the deep tick (14-day
# window, drafted as one arc), every other day is the ambient tick (3-day
# window, standalone singles). launchd cannot tell the script which schedule
# entry fired, so a second entry would double-fire on Sunday — the weekday
# branch below is deliberate, not a convenience.
#
# Nothing personal is hardcoded here. Every path comes from the environment,
# which the plist supplies; run.sh refuses to run rather than fall back to a
# default that would silently write the queue somewhere else.
#
# Environment (required — no defaults, on purpose):
#     SESSION_PUBLISHER_NOTES_DIR   notes root; the queue lives under
#                                   <notes>/posts/x/queue/. launchd inherits
#                                   nothing from the login shell, so an unset
#                                   value would silently queue into
#                                   ~/personal-notes.
#     SESSION_PUBLISHER_TZ          IANA zone for every timestamp the helpers
#                                   stamp. Unset means UTC, which is wrong
#                                   quietly rather than loudly.
#
# Environment (optional):
#     X_COMMS_CLI        headless CLI, default `claude`. launchd's PATH is
#                        minimal, so the plist should pass an absolute path;
#                        whatever resolves here is exported absolute to draft.py.
#     X_COMMS_PYTHON     interpreter, default /usr/bin/python3 (always present
#                        on macOS and independent of PATH, pyenv and nvm).
#     X_COMMS_LOG_DIR    log directory, default $HOME/Library/Logs/ai.fero.x-comms
#     X_COMMS_FORCE_SEED `1` skips mining and drafts the fixture seed instead —
#                        the test hook that proves the trigger path independently
#                        of whether the miner had anything to say today. launchd
#                        cannot pass this in, so a one-shot marker file at
#                        $X_COMMS_LOG_DIR/force-seed arms the same hook for a
#                        kickstart; see the logging section.
#     X_COMMS_MODEL / X_COMMS_TIMEOUT   passed through to draft.py.
#
# Usage:
#     run.sh                  # weekday branch decides the mode
#     run.sh --mode ambient   # force the daily cadence (test hook)
#     run.sh --mode deep      # force the Sunday cadence (test hook)
#
# Exit: 0 when the tick completed (including "nothing to draft", which is a
# correct outcome), 1 when the tick could not run — both write a tick line first.
# 64 is a usage error (bad argument), which happens before the log directory is
# even resolved and deliberately writes no tick line: nothing ticked.

set -u
set -o pipefail

# D8: the two cadences. mine's cap matches draft's cap so the deep tick does not
# pay for candidate seeds the arc call can never use, and the ambient tick never
# reports a skip for a seed it never intended to draft.
AMBIENT_DAYS=3
AMBIENT_DRAFTS=2
DEEP_DAYS=14
DEEP_DRAFTS=3

usage() {
    cat <<'USAGE'
run.sh — one ambient tick of the x-comms engine.

    run.sh                  weekday branch decides the mode (Sunday = deep)
    run.sh --mode ambient   force the daily cadence: mine 3 days, draft <=2 singles
    run.sh --mode deep      force the Sunday cadence: mine 14 days, draft <=3 as an arc

Required environment: SESSION_PUBLISHER_NOTES_DIR, SESSION_PUBLISHER_TZ.
Optional: X_COMMS_CLI, X_COMMS_PYTHON, X_COMMS_LOG_DIR, X_COMMS_FORCE_SEED,
X_COMMS_MODEL, X_COMMS_TIMEOUT. See the comment header for what each one does.

Under launchd, arm the fixture hook with a one-shot marker instead of the
variable — launchctl setenv does not reach a gui/ agent:

    touch "${X_COMMS_LOG_DIR:-$HOME/Library/Logs/ai.fero.x-comms}/force-seed"
    launchctl kickstart -k "gui/$UID/ai.fero.x-comms"
USAGE
}

# --- arguments --------------------------------------------------------------

usage_error() {
    printf 'run.sh: %s\n' "$1" >&2
    exit 64
}

# MODE_SET distinguishes "--mode was given" from "--mode was given empty": bash
# has no way to tell `--mode=` from an absent flag once the value is extracted,
# and silently falling through to the weekday branch for a typo'd flag is the
# kind of wrong that only shows up as a surprising Sunday.
MODE=""
MODE_SET=0
while [ $# -gt 0 ]; do
    case "$1" in
        # NOT `shift 2`: in bash 3.2 a shift past the end of the argument list
        # FAILS and shifts nothing, and with no `set -e` that turns this loop
        # into an infinite one — upstream of the EXIT trap, so the job would spin
        # forever with no tick line and block every later calendar fire.
        --mode)
            [ $# -ge 2 ] || usage_error "--mode needs a value (ambient or deep)"
            MODE="$2"; MODE_SET=1; shift; shift ;;
        --mode=*) MODE="${1#--mode=}"; MODE_SET=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) usage_error "unknown argument: $1" ;;
    esac
done

if [ "$MODE_SET" -eq 1 ]; then
    case "$MODE" in
        ambient|deep) ;;
        *) usage_error "--mode must be ambient or deep, got: '$MODE'" ;;
    esac
fi

# When the mode was NOT given, it is resolved further down, after the environment
# block: the weekday branch has to read the clock in SESSION_PUBLISHER_TZ, and
# that variable is not validated yet. Until then the tick line says `pending`
# rather than guessing a cadence. An explicit --mode is already final.
if [ "$MODE_SET" -eq 0 ]; then MODE="pending"; fi

FORCED=0
[ "${X_COMMS_FORCE_SEED:-}" = "1" ] && FORCED=1

# --- logging ----------------------------------------------------------------
# Set up before anything that can fail, so a failed tick still leaves a line.
#
# The tick line is written here rather than to stdout on purpose. launchd opens
# StandardOutPath *before* exec'ing this script, so on a first run — or after
# someone clears ~/Library/Logs — the redirect fails and the one line that says
# what happened is the line that disappears. The stdout/stderr redirects still
# earn their keep: they carry helper diagnostics, which is where a reason code
# gets its detail.

LOG_DIR="${X_COMMS_LOG_DIR:-$HOME/Library/Logs/ai.fero.x-comms}"
mkdir -p "$LOG_DIR" 2>/dev/null
TICK_LOG="$LOG_DIR/tick.log"
# `2>/dev/null` first: redirections are applied left to right, and a failing
# append reports itself on whatever stderr is at that moment. Silencing it
# afterwards silences nothing.
if ! : 2>/dev/null >> "$TICK_LOG"; then
    # Losing the log must not lose the tick. Fall back to stderr, which launchd
    # is redirecting anyway. `>&2` rather than a path: /dev/stderr is a symlink
    # to /dev/fd/2 and opening it for append is not portable.
    TICK_LOG="-"
fi

# The second half of the test hook. launchd offers no way to pass a one-off
# variable into a job: `launchctl setenv X_COMMS_FORCE_SEED 1` does not reach a
# gui/ agent's environment — verified here, a kickstart after setenv still mined
# normally — and arming the hook by editing the plist would leave the engine
# armed. So a marker file arms exactly one tick, and it is consumed BEFORE
# anything else can fail:
#
#     touch ~/Library/Logs/ai.fero.x-comms/force-seed
#     launchctl kickstart -k gui/$UID/ai.fero.x-comms
#
# Arming is conditional on the removal SUCCEEDING. A marker in a directory the
# job cannot write to would otherwise arm every tick from here to eternity —
# silently, since the whole point of the hook is to bypass the miner.
FORCE_MARKER="$LOG_DIR/force-seed"
FORCE_MARKER_STUCK=0
if [ -f "$FORCE_MARKER" ]; then
    if rm -f "$FORCE_MARKER" 2>/dev/null && [ ! -e "$FORCE_MARKER" ]; then
        FORCED=1
    else
        FORCE_MARKER_STUCK=1
    fi
fi
if [ "$FORCED" -eq 1 ]; then
    # draft.py reads the fixture only when this is set AND no seed source is
    # passed, so both halves of the forced branch have to agree.
    export X_COMMS_FORCE_SEED=1
fi

# `incomplete`, not `ok`. Every clean exit promotes it explicitly; anything that
# kills the script between here and there — SIGTERM from launchd's ExitTimeOut,
# a logout, a `launchctl kill` — still fires the EXIT trap and still writes a
# line, and that line must not claim the tick succeeded.
STATUS="incomplete"
REASON="-"
SEEDS_MINED="-"
# How many of the mined seeds carried a resolved session document rather than
# degrading to the thin SESSION_INDEX row. `mine.py` degrades silently by
# design — a missing or ambiguous document must never fail a tick — so without
# this field a regression in document resolution (a wrap-up naming-convention
# change, a dropped `SESSION_` marker) would produce ticks that read exactly
# like healthy ones while quietly drafting from ~5% of the material again.
# That is the failure this whole path exists to correct, so it gets a counter.
DOCS="-"
DRAFTED="-"
SKIPPED="-"
REJECTED="-"
ERRORS="-"
EXPIRED="-"
QUEUED="-"
TICK_EMITTED=0
WORK=""
LOCK_HELD=""

# Every other timestamp in this pipeline is stamped in SESSION_PUBLISHER_TZ
# (queue.py, mine.py's window and its git-log day boundary). A tick line in the
# host's zone would be in a different zone than the `created_at` of the entries
# that very tick wrote — confusing in exactly the situation the log exists for.
now_ts() {
    if [ -n "${SESSION_PUBLISHER_TZ:-}" ]; then
        TZ="$SESSION_PUBLISHER_TZ" date +%Y-%m-%dT%H:%M:%S%z
    else
        date +%Y-%m-%dT%H:%M:%S%z
    fi
}

emit_tick() {
    if [ "$TICK_EMITTED" -eq 1 ]; then return 0; fi
    TICK_EMITTED=1
    # D9: every field is a count or a reason-code slug. No body, no seed_ref, no
    # path — the tick log is the operator's only view of an unattended run and is
    # kept publishable so it can be read anywhere.
    local line
    line="$(printf '%s mode=%s forced=%s status=%s reason=%s seeds_mined=%s docs=%s drafted=%s skipped=%s rejected=%s errors=%s expired=%s queued=%s' \
        "$(now_ts)" "$MODE" "$FORCED" "$STATUS" "$REASON" \
        "$SEEDS_MINED" "$DOCS" "$DRAFTED" "$SKIPPED" "$REJECTED" "$ERRORS" \
        "$EXPIRED" "$QUEUED")"
    if [ "$TICK_LOG" = "-" ]; then
        printf '%s\n' "$line" >&2
    else
        printf '%s\n' "$line" >> "$TICK_LOG"
    fi
}

on_exit() {
    emit_tick
    if [ -n "$WORK" ]; then rm -rf "$WORK"; fi
    # Only ever release a lock this process actually took: the not-my-lock exit
    # above leaves LOCK_HELD empty, so it cannot free the running tick's lock.
    if [ -n "$LOCK_HELD" ]; then rm -rf "$LOCK_HELD"; fi
    return 0
}
trap on_exit EXIT

# A killed tick reaches the EXIT trap with STATUS untouched. Name the signal so
# the line reads as the interruption it was; the EXIT trap then writes it.
on_signal() {
    STATUS="interrupted"
    REASON="signal:$1"
    exit "$2"
}
trap 'on_signal TERM 143' TERM
trap 'on_signal INT 130' INT
trap 'on_signal HUP 129' HUP

fail() {
    STATUS="failed"
    REASON="$1"
    shift
    printf 'run.sh: %s\n' "$*" >&2
    exit 1
}

# Promote the pessimistic default exactly once, and never over a status a real
# outcome already set (idle / no_output / capacity / failed).
finish_ok() {
    if [ "$STATUS" = "incomplete" ]; then STATUS="ok"; fi
}

# Append a run.sh-level code to the same comma-joined field the helpers' reason
# codes land in. These are conditions the tick survived but the operator should
# still see — they would otherwise be visible nowhere at all.
note_code() {
    if [ "$REJECTED" = "-" ]; then REJECTED="$1"; else REJECTED="$REJECTED,$1"; fi
}

# --- environment ------------------------------------------------------------

PYTHON="${X_COMMS_PYTHON:-/usr/bin/python3}"
if ! "$PYTHON" -c 'raise SystemExit(0)' >/dev/null 2>&1; then
    fail env:python "cannot run interpreter '$PYTHON' — set X_COMMS_PYTHON to an absolute path"
fi

if [ -z "${SESSION_PUBLISHER_NOTES_DIR:-}" ]; then
    fail env:notes_dir "SESSION_PUBLISHER_NOTES_DIR is not set; refusing to queue into the default"
fi
if [ ! -d "$SESSION_PUBLISHER_NOTES_DIR" ]; then
    fail env:notes_dir "SESSION_PUBLISHER_NOTES_DIR does not point at a directory"
fi
if [ -z "${SESSION_PUBLISHER_TZ:-}" ]; then
    fail env:tz "SESSION_PUBLISHER_TZ is not set; refusing to stamp the queue in UTC"
fi
export SESSION_PUBLISHER_NOTES_DIR SESSION_PUBLISHER_TZ

# D1's load-bearing dependency. Resolve it to an absolute path here so draft.py's
# subprocess call does not depend on the PATH launchd happened to hand us, and so
# a missing CLI is one clear reason code instead of one failure per seed.
CLI="${X_COMMS_CLI:-claude}"
CLI_PATH="$(command -v "$CLI" 2>/dev/null)"
# `command -v ./foo` answers `./foo`, and `-x ./foo` is true from whatever
# directory we happen to be in — but draft.py runs the CLI with cwd set to a
# fresh temp dir, where a relative path resolves to nothing. Insisting on an
# absolute path here is what makes the one-reason-code promise true.
case "$CLI_PATH" in
    /*) ;;
    *) fail env:cli "headless CLI '$CLI' did not resolve to an absolute path — set X_COMMS_CLI to one" ;;
esac
if [ ! -x "$CLI_PATH" ]; then
    fail env:cli "headless CLI '$CLI' not found or not executable — set X_COMMS_CLI to an absolute path"
fi
X_COMMS_CLI="$CLI_PATH"
export X_COMMS_CLI

HELPERS_DIR="$(cd "$(dirname "$0")/../helpers" 2>/dev/null && pwd -P)"
if [ -z "$HELPERS_DIR" ]; then
    fail env:helpers "cannot resolve the helpers directory relative to $0"
fi
for helper in queue.py mine.py draft.py; do
    if [ ! -f "$HELPERS_DIR/$helper" ]; then
        fail env:helpers "missing helper: $helper"
    fi
done

# --- mode ------------------------------------------------------------------
# D8's weekday branch, resolved only now: `date +%u` has to read the clock in
# SESSION_PUBLISHER_TZ, the same zone mine.py windows on. Reading it in the
# host's zone means that on a host whose zone straddles midnight against the
# operator's, the tick picks the deep cadence on a day the miner does not
# consider Sunday.
if [ "$MODE_SET" -eq 0 ]; then
    if [ "$(TZ="$SESSION_PUBLISHER_TZ" date +%u)" = "7" ]; then MODE="deep"; else MODE="ambient"; fi
fi
case "$MODE" in
    ambient) DAYS="$AMBIENT_DAYS"; MAX_DRAFTS="$AMBIENT_DRAFTS"; DRAFT_MODE="single" ;;
    deep)    DAYS="$DEEP_DAYS";    MAX_DRAFTS="$DEEP_DRAFTS";    DRAFT_MODE="arc" ;;
    # Unreachable — the flag was validated at parse time and the weekday branch
    # only yields these two — but `set -u` would turn a future edit that broke
    # that into an unbound-variable death with no reason code.
    *) fail env:mode "mode did not resolve to ambient or deep" ;;
esac

# --- single-instance lock ---------------------------------------------------
# launchd will not overlap a job with itself, but nothing stops a hand-run tick
# (which the README actively invites) from landing on a scheduled one. Two ticks
# a second apart both mine the same seeds — neither has ledgered anything yet —
# and both draft them: duplicate entries, duplicate headless calls, and the
# operator reviewing the same session twice.
#
# `mkdir` is the atomic primitive here; the pid file makes the lock recoverable.
# A lock whose owner is gone is stale by definition, and breaking it beats the
# alternative of one crashed tick wedging every future one.
LOCK_DIR="$LOG_DIR/.lock"
if mkdir "$LOCK_DIR" 2>/dev/null; then
    LOCK_HELD="$LOCK_DIR"
else
    OWNER="$(cat "$LOCK_DIR/pid" 2>/dev/null || echo "")"
    if [ -n "$OWNER" ] && kill -0 "$OWNER" 2>/dev/null; then
        STATUS="locked"
        REASON="lock:held"
        printf 'run.sh: another tick (pid %s) is running; exiting\n' "$OWNER" >&2
        exit 0
    fi
    rm -rf "$LOCK_DIR" 2>/dev/null
    if mkdir "$LOCK_DIR" 2>/dev/null; then
        LOCK_HELD="$LOCK_DIR"
        printf 'run.sh: broke a stale lock (owner %s is gone)\n' "${OWNER:-unknown}" >&2
    else
        # Could not take the lock and nobody holds it — the log directory itself
        # is unwritable. Proceed anyway: the lock guards against duplicate work,
        # not against corruption (queue.py handles concurrent writers), so
        # refusing to draft here would turn a cosmetic problem into an outage.
        note_code lock:unavailable
        printf 'run.sh: proceeding without a lock (cannot write the lock dir)\n' >&2
    fi
fi
if [ -n "$LOCK_HELD" ]; then echo $$ > "$LOCK_HELD/pid" 2>/dev/null; fi

WORK="$(mktemp -d "${TMPDIR:-/tmp}/x-comms.XXXXXX")" || fail env:tmpdir "cannot create a working directory"

# --- report readers ---------------------------------------------------------
# The helpers all speak JSON on stdout. Their reports carry seed_ref and body
# text, so they are read into $WORK and never echoed; only counts and reason
# codes come back out of these two functions.

jfield() {  # jfield <report> <dotted.path> [default]
    "$PYTHON" - "$1" "$2" "${3:--}" <<'PY'
import json, re, sys

try:
    with open(sys.argv[1], encoding="utf-8") as handle:
        value = json.load(handle)
except Exception:
    # Distinguishable from a legitimate 0: a truncated report is not a quiet day.
    print("report:unreadable")
    raise SystemExit(0)
for part in sys.argv[2].split("."):
    if not isinstance(value, dict):
        value = None
        break
    value = value.get(part)
if value is None:
    print(sys.argv[3])
elif isinstance(value, (list, tuple, dict)):
    print(len(value))
elif isinstance(value, str):
    # Same clamp jreasons applies, for the same reason: `reason=` also takes a
    # helper-supplied string, and one containing a space would split the field
    # while one containing a newline would turn one tick line into two.
    print(re.sub(r"\s+", "_", value.replace(",", ";")).strip()[:48] or sys.argv[3])
else:
    print(value)
PY
}

jreasons() {  # jreasons <report>
    "$PYTHON" - "$1" <<'PY'
import json, re, sys

codes = []
try:
    with open(sys.argv[1], encoding="utf-8") as handle:
        data = json.load(handle)
except Exception:
    print("report:unreadable")
    raise SystemExit(0)
if data.get("status") != "ok" and data.get("reason_code"):
    codes.append(data["reason_code"])
for item in (data.get("skipped") or []) + (data.get("errors") or []):
    if isinstance(item, dict) and item.get("reason"):
        codes.append(item["reason"])
# Most of draft.py's skip reasons come from a fixed vocabulary, but not all:
# `gate:unsourced_number:` appends the offending digit runs comma-separated, and a
# raw comma inside a code would silently split the comma-joined `rejected=` field
# into two codes that never existed. Commas become `;`, whitespace becomes `_`,
# and the whole code is capped — the tick line stays one parseable record whatever
# upstream decides a reason code may contain.
out, seen = [], set()
for code in codes:
    code = re.sub(r"\s+", "_", str(code).replace(",", ";")).strip()[:48]
    if code and code not in seen:
        seen.add(code)
        out.append(code)
print(",".join(out) or "-")
PY
}

queue_depth() {  # queued-entry count for the tick line; "-" if the queue cannot be read
    local listing="$WORK/list.json"
    if "$PYTHON" "$HELPERS_DIR/queue.py" list > "$listing" 2>/dev/null; then
        jfield "$listing" counts.queued 0
    else
        printf '%s\n' "-"
    fi
}

# --- 1. expire --------------------------------------------------------------
# D3: run.sh is the single mover for expiry, and it runs before drafting so a
# tick that frees capacity can use it in the same pass.

EXPIRE_JSON="$WORK/expire.json"
"$PYTHON" "$HELPERS_DIR/queue.py" expire > "$EXPIRE_JSON"
EXPIRE_RC=$?
if [ "$EXPIRE_RC" -ne 0 ]; then
    # Expiry is housekeeping. Note it and carry on: drafting will report its own
    # failure if the queue is genuinely unusable.
    EXPIRED="err"
    note_code "expire:exit_$EXPIRE_RC"
else
    EXPIRED="$(jfield "$EXPIRE_JSON" expired 0)"
fi

# --- 2. seeds ---------------------------------------------------------------

SEEDS_JSON="$WORK/seeds.json"
if [ "$FORCED" -eq 0 ]; then
    "$PYTHON" "$HELPERS_DIR/mine.py" --days "$DAYS" --max-seeds "$MAX_DRAFTS" > "$SEEDS_JSON"
    MINE_RC=$?
    if [ "$MINE_RC" -ne 0 ]; then
        fail "$(jfield "$SEEDS_JSON" reason_code "mine:exit_$MINE_RC")" "mine.py failed; see the stderr log"
    fi
    # mine.py exiting 0 with an unparseable report would otherwise read as a
    # quiet day. jfield says `report:unreadable`; treat that as the failure it is.
    if [ "$(jfield "$SEEDS_JSON" status "-")" != "ok" ]; then
        fail mine:unreadable_report "mine.py exited 0 but its report is not a healthy JSON object"
    fi
    SEEDS_MINED="$(jfield "$SEEDS_JSON" seeds 0)"
    DOCS="$(jfield "$SEEDS_JSON" with_document 0)"
    if [ "$SEEDS_MINED" = "0" ]; then
        # Smoke #5: a tick with nothing fresh to say is a correct outcome. Say so
        # in the status field so a quiet day is not read as a broken engine.
        STATUS="idle"
        DRAFTED=0
        SKIPPED=0
        ERRORS=0
        QUEUED="$(queue_depth)"
        exit 0
    fi
fi

# --- 3. draft ---------------------------------------------------------------
# X_COMMS_FORCE_SEED only reaches the fixture when no seed source is passed, so
# the forced branch deliberately calls draft.py with no --seeds-file.

DRAFT_JSON="$WORK/draft.json"
if [ "$FORCED" -eq 1 ]; then
    "$PYTHON" "$HELPERS_DIR/draft.py" --mode "$DRAFT_MODE" --max-drafts "$MAX_DRAFTS" > "$DRAFT_JSON"
else
    "$PYTHON" "$HELPERS_DIR/draft.py" --mode "$DRAFT_MODE" --max-drafts "$MAX_DRAFTS" \
        --seeds-file "$SEEDS_JSON" > "$DRAFT_JSON"
fi
DRAFT_RC=$?

DRAFTED="$(jfield "$DRAFT_JSON" drafted 0)"
SKIPPED="$(jfield "$DRAFT_JSON" skipped 0)"
ERRORS="$(jfield "$DRAFT_JSON" errors 0)"
DRAFT_REASONS="$(jreasons "$DRAFT_JSON")"
if [ "$DRAFT_REASONS" != "-" ]; then note_code "$DRAFT_REASONS"; fi
if [ "$FORCED" -eq 1 ]; then
    SEEDS_MINED="$(jfield "$DRAFT_JSON" seeds 0)"
fi

case "$DRAFT_RC" in
    0)
        # draft.py reports `queued_before` on exactly one path: the D8 capacity
        # skip. A full queue and a productive tick are both `ok` otherwise, and
        # only one of them is a reason to go look at the queue.
        if [ "$(jfield "$DRAFT_JSON" queued_before "-")" != "-" ]; then
            STATUS="capacity"
        fi
        ;;
    2) STATUS="no_output" ;;  # the tick ran; no seed produced a postable body
    *) STATUS="failed"; REASON="$(jfield "$DRAFT_JSON" reason_code "draft:exit_$DRAFT_RC")" ;;
esac

# --- 4. queue depth ---------------------------------------------------------

QUEUED="$(queue_depth)"

if [ "$FORCE_MARKER_STUCK" -eq 1 ]; then
    # Not fatal — the tick ran normally, unforced — but the marker is still there
    # and the operator's next arming attempt will look like it worked. Say it in
    # the line rather than nowhere.
    note_code marker:stuck
fi

if [ "$STATUS" = "failed" ]; then exit 1; fi
finish_ok
exit 0
