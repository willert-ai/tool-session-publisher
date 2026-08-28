#!/usr/bin/env bash
#
# Surface the queue, don't fill it. Every morning at 07:45 this asks whether to review
# what the 07:30 tick drafted — and, when the tick did not happen, says so out loud.
# It never drafts, never approves, and never publishes.
#
# WHY THIS IS NOT THE VOICE-DISCOVERY REMINDER, DESPITE LOOKING LIKE IT. Its sibling
# `rls_reminder.sh` exists because `check_rls.sh` CANNOT run unattended: it needs `op
# read`, which needs a human for Touch ID. There, the prompt IS the trigger. Here the
# opposite holds — `run.sh` already fires unattended at 07:30 and has done so with
# nobody present (2026-08-27, 2026-08-28). What cannot be automated is the *judgement*:
# whether a draft is publishable is the operator's call and nothing else's.
#
# So this prompt is not an activation. It is the report the tick has never had. Today a
# failed tick is invisible until somebody opens `tick.log`, and nobody opens `tick.log`
# — the same silent-death shape the sibling script spends forty lines guarding against,
# reproduced one project over.
#
# THE THREE OUTCOMES, AND WHY THE QUIET ONE MATTERS MOST.
#
#   posts waiting          -> dialog: review them          [Later] [Review now]
#   nothing, everything ok -> NO DIALOG. one line in the log.
#   anything else          -> dialog: something is wrong   [Ignore] [Show log]
#
# "Anything else" is deliberately broad, and both halves of it were once holes:
#   - the tick did not happen, is stale, reported a status outside the healthy set, or
#     carries errors=N; and
#   - the QUEUE cannot be seen — directory absent (a synced drive not mounted), not
#     readable, or entries that will not parse. Each of those otherwise arrives as
#     count=0, which is indistinguishable from an empty queue and takes the quiet path.
#
# The middle case is silent on purpose, and it is the common case: the engine's own
# quality gates reject roughly two-thirds of what it attempts, so an empty queue is the
# filter working rather than a fault. A dialog that appears on a morning with nothing to
# decide is a dialog you learn to dismiss without reading — and the third case, the one
# that actually needs your eyes, arrives in the same window you have trained yourself to
# click away. Restraint here is what keeps the alert legible.
#
# WHY STALENESS IN HOURS AND NOT "DID IT RUN TODAY". Because `StartCalendarInterval`
# defers to the next wake, a laptop opened at 14:00 fires the 07:30 tick and this 07:45
# reminder at nearly the same moment, in an order launchd does not promise. "No line
# dated today" would therefore cry failure every time you open the lid late — which is
# most days. A 36-hour ceiling tolerates that race by construction: yesterday's tick is
# ~30h old at 14:00 and reads as healthy, while a genuinely dead engine crosses 36h and
# alerts. The bounded wait below closes the remaining gap.
#
# WHY IT WAITS WHILE THE ENGINE IS RUNNING. On a cold wake both jobs start together and
# a drafting call takes minutes, so reading the queue immediately reports the state from
# *before* the tick this reminder is supposed to be reporting on. It polls while
# `ai.fero.x-comms` is resident-and-running, capped, then decides. The cap matters: an
# engine wedged forever must not wedge the reminder too, because a reminder that never
# appears is indistinguishable from one that decided there was nothing to say.
#
# WHY IT READS ITS CONFIGURATION OUT OF THE ENGINE'S PLIST. The notes directory, the
# Python interpreter and the tick-log path are all already stated in
# `ai.fero.x-comms.plist`, which calls itself "the single source of the path". Copying
# those three values into a second plist creates a second source that drifts silently —
# and the failure it produces is this reminder counting an empty queue somewhere the
# engine never writes, then reporting "nothing today" forever. Read them; do not
# restate them.
#
# WHY StartCalendarInterval AND NOT StartInterval — the same correction the sibling
# documents, and it applies with more force here because this schedule is daily. From
# `man launchd.plist`: StartInterval MISSES an interval that elapses while asleep;
# StartCalendarInterval defers it to the next wake and COALESCES multiple missed ones
# into a single event. A closed laptop must not silently skip the day's review.
#
# Install:    bash skill/engine/review_reminder.sh --install
# Status:     bash skill/engine/review_reminder.sh --status
# Uninstall:  bash skill/engine/review_reminder.sh --uninstall
# Test now:   bash skill/engine/review_reminder.sh

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
QUEUE_HELPER="$REPO_ROOT/skill/helpers/queue.py"

LABEL="ai.fero.x-comms-review"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"

ENGINE_LABEL="ai.fero.x-comms"
ENGINE_PLIST="$HOME/Library/LaunchAgents/$ENGINE_LABEL.plist"

# `~/Library/Logs`, never `/tmp`: /tmp is cleared at boot, and on the quiet mornings
# this script writes a log line INSTEAD of showing a dialog, that line is the only
# evidence it ran at all. Losing it to a reboot would make "silent because healthy"
# and "silent because broken" the same observation.
LOG_DIR="${X_COMMS_REVIEW_LOG_DIR:-$HOME/Library/Logs}"
LOG="$LOG_DIR/$LABEL.log"

