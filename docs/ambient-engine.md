# Ambient engine reference

Moved here from `AGENTS.md` on 2026-09-23 by the D10 guard follow-up's whole-file relocation: from § Working state, the overview lines of the 2026-08-30 engine snapshot (one stale clause replaced by the audit's finding) and the register fragment of that snapshot's three-causes paragraph; the engine smoke-test bullets from § Build & run; and from § Conventions & gotchas, the quota-floor and yield bullets of Headless drafting, the first two `launchd` gotchas and the 07:45 review-nag section; paths are relative to the repository root, and a bare file name after a full path shares its directory.

A launchd user agent (`ai.fero.x-comms`, daily 07:30) runs `skill/engine/run.sh` with zero Claude sessions open: it expires the queue, mines the session history for seeds, drafts finished bodies through a headless `claude -p`, and files them into a queue **outside this repo**. Sunday is a deep tick (14-day window, ≤3 drafted as one arc); every other day is ambient (3 days, ≤2 singles). A second agent (`ai.fero.x-comms-review`, daily 07:45, `skill/engine/review_reminder.sh --install`) reports on that tick and opens the review loop —
the reminder has fired in production: the 2026-09-07 audit counted eight scheduled outcomes, six of them AppleEvent timeout failures and two "Later" deferrals (`strategy/REPOSITORY_AUDIT.md:54`).

