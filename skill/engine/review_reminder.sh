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
#   posts waiting        -> dialog: review them            [Later] [Review now]
#   nothing, tick fine   -> NO DIALOG. one line in the log.
#   tick stale or failed -> dialog: something is wrong     [Ignore] [Show log]
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

# `status=<x>` out of a tick line. run.sh clamps this to a slug vocabulary
# (ok / idle / capacity / failed), so a bare word-split is safe.
tick_field() {
  local line="$1" key="$2" tok
  for tok in $line; do
    case "$tok" in "$key="*) printf '%s' "${tok#*=}"; return 0 ;; esac
  done
}

engine_running() {
  launchctl print "$DOMAIN/$ENGINE_LABEL" 2>/dev/null | grep -qE '^[[:space:]]*state = running'
}

# Actionable entries = queued + approved-but-not-yet-copied. Both need an action from
# the operator, which is exactly what this reminder is counting. Asking queue.py rather
# than globbing the directory keeps the definition in the one file that owns it.
#
# Runs from REPO_ROOT, never from skill/helpers: that directory contains `queue.py` and
# `select.py`, which shadow the stdlib `queue` and `select` modules for anything whose
# sys.path[0] lands there.
actionable_count() {
  local json count
  json="$(cd "$REPO_ROOT" && SESSION_PUBLISHER_NOTES_DIR="$NOTES_DIR" "$PYTHON" "$QUEUE_HELPER" list 2>>"$LOG")" || return 1
  count="$(cd "$REPO_ROOT" && printf '%s' "$json" | "$PYTHON" -c \
    'import json,sys; print(sum(json.load(sys.stdin).get("counts",{}).values()))' 2>>"$LOG")" || return 1
  case "$count" in ''|*[!0-9]*) return 1 ;; esac
  printf '%s' "$count"
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
DIALOG_ERR_FILE="${TMPDIR:-/tmp}/.x-comms-review-dialog.err"

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
  # No EnvironmentVariables block, deliberately: every value this needs is read out of
  # the engine's plist at run time (see resolve_config). PATH is the exception, because
  # launchd supplies almost none and `date`, `tail`, `grep`, `osascript` and `launchctl`
  # must resolve.
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
  n="$(actionable_count)" && printf 'queue:      %s waiting\n' "$n" || { printf 'queue:      COULD NOT READ\n'; ok=1; }
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
  osascript -e "display alert \"x-comms — review loop unavailable\" message $(as_str "queue.py or python3 could not be found. The reminder is armed but has nothing to open.") as critical" >/dev/null 2>&1
  printf 'FATAL: queue.py or python3 not usable\n' >&2
  exit 2
fi

# Wait out an in-flight tick. See the header: on a cold wake both jobs start together,
# and deciding first would report the queue as it was BEFORE the tick this reminder
# exists to report on.
waited=0
while engine_running && [ "$waited" -lt "$WAIT_MAX" ]; do
  sleep "$WAIT_STEP"
  waited=$(( waited + WAIT_STEP ))
done
[ "$waited" -gt 0 ] && log "waited ${waited}s for an in-flight tick"

tick_line="$(last_tick_line)"
tick_age="$(tick_age_hours "$tick_line")"
tick_status="$(tick_field "$tick_line" status)"

if count="$(actionable_count)"; then :; else
  log "FATAL could not read the queue at $NOTES_DIR"
  osascript -e "display alert \"x-comms — cannot read the queue\" message $(as_str "queue.py list failed for $NOTES_DIR. See $LOG.") as critical" >/dev/null 2>&1
  exit 2
fi

# An unparseable or absent timestamp is unhealthy, not unknown-therefore-fine. That
# asymmetry is the whole safety property: this script may cry wolf, it may not go quiet.
if [ -z "$tick_age" ] || [ "$tick_age" -ge "$STALE_HOURS" ] || [ "$tick_status" = "failed" ]; then
  tick_ok=0
else
  tick_ok=1
fi

# --- outcome 1: there is something to act on ---------------------------------

if [ "$count" -gt 0 ]; then
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

if [ "$tick_ok" -eq 1 ]; then
  log "quiet: nothing waiting, last tick ${tick_age}h ago status=${tick_status:-?}"
  exit 0
fi

# --- outcome 3: nothing waiting, and that is because something is wrong ------

detail="Last run: ${tick_line%% *} (status ${tick_status:-unknown}, ${tick_age:-unknown} hours ago)."
[ -n "$tick_line" ] || detail="There is no tick line at all — the engine has never written one."

answer="$(ask "x-comms — the drafting run looks broken" \
  "Nothing is waiting for review, and that is not because the queue is simply empty.

$detail

It normally runs every day at 07:30 and writes one line per run." \
  "Ignore" "Show log" "caution" 14400)"
rc=$?

if [ "$rc" -ne 0 ]; then
  log "DIALOG FAILED (osascript rc=$rc): $(dialog_err)"
  printf 'ERROR: could not show the dialog (rc=%s): %s\n' "$rc" "$(dialog_err)" >&2
  exit 1
fi

case "$answer" in
"Show log") : ;;
TIMEOUT) log "stale tick, dialog timed out unanswered (age=${tick_age:-?}h status=${tick_status:-?})"; exit 0 ;;
*)       log "stale tick, dismissed (age=${tick_age:-?}h status=${tick_status:-?})"; exit 0 ;;
esac

open_terminal "tail -20 $(printf '%q' "$TICK_LOG")" || exit 1
log "opened the tick log (age=${tick_age:-?}h status=${tick_status:-?})"
exit 0