# Hours after which a missing tick is a problem rather than a late wake. See the header.
STALE_HOURS="${X_COMMS_REVIEW_STALE_HOURS:-36}"
# Seconds to wait out an in-flight tick before deciding. Capped, deliberately.
WAIT_MAX="${X_COMMS_REVIEW_WAIT:-600}"
# Seconds to wait for a due-but-not-yet-started engine to appear. Shorter than WAIT_MAX:
# this covers a launchd start-order race, not a slow drafting call.
WAIT_GRACE="${X_COMMS_REVIEW_GRACE:-180}"
WAIT_STEP=15

# --- escaping, once, correctly -----------------------------------------------
# Two grammars, two escapes, and they are not interchangeable. bash's `printf %q`
# renders `My\ Drive`, which AppleScript refuses to COMPILE (-2741) — before any Apple
# event is sent, so the failure does not even reach the dialog layer.

# A string literal for AppleScript: backslashes first, then quotes — and then newlines,
# which the sibling script never had to handle because its dialog text was assembled in
# AppleScript with `& return &`. Ours is assembled in bash, and an AppleScript literal
# CANNOT contain a raw newline: it is a compile error (-2741), so the dialog never
# appears and the failure looks identical to the operator dismissing it.
as_str() {
  local s=${1//\\/\\\\}
  s=${s//\"/\\\"}
  local out="" line first=1
  while IFS= read -r line || [ -n "$line" ]; do
    if [ "$first" -eq 1 ]; then out="$line"; first=0; else out="$out\" & return & \"$line"; fi
  done <<< "$s"
  printf '"%s"' "$out"
}

# Text content for the plist. A path containing & < > otherwise yields XML that
# `launchctl` rejects while reporting success.
xml_text() { local s=${1//&/&amp;}; s=${s//</&lt;}; printf '%s' "${s//>/&gt;}"; }

log() { mkdir -p "$LOG_DIR" 2>/dev/null; printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >>"$LOG"; }

# --- configuration, resolved from the engine rather than restated -------------

engine_var() {
  /usr/libexec/PlistBuddy -c "Print :EnvironmentVariables:$1" "$ENGINE_PLIST" 2>/dev/null
}

# Precedence: explicit environment, then the engine's plist, then a default.
#
# The environment step is the TEST SEAM, and it is first for the same reason the engine
# puts `X_COMMS_CLI` first — every branch below (waiting, stale, failed, unreadable
# queue) has to be reachable on a scratch directory without a scheduler, or it will
# only ever be exercised for the first time at 07:45 on a morning that matters.
#
# It costs nothing in production: this job's own plist sets no EnvironmentVariables
# beyond PATH, so under launchd the environment is empty and the engine's plist wins
# every value. Running it by hand from a shell that exports SESSION_PUBLISHER_NOTES_DIR
# picks that up, which is what a manual test should do.
resolve_config() {
  NOTES_DIR="${SESSION_PUBLISHER_NOTES_DIR:-}"
  [ -n "$NOTES_DIR" ] || NOTES_DIR="$(engine_var SESSION_PUBLISHER_NOTES_DIR)"
  [ -n "$NOTES_DIR" ] || NOTES_DIR="$HOME/personal-notes"

  PYTHON="${X_COMMS_PYTHON:-}"
  [ -n "$PYTHON" ] && [ -x "$PYTHON" ] || PYTHON="$(engine_var X_COMMS_PYTHON)"
  [ -n "$PYTHON" ] && [ -x "$PYTHON" ] || PYTHON="$(command -v python3 2>/dev/null)"

  local tick_dir
  tick_dir="${X_COMMS_LOG_DIR:-}"
  [ -n "$tick_dir" ] || tick_dir="$(engine_var X_COMMS_LOG_DIR)"
  [ -n "$tick_dir" ] || tick_dir="$HOME/Library/Logs/$ENGINE_LABEL"
  TICK_LOG="$tick_dir/tick.log"
}

# --- reading the world --------------------------------------------------------

# The whole last line, or empty. run.sh writes one line per tick with a single
# O_APPEND write, so a torn read is not a case that needs handling here.
last_tick_line() { [ -f "$TICK_LOG" ] && tail -1 "$TICK_LOG" 2>/dev/null; }

# Age of that line in whole hours, or empty when it cannot be established. Empty is
# NOT treated as healthy downstream — an unparseable timestamp is a reason to speak up,
# not a reason to assume the best.
tick_age_hours() {
  local line ts t0 now
  line="$1"
  [ -n "$line" ] || return 0
  ts="${line%% *}"
  t0="$(date -j -f '%Y-%m-%dT%H:%M:%S%z' "$ts" +%s 2>/dev/null)"
  [ -n "$t0" ] || return 0
  now="$(date +%s)"
  printf '%s' $(( (now - t0) / 3600 ))
}

# `<key>=<value>` out of a tick line. run.sh clamps every field to a slug vocabulary
# with commas rewritten and whitespace collapsed, so a word-split is safe — but `set -f`
# is on for the split anyway: `rejected=` carries helper-supplied reason codes, and the
# clamp guarantees no whitespace, not the absence of `*?[`. Unset it on both exits.
tick_field() {
  local line="$1" key="$2" tok
  set -f
  for tok in $line; do
    case "$tok" in "$key="*) set +f; printf '%s' "${tok#*=}"; return 0 ;; esac
  done
  set +f
}

# THE HEALTH TEST IS AN ALLOWLIST, AND THAT IS THE WHOLE POINT.
#
# It was a denylist of one (`status = failed`) and that was a real hole, not a
# theoretical one. `run.sh` writes EIGHT statuses, not the four this comment used to
# claim: ok, idle, no_output, capacity, failed, locked, interrupted, incomplete. A
# denylist passed the last three as healthy.
#
#   locked        another tick's pid is still alive — a wedged engine
#   interrupted   SIGTERM/INT/HUP: lid closed mid-tick, logout, launchd ExitTimeOut
#   incomplete    killed before the status was ever promoted
#
# `locked` is the one that matters most, because it recurs every morning WITH A FRESH
# TIMESTAMP — so the staleness ceiling never trips and a permanently wedged engine stays
# silent forever. That is precisely the failure this script exists to end, reproduced
# inside it. `interrupted` is the likeliest on a laptop, and repeats the same way.
#
# An allowlist also fails closed on whatever status run.sh grows next, which is the
# asymmetry the header argues for: this may cry wolf, it may not go quiet.
tick_is_healthy() {
  local status="$1" age="$2" errors="$3"
  case "$status" in
  ok|idle|no_output|capacity) : ;;
  *) return 1 ;;
  esac
  # An unparseable or absent timestamp is unhealthy, not unknown-therefore-fine.
  [ -n "$age" ] || return 1
  # Negative means a clock or a SESSION_PUBLISHER_TZ offset moved under us. Silence on a
  # timestamp we cannot trust is the same defect as silence on a missing one.
  [ "$age" -ge 0 ] || return 1
  [ "$age" -lt "$STALE_HOURS" ] || return 1
  # `errors=N` on an otherwise-ok line is a partial failure the tick log records and
  # nothing else surfaces. Every line to date reads errors=0, so this costs nothing
  # today and catches a drafting call that died inside a tick that still completed.
  case "$errors" in ''|-|0) : ;; *) return 1 ;; esac
  return 0
}