**register** (`persona.local.md` §4 prescribed a ≤280-char staccato voice derived from the operator's 5 weakest posts — rebuilt 2026-08-28 from a 33-draft operator-verdicted calibration into **400–650 characters, three or four short paragraphs, framing question as the opening line only, plain-language landing**; the five laws live in `skill/engine/task-single.md` and `task-arc.md`);

- **Smoke-test the drafting engine without spending a model call:** `X_COMMS_FORCE_SEED=1 python3 skill/helpers/draft.py --dry-run` assembles the prompt and reports its size; `--stub-response <file>` feeds a canned model reply through the full gate + write path; `X_COMMS_CLI=<script>` swaps the CLI for one that hangs or exits non-zero, which is how the timeout and exit-code branches are tested. A real end-to-end run is `X_COMMS_FORCE_SEED=1 python3 skill/helpers/draft.py --queue-dir /tmp/q` (add `--mode arc` for the Sunday batch path).
- **Smoke-test one ambient tick without a scheduler:** `skill/engine/run.sh --mode ambient` (or `--mode deep` for the arc path) runs the real pipeline against whatever `SESSION_PUBLISHER_NOTES_DIR` points at. Point that at a scratch directory holding a `SESSION_INDEX.md` and set `X_COMMS_CLI` to a stub script that prints a `{"is_error": false, "result": "<json>"}` envelope, and every branch — idle, capacity skip, expire, gate rejection, CLI failure — is exercisable for free. `X_COMMS_LOG_DIR` isolates the tick log.
- **Arm the 07:45 review nag:** `bash skill/engine/review_reminder.sh --install` (`--status`, `--uninstall`; no argument prompts immediately). It reports on the 07:30 tick and opens the review loop — it never drafts. Every branch is reachable without a scheduler: `X_COMMS_REVIEW_LOG_DIR` isolates its log (and is ignored by `--install`), `X_COMMS_REVIEW_WAIT=0` and `X_COMMS_REVIEW_GRACE=0` skip the two tick waits, `X_COMMS_REVIEW_STALE_HOURS` moves the alert threshold, and a stub `osascript` earlier in `PATH` stands in for the dialog. That is how all eight engine statuses, the three invisible-queue states, clock skew, a TCC denial and both wait orderings were each exercised.

### Headless drafting (`claude -p`)

- **There is a fixed floor of ~55k cached input tokens per call, and it is quota, not money.** The
  CLI reports `total_cost_usd` (measured `0.559385` for a nine-token reply), but with no API key,
  auth token or `apiKeyHelper` it authenticates via subscription OAuth — so that figure is notional.
  **Never convert it to monthly spend without checking which credentials are in play.** The real
  cost is that ticks consume the same usage windows as your own sessions, which makes tick timing
  (D8) the lever alongside `X_COMMS_MODEL` (D7). `--bare` cuts the floor but forces API-key auth,
  which D1 rules out.
- **Expect a low yield per tick, by design.** Eight forced ticks on the fixture gave five anti-voice
  rejections (the model reaches for "we"), two unsourced-number rejections, one clean draft. A tick
  attempts exactly `--max-drafts` seeds (2 ambient / 3 deep) because `draft.py` drops anything past
  `seeds[:max_drafts]`. So `drafted=0` runs are the gates working, not a fault — and a single red
  forced run is a coin flip, not a regression. Raising throughput means retrying into the next seed
  after a gate skip: a `draft.py` change, not a `run.sh` one.

### launchd

- **`launchctl setenv` does not reach a `gui/` agent's environment.** `getenv` reports the value and
  the job never sees it — verified across a full `bootout`/`bootstrap` cycle. To pass a one-off flag,
  use the marker-file idiom: `run.sh` consumes a one-shot `$X_COMMS_LOG_DIR/force-seed`, and the tick
  line reports `forced=1`. Editing the plist to arm a test leaves the engine armed — don't.
- **launchd opens `StandardOutPath` before exec'ing the program**, so a script that `mkdir -p`s its
  own log directory cannot rescue its own first run's redirect. Hence the D9 tick line is written
  directly to `tick.log`, never echoed to stdout: the line that says what happened must not be the
  line that disappears. stdout/stderr remain the helpers' diagnostic channel.

### The 07:45 review nag (`review_reminder.sh`)

- **An AppleScript string literal cannot contain a raw newline.** It is a *compile* error (−2741),
  so the dialog never appears — and a dialog that never appeared is indistinguishable from one the
  operator dismissed. The sibling `rls_reminder.sh` never hit this because it assembles its text in
  AppleScript with `& return &`; ours assembles in bash, so `as_str` splices multi-line text into
  `"line" & return & "" & return & "line"`. Any change to dialog copy must be re-checked with
  `osacompile` — **from outside the Claude Code sandbox**, which blocks scripting-addition
  terminology and fails even `display dialog "hello"`, producing a false negative that looks exactly
  like a real syntax error.
- **`ask` is always called inside a command substitution, so it cannot report through a variable.**
  Capturing osascript's stderr into `DIALOG_ERR=` was silently discarded with the subshell and every
  failure logged as "no stderr" — reintroducing, inside the reporting channel, the exact blindness
  the capture exists to prevent. It writes to `DIALOG_ERR_FILE`; `open_terminal` reuses that file
  rather than calling `mktemp`, because a failed `mktemp` takes the redirect down with it and bash
  then reports "could not launch Terminal" for a Terminal that was never asked.
- **The health test is an allowlist, and a denylist there was a real hole.** `run.sh` writes EIGHT statuses — `ok idle no_output capacity failed locked interrupted incomplete` — and testing only for `failed` passed the last three as healthy. `locked` is the worst: a wedged engine re-emits it every morning **with a fresh timestamp**, so the staleness ceiling never trips and the reminder stays silent forever, which is the exact failure it exists to end. `interrupted` (lid closed mid-tick) repeats the same way. Allowlist the healthy four so any status `run.sh` grows later fails closed.
- **`queue.py list` exits 0 and reports `counts: {}` in three states that are not "nothing to review":** the queue directory absent (it lives on a synced drive — unmounted looks exactly like empty), the directory present but unreadable (`Path.glob` swallows `PermissionError`), and entries that do not parse (`cmd_list` files those under `unreadable` and excludes them from `counts`). Reading config from the engine plist prevents plist *drift*; it does not prevent any of these. Take `queue_dir` and `unreadable` from the same JSON and speak up rather than counting zero.
- **Quiet is a state, and it is logged.** On a healthy morning with an empty queue there is no
  dialog — so the log line is the only evidence the job ran at all, and "silent because fine" and
  "silent because broken" are otherwise the same observation. Hence `~/Library/Logs`, never `/tmp`.
- **Staleness is measured in hours, not in "did it run today".** `StartCalendarInterval` defers to
  the next wake, so opening the lid at 14:00 fires the 07:30 tick and this 07:45 job at nearly the
  same moment in an order launchd does not promise. A date comparison cries failure on every late
  wake; the 36-hour ceiling plus a capped poll while `ai.fero.x-comms` is running tolerates the race.
  An **unparseable** timestamp counts as unhealthy, not unknown — this script may cry wolf, it may
  not go quiet.
- **It restates none of the engine's configuration.** Notes dir, interpreter, tick-log path and the
  engine's own `StartCalendarInterval` are read out of `ai.fero.x-comms.plist` at run time. A second copy drifts, and the failure it produces
  is a reminder counting an empty queue in a directory the engine never writes to, reporting
  "nothing today" forever. Environment variables take precedence over the plist purely as the test
  seam; this job's own plist sets nothing but `PATH`.
- **`PlistBuddy` prints "File Doesn't Exist, Will Create:" to stdout, not stderr.** Reading a baked
  path from a missing plist therefore captures that sentence as the path and reports a mismatch that
  is really a missing install. Guard the read on the file existing.