engine_running() {
  launchctl print "$DOMAIN/$ENGINE_LABEL" 2>/dev/null | grep -qE '^[[:space:]]*state = running'
}

# True when the engine is loaded and no tick has landed since its own scheduled time
# today — i.e. it is expected to run and has not yet. The schedule is READ from the
# engine's plist rather than restated: hard-coding 07:30 here means moving the engine
# silently disables this wait, and the symptom would be an occasional unexplained quiet
# morning, which is close to unfindable.
engine_is_due() {
  local hour minute due last t0
  launchctl print "$DOMAIN/$ENGINE_LABEL" >/dev/null 2>&1 || return 1
  hour="$(/usr/libexec/PlistBuddy -c 'Print :StartCalendarInterval:Hour' "$ENGINE_PLIST" 2>/dev/null)"
  minute="$(/usr/libexec/PlistBuddy -c 'Print :StartCalendarInterval:Minute' "$ENGINE_PLIST" 2>/dev/null)"
  case "$hour" in ''|*[!0-9]*) return 1 ;; esac
  case "$minute" in ''|*[!0-9]*) minute=0 ;; esac
  due="$(date -j -f '%Y-%m-%d %H:%M:%S' "$(date +%Y-%m-%d) $(printf '%02d:%02d' "$hour" "$minute"):00" +%s 2>/dev/null)"
  [ -n "$due" ] || return 1
  # Not yet its time today — nothing is due, so nothing to wait for.
  [ "$(date +%s)" -ge "$due" ] || return 1
  last="$(last_tick_line)"
  [ -n "$last" ] || return 0
  t0="$(date -j -f '%Y-%m-%dT%H:%M:%S%z' "${last%% *}" +%s 2>/dev/null)"
  [ -n "$t0" ] || return 0
  [ "$t0" -lt "$due" ]
}

# Actionable entries = queued + approved-but-not-yet-copied. Both need an action from
# the operator, which is exactly what this reminder is counting. Asking queue.py rather
# than globbing the directory keeps the definition in the one file that owns it.
#
# THE COUNT ALONE IS NOT ENOUGH TO GO QUIET ON, which is why this returns three values.
# `queue.py list` exits 0 and reports `counts: {}` in three states that are NOT "nothing
# to review":
#
#   - the queue directory does not exist. `entry_paths()` returns [] for a non-directory
#     without erroring. The queue lives on a synced drive; if that drive is not mounted
#     at 07:45, an empty count is what "unmounted" looks like. The same follows from the
#     $HOME/personal-notes fallback if the engine plist is ever unreadable.
#   - the directory exists but cannot be read. Path.glob swallows PermissionError, so
#     real actionable entries report as zero.
#   - entries exist but do not parse. cmd_list files those under `unreadable` and
#     excludes them from `counts` — so a corrupted queue reads as an empty one.
#
# Reading configuration from the engine's plist prevents plist DRIFT; it does not
# prevent any of these. The queue_dir and unreadable count come back so the caller can
# tell "nothing to do" apart from "cannot see anything".
#
# Three lines rather than one, because queue_dir contains spaces and parentheses.
#
# The `cd "$REPO_ROOT"` is load-bearing for the `python3 -c` on the second call only:
# there sys.path[0] is '' (the cwd), so running it from skill/helpers would import that
# directory's `queue.py` in place of the stdlib `queue` that `json` pulls in. It does
# NOT protect the first call — sys.path[0] for a script is the SCRIPT's directory, and
# queue.py's own guard is what handles that. Do not relocate either call on the belief
# that the cd covers both.
queue_probe() {
  local json
  json="$(cd "$REPO_ROOT" && SESSION_PUBLISHER_NOTES_DIR="$NOTES_DIR" "$PYTHON" "$QUEUE_HELPER" list 2>>"$LOG")" || return 1
  (cd "$REPO_ROOT" && printf '%s' "$json" | "$PYTHON" -c '
import json, sys
d = json.load(sys.stdin)
print(sum(d.get("counts", {}).values()))
print(len(d.get("unreadable", [])))
print(d.get("queue_dir", ""))
' 2>>"$LOG") || return 1
}

# --- dialogs ------------------------------------------------------------------
# stderr is CAPTURED, not discarded. Swallowing it makes a TCC Automation denial
# (-1743), a missing GUI session and a non-scriptable System Events indistinguishable
# from the operator clicking "Later": all four produce an empty string and exit 0, and
# the log then records a cheerful "deferred" for a dialog nobody ever saw.
#
# It is captured to a FILE, not to a variable. `ask` is always called inside a command
# substitution — that is a subshell, so an assignment here would be discarded on return
# and the caller would report "no stderr" for every failure. Reintroducing, by way of
# the reporting channel, precisely the blindness this function is built to prevent.
# Under LOG_DIR, not ${TMPDIR:-/tmp}: with TMPDIR unset that is a fixed, predictable
# /tmp path this script truncates on every run, which anyone on the machine can
# pre-create. LOG_DIR already exists, is per-user, and survives a reboot.
DIALOG_ERR_FILE="$LOG_DIR/.$LABEL.dialog.err"

ask() {
  local title="$1" body="$2" left="$3" right="$4" icon="$5" timeout="$6"
  local answer rc
  : >"$DIALOG_ERR_FILE"
  answer="$(osascript 2>"$DIALOG_ERR_FILE" <<OSA
tell application "System Events"
  activate
  set r to display dialog $(as_str "$body") ¬
    with title $(as_str "$title") ¬
    buttons {$(as_str "$left"), $(as_str "$right")} ¬
    default button $(as_str "$right") ¬
    with icon $icon ¬
    giving up after $timeout
  if gave up of r then
    return "TIMEOUT"
  else
    return button returned of r
  end if
end tell
OSA
  )"
  rc=$?
  [ "$rc" -eq 0 ] || return "$rc"
  printf '%s' "$answer"
}

dialog_err() { cat "$DIALOG_ERR_FILE" 2>/dev/null; }

# A real Terminal window rather than text captured into an alert box. The review loop is
# interactive — six single-key actions, one entry at a time — so there is nothing to
# capture; and the tick line is evidence, which truncated into a dialog is how a
# "healthy" gets believed unread.
#
# It reuses DIALOG_ERR_FILE rather than calling `mktemp`. A failed `mktemp` takes the
# redirect down with it, and bash then fails the whole command BEFORE osascript runs —
# so the handler reports "could not launch Terminal" for a Terminal that was never
# asked. The diagnostic path must not be able to manufacture the fault it reports.
open_terminal() {
  : >"$DIALOG_ERR_FILE"
  if ! osascript -e 'tell application "Terminal" to activate' \
                 -e "tell application \"Terminal\" to do script $(as_str "$1")" >/dev/null 2>"$DIALOG_ERR_FILE"; then
    log "FAILED to launch Terminal: $(dialog_err)"
    printf 'ERROR: could not launch Terminal\n' >&2
    return 1
  fi
  return 0
}

# --- install / status / uninstall --------------------------------------------

case "${1:-}" in
--install)
  # Checked at INSTALL time, not only at prompt time. Arming a daily reminder against a
  # helper that is already gone is a next-morning discovery at best, and on the quiet
  # path it would fail into silence rather than into a dialog.
  [ -f "$QUEUE_HELPER" ] || { printf 'FATAL: %s not found — refusing to arm a reminder for a missing review loop\n' "$QUEUE_HELPER" >&2; exit 2; }
  [ -f "$ENGINE_PLIST" ] || { printf 'FATAL: %s not found — the drafting engine is not installed, so there would never be anything to review\n' "$ENGINE_PLIST" >&2; exit 2; }

  # The test seam must not reach the installed job. `X_COMMS_REVIEW_LOG_DIR` is honoured
  # everywhere else, but baking it into StandardOutPath/StandardErrorPath would put the
  # quiet-morning log line in a scratch directory that a reboot erases — which is exactly
  # what the LOG_DIR comment above forbids, arrived at by way of a stale shell export.
  # Installing always uses the real location.
  if [ -n "${X_COMMS_REVIEW_LOG_DIR:-}" ] && [ "$X_COMMS_REVIEW_LOG_DIR" != "$HOME/Library/Logs" ]; then
    printf 'NOTE: ignoring X_COMMS_REVIEW_LOG_DIR=%s for the install — the installed job logs to %s\n' \
      "$X_COMMS_REVIEW_LOG_DIR" "$HOME/Library/Logs" >&2
  fi
  LOG_DIR="$HOME/Library/Logs"
  LOG="$LOG_DIR/$LABEL.log"
  mkdir -p "$HOME/Library/LaunchAgents" "$LOG_DIR"

  resolve_config
  [ -n "$PYTHON" ] && [ -x "$PYTHON" ] || { printf 'FATAL: no usable python3 (engine plist X_COMMS_PYTHON, then PATH)\n' >&2; exit 2; }
  [ -d "$NOTES_DIR" ] || printf 'WARNING: notes dir does not exist yet: %s\n' "$NOTES_DIR" >&2

  # A warning, not a refusal: an unloaded engine is a real state to be told about, and
  # this reminder is precisely the thing that would tell you.
  launchctl print "$DOMAIN/$ENGINE_LABEL" >/dev/null 2>&1 || \
    printf 'WARNING: %s is not loaded — nothing will draft, and this reminder will alert every morning\n' "$ENGINE_LABEL" >&2

  # RunAtLoad stays false — installing must not throw a dialog while you are mid-task.
  # With a calendar schedule that costs nothing: tomorrow's 07:45 fires regardless of
  # when the job was loaded, which would NOT have been true of an interval timer.
  #
  # Two EnvironmentVariables only; every other value is read out of the engine's plist at
  # run time (see resolve_config).
  #
  # PATH, because launchd supplies almost none and `date`, `tail`, `grep`, `cut`, `sed`,
  # `osascript`, `plutil` and `launchctl` must resolve.
  #
  # HOME, for the same reason the engine's plist sets it: it is normally inherited in the
  # gui/ domain, but this script expands $HOME at the top level under `set -u`, before
  # the log function is ever callable — so a HOME-less spawn dies with `HOME: unbound
  # variable`, no dialog and no log line. Silent death, in the script whose entire job is
  # to prevent one.
  cat > "$PLIST" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$(xml_text "$LABEL")</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$(xml_text "$SCRIPT_DIR/review_reminder.sh")</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>HOME</key><string>$(xml_text "$HOME")</string>
    <key>PATH</key><string>/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key><integer>7</integer>
    <key>Minute</key><integer>45</integer>
  </dict>
  <key>RunAtLoad</key><false/>
  <key>StandardOutPath</key><string>$(xml_text "$LOG")</string>
  <key>StandardErrorPath</key><string>$(xml_text "$LOG")</string>
</dict>
</plist>
PLIST_EOF

  plutil -lint "$PLIST" >/dev/null 2>&1 || { printf 'FATAL: generated plist is malformed (path contains something unescaped?)\n' >&2; exit 2; }

  # `bootout`/`bootstrap`, NOT `load`/`unload`. The legacy pair exits 0 for a missing
  # plist, a malformed plist AND a valid plist that failed to bootstrap, so the obvious
  # `|| exit` guard is dead code and an unload-then-failed-load silently DISARMS the
  # reminder while printing "installed".
  launchctl bootout "$DOMAIN/$LABEL" >/dev/null 2>&1 || true
  boot_err="$LOG_DIR/.$LABEL.bootstrap.err"
  if ! launchctl bootstrap "$DOMAIN" "$PLIST" 2>"$boot_err"; then
    printf 'FATAL: bootstrap failed: %s\n' "$(cat "$boot_err" 2>/dev/null)" >&2
    printf '       (a GUI login session is required — this will not work over SSH)\n' >&2
    rm -f "$boot_err"
    exit 2
  fi
  rm -f "$boot_err"

  # Verify rather than assume. The entire reason for the bootout/bootstrap switch is a
  # trustworthy exit code; confirming residency costs one call and closes the gap.
  launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1 || { printf 'FATAL: bootstrap reported success but the job is not resident\n' >&2; exit 2; }

  log "installed, schedule daily 07:45, notes=$NOTES_DIR"
  printf 'installed and verified resident: %s\n' "$PLIST"
  printf 'prompts daily at 07:45 local (deferred to the next wake if asleep).\n'
  printf 'quiet when the queue is empty and the tick is healthy — that is by design.\n'
  printf 'notes dir:  %s\n' "$NOTES_DIR"
  printf 'tick log:   %s\n' "$TICK_LOG"
  printf 'log:        %s\n' "$LOG"
  printf 'test: bash skill/engine/review_reminder.sh    status: --status    remove: --uninstall\n'
  exit 0
  ;;

--status)
  ok=0
  resolve_config
  if [ -f "$PLIST" ]; then printf 'plist:      %s\n' "$PLIST"; else printf 'plist:      MISSING\n'; ok=1; fi
  if launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
    printf 'loaded:     yes (%s)\n' "$DOMAIN/$LABEL"
  else
    printf 'loaded:     NO — the reminder is not armed\n'; ok=1
  fi
  # The path is baked at install time. Move the repo and launchd runs a script that no
  # longer exists, every morning, forever, one line into a log nobody reads.
  # Guarded on the file existing: for a missing plist PlistBuddy prints "File Doesn't
  # Exist, Will Create:" to STDOUT, not stderr, so an unguarded read captures that
  # sentence as the baked path and reports a path mismatch that is really a missing
  # install — two different problems, one confusing message.
  baked=""
  [ -f "$PLIST" ] && baked="$(/usr/libexec/PlistBuddy -c 'Print :ProgramArguments:1' "$PLIST" 2>/dev/null || true)"
  if [ -n "$baked" ] && [ "$baked" != "$SCRIPT_DIR/review_reminder.sh" ]; then
    printf 'baked path: %s\n            DIFFERS from this checkout (%s) — re-run --install\n' "$baked" "$SCRIPT_DIR/review_reminder.sh"; ok=1
  elif [ -n "$baked" ]; then
    printf 'baked path: %s (matches)\n' "$baked"
  fi
  [ -f "$QUEUE_HELPER" ] && printf 'queue.py:   present\n' || { printf 'queue.py:   MISSING at %s\n' "$QUEUE_HELPER"; ok=1; }
  if launchctl print "$DOMAIN/$ENGINE_LABEL" >/dev/null 2>&1; then
    printf 'engine:     loaded (%s)\n' "$ENGINE_LABEL"
  else
    printf 'engine:     NOT loaded — nothing will draft\n'; ok=1
  fi
  printf 'notes dir:  %s\n' "$NOTES_DIR"
  printf 'python:     %s\n' "${PYTHON:-NONE FOUND}"
  printf 'tick log:   %s\n' "$TICK_LOG"
  line="$(last_tick_line)"
  if [ -n "$line" ]; then
    age="$(tick_age_hours "$line")"
    printf 'last tick:  %s\n' "${line%% *}"
    printf '            status=%s queued=%s age=%sh\n' "$(tick_field "$line" status)" "$(tick_field "$line" queued)" "${age:-?}"
  else
    printf 'last tick:  none — the engine has never written a tick line\n'; ok=1
  fi
  # Two queue numbers that legitimately disagree: the tick line's `queued=` is what the
  # engine saw when it finished, `queue: N waiting` is what is actionable NOW. They
  # differ whenever the operator has acted since, which is the normal case — labelled so
  # it reads as history-vs-now rather than as a contradiction.
  if n="$(queue_probe)"; then
    printf 'queue now:  %s waiting (the tick line above is what the engine saw when it ran)\n' "$(printf '%s\n' "$n" | sed -n 1p)"
    u="$(printf '%s\n' "$n" | sed -n 2p)"
    [ "${u:-0}" = "0" ] || { printf 'unreadable: %s entries cannot be parsed — invisible to the review loop\n' "$u"; ok=1; }
    q="$(printf '%s\n' "$n" | sed -n 3p)"
    [ -d "$q" ] || { printf 'queue dir:  MISSING at %s (synced drive not mounted?)\n' "$q"; ok=1; }
  else
    printf 'queue now:  COULD NOT READ\n'; ok=1
  fi
  [ -f "$LOG" ] && { printf 'last log lines:\n'; tail -3 "$LOG" | sed 's/^/  /'; } || printf 'log:        none yet (never fired)\n'
  exit $ok
  ;;

--uninstall)
  if launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null; then
    printf 'unloaded:   %s\n' "$DOMAIN/$LABEL"
  elif launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
    # Reported nothing to unload, yet still resident. Say so instead of deleting the
    # plist and leaving a loaded job with no backing file.
    printf 'FATAL: could not unload, and the job is still resident — plist left in place\n' >&2
    exit 2
  else
    printf 'unloaded:   (was not loaded)\n'
  fi
  rm -f "$PLIST"
  log "uninstalled"
  printf 'removed:    %s\n' "$PLIST"
  exit 0
  ;;

"") : ;;  # no argument: fall through to the prompt

*)
  printf 'unknown option: %s\n' "$1" >&2
  printf 'usage: review_reminder.sh [--install | --status | --uninstall]   (no argument prompts now)\n' >&2
  exit 2
  ;;
esac

# --- the prompt --------------------------------------------------------------

resolve_config

# A missing review loop must be LOUDER than a due one, not quieter. From a launchd fire
# there is no terminal, so stderr alone reaches nobody — the dialog is the only channel.
if [ ! -f "$QUEUE_HELPER" ] || [ -z "$PYTHON" ] || [ ! -x "$PYTHON" ]; then
  log "FATAL cannot run the review loop (queue.py=$QUEUE_HELPER python=${PYTHON:-none})"
  osascript -e "display alert \"x-comms — review loop unavailable\" message $(as_str "queue.py or python3 could not be found. The reminder is armed but has nothing to open.") as critical" 2>>"$LOG" >/dev/null
  printf 'FATAL: queue.py or python3 not usable\n' >&2
  exit 2
fi

# Wait out the tick. See the header: on a cold wake both jobs start together, and
# deciding first would report the queue as it was BEFORE the tick this reminder exists
# to report on.
#
# TWO WAITS, because there are two orderings and only one of them is "already running".
# If launchd starts this job first, the engine has not begun, `engine_running` is false
# immediately, and a single loop would decide on the pre-tick queue — reporting a quiet
# morning while the tick then files posts that wait an extra day. So: first give a
# not-yet-started engine a bounded grace to appear, but only when it is loaded AND no
# tick has landed since its own scheduled time today (read from its plist, not restated
# here). Then wait while it runs.
if engine_is_due; then
  grace=0
  while [ "$grace" -lt "$WAIT_GRACE" ] && ! engine_running; do
    sleep "$WAIT_STEP"
    grace=$(( grace + WAIT_STEP ))
  done
  [ "$grace" -gt 0 ] && log "waited ${grace}s for the engine to start"
fi

waited=0
while engine_running && [ "$waited" -lt "$WAIT_MAX" ]; do
  sleep "$WAIT_STEP"
  waited=$(( waited + WAIT_STEP ))
done
[ "$waited" -gt 0 ] && log "waited ${waited}s for an in-flight tick"

tick_line="$(last_tick_line)"
tick_age="$(tick_age_hours "$tick_line")"
tick_status="$(tick_field "$tick_line" status)"
tick_errors="$(tick_field "$tick_line" errors)"

if probe="$(queue_probe)"; then :; else
  log "FATAL could not read the queue at $NOTES_DIR"
  osascript -e "display alert \"x-comms — cannot read the queue\" message $(as_str "queue.py list failed for $NOTES_DIR. See $LOG.") as critical" 2>>"$LOG" >/dev/null
  exit 2
fi
count="$(printf '%s\n' "$probe" | sed -n 1p)"
unreadable="$(printf '%s\n' "$probe" | sed -n 2p)"
queue_dir="$(printf '%s\n' "$probe" | sed -n 3p)"
case "$count" in ''|*[!0-9]*) count=-1 ;; esac
case "$unreadable" in ''|*[!0-9]*) unreadable=-1 ;; esac

# Anything that means "cannot see the queue" rather than "the queue is empty". Each of
# these otherwise arrives as count=0 and takes the silent branch.
queue_problem=""
if [ "$count" -lt 0 ] || [ "$unreadable" -lt 0 ] || [ -z "$queue_dir" ]; then
  queue_problem="The queue could not be read at all. See $LOG."
elif [ ! -d "$queue_dir" ]; then
  queue_problem="The queue directory is not there: $queue_dir — if it lives on a synced drive, that drive may not be mounted."
elif [ ! -r "$queue_dir" ] || [ ! -x "$queue_dir" ]; then
  queue_problem="The queue directory cannot be read: $queue_dir"
elif [ "$unreadable" -gt 0 ]; then
  entry="entries"; [ "$unreadable" -eq 1 ] && entry="entry"
  queue_problem="$unreadable queue $entry could not be parsed, so they are invisible to the review loop: $queue_dir"
fi

if tick_is_healthy "$tick_status" "$tick_age" "$tick_errors"; then tick_ok=1; else tick_ok=0; fi

# --- outcome 1: there is something to act on ---------------------------------
# Guarded on there being no queue problem: with the directory unreadable or entries
# unparseable, `count` is a floor rather than a count, and the alert below is the
# honest response.

if [ -z "$queue_problem" ] && [ "$count" -gt 0 ]; then
  noun="post"; [ "$count" -eq 1 ] || noun="posts"
  when="$(printf '%s' "${tick_line%% *}" | cut -c12-16)"
  summary="Drafted at ${when:-an unknown time}."
  [ "$tick_ok" -eq 1 ] || summary="Heads up: the last run was $(printf '%s' "${tick_line%% *}" | cut -c1-10) (status ${tick_status:-unknown})."

  answer="$(ask "x-comms — $count $noun waiting" \
    "$count $noun waiting for you.

$summary Nothing has published itself.

Approving teaches the voice. Copying is what actually posts. They are separate on purpose." \
    "Later" "Review now" "note" 14400)"
  rc=$?

  if [ "$rc" -ne 0 ]; then
    log "DIALOG FAILED (osascript rc=$rc): $(dialog_err)"
    printf 'ERROR: could not show the dialog (rc=%s): %s\n' "$rc" "$(dialog_err)" >&2
    exit 1
  fi

  case "$answer" in
  "Review now") : ;;
  TIMEOUT) log "deferred, $count waiting (dialog timed out unanswered)"; exit 0 ;;
  *)       log "deferred, $count waiting (${answer:-empty answer})"; exit 0 ;;
  esac

  # Two escaping layers, in the right order. Inner: each path is shell-quoted for the
  # shell Terminal will run it in. Outer: the whole command becomes an AppleScript
  # string literal via as_str.
  #
  # The notes dir is exported rather than left to ~/.zshrc, so the window reviews the
  # queue this script just counted. Two sources for that path is how a review loop ends
  # up pointed at a directory the engine never writes to.
  #
  # The EDITOR line is a warning, not a fix: with EDITOR unset, [e]dit drops you into
  # vi, and `code` without `--wait` returns immediately and saves an unedited post.
  review_cmd="cd $(printf '%q' "$REPO_ROOT") && export SESSION_PUBLISHER_NOTES_DIR=$(printf '%q' "$NOTES_DIR")"'; tail -3 '"$(printf '%q' "$TICK_LOG")"'; echo; [ -n "${EDITOR:-}" ] || echo "note: EDITOR is unset — [e]dit would open vi. export EDITOR=\"nano\" (or \"code --wait\") first."; echo; '"$(printf '%q' "$PYTHON")"' skill/helpers/queue.py review'

  open_terminal "$review_cmd" || exit 1
  log "opened the review loop, $count waiting"
  exit 0
fi

# --- outcome 2: nothing waiting, and the engine is healthy -------------------
# No dialog. This is the common case and the reason the other two stay legible.

if [ "$tick_ok" -eq 1 ] && [ -z "$queue_problem" ]; then
  log "quiet: nothing waiting, last tick ${tick_age}h ago status=${tick_status:-?}"
  exit 0
fi

# --- outcome 3: nothing waiting, and that is because something is wrong ------
# Two distinct faults reach here — the queue cannot be seen, or the tick did not happen
# — and they need different words. A queue that cannot be read is reported first: with
# the directory missing there is nothing meaningful to say about drafts landing in it.

if [ -n "$queue_problem" ]; then
  alert_kind="queue unreadable"
  alert_title="x-comms — the queue cannot be read"
  alert_body="Nothing is showing as waiting for review, and that is not because the queue is empty.

$queue_problem"
  [ "$tick_ok" -eq 1 ] || alert_body="$alert_body

The last run also looks wrong: status ${tick_status:-unknown}, ${tick_age:-unknown} hours ago."
  log "queue problem: $queue_problem"
else
  alert_kind="unhealthy tick"
  alert_title="x-comms — the drafting run looks broken"
  detail="Last run: ${tick_line%% *} (status ${tick_status:-unknown}, ${tick_age:-unknown} hours ago, errors ${tick_errors:-unknown})."
  [ -n "$tick_line" ] || detail="There is no tick line at all — the engine has never written one."
  alert_body="Nothing is waiting for review, and that is not because the queue is simply empty.

$detail

It normally runs every day and writes one line per run."
fi

answer="$(ask "$alert_title" "$alert_body" "Ignore" "Show log" "caution" 14400)"
rc=$?

if [ "$rc" -ne 0 ]; then
  log "DIALOG FAILED (osascript rc=$rc): $(dialog_err)"
  printf 'ERROR: could not show the dialog (rc=%s): %s\n' "$rc" "$(dialog_err)" >&2
  exit 1
fi

case "$answer" in
"Show log") : ;;
# `alert_kind` rather than a hardcoded "stale tick": the alert now fires for a queue
# that cannot be read as well, and a log line that misattributes the fault sends the
# next reader to the wrong file.
TIMEOUT) log "$alert_kind, dialog timed out unanswered (age=${tick_age:-?}h status=${tick_status:-?})"; exit 0 ;;
*)       log "$alert_kind, dismissed (age=${tick_age:-?}h status=${tick_status:-?})"; exit 0 ;;
esac

open_terminal "tail -20 $(printf '%q' "$TICK_LOG")" || exit 1
log "$alert_kind: opened the log (age=${tick_age:-?}h status=${tick_status:-?})"
exit 0
