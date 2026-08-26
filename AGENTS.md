<!-- Project context for any AI agent. NOT agent persona — see role prompts -->
# AGENTS.md — session-publisher

## Project context

An ambient drafting system for X, packaged as a Claude Code skill. A scheduled local agent mines the operator's own session history, drafts finished ≤280-character post bodies through a headless `claude -p` with no session open, and files them in a review queue; the operator's only obligation is one action per entry. A seven-stage interactive conversation remains as the manual fallback path. Everything is written under the operator's configured notes directory (`$SESSION_PUBLISHER_NOTES_DIR`, default `~/personal-notes`), never in this repo. The system never publishes directly — the operator pastes an approved body into their X scheduler of choice (or x.com directly).

## Stack & key dependencies

- Language: Python 3.11+
- Dependencies: standard library only (no `requirements.txt`)
- Critical external services: none in v0 (no X API, no separate LLM API key)
- Notes directory: `$SESSION_PUBLISHER_NOTES_DIR` env var; falls back to `~/personal-notes`

## Working state

- **Authoritative design:** `planning/SPEC.md` (Claude Code skill, manual-paste gateway, 7-stage interactive conversation, drafts saved to `$NOTES_DIR/posts/x/`).
- **Skill shipped:** `skill/` directory. Files: `SKILL.md`, `helpers/{select,save,thread,mirror,queue}.py`, `prompts/drafting-guide.md`. All helpers stdlib-only. Install via `ln -s <repo>/skill ~/.claude/skills/session-publisher` — **installed on this machine 2026-08-25**; it had never been run, which is why the tool went stale.
- **x-comms-engine v1 — SHIPPED, chain complete (branch `feat/x-comms-engine`, 6 commits, not yet merged).** The skill is no longer pull-model. A launchd user agent (`ai.fero.x-comms`, daily 07:30) runs `skill/engine/run.sh` with zero Claude sessions open: it expires the queue, mines `SESSION_INDEX.md` + git logs for seeds, drafts finished ≤280-char bodies through a headless `claude -p`, and files them into a queue **outside this repo** at `$SESSION_PUBLISHER_NOTES_DIR/posts/x/queue/`. Sunday is a deep tick (14-day window, ≤3 drafted as one narrative arc); every other day is ambient (3 days, ≤2 standalone singles). The operator reviews with `python3 skill/helpers/queue.py review` — one action per entry (`[a]pprove [e]dit [k]ill [c]opy [s]kip`) — and approval appends the body to the private corpus automatically. Nothing publishes itself; the operator pastes an approved body into X. **D1 is proven**: headless `claude -p` runs under launchd on subscription credentials, no API key. **Pending:** Smoke checklist v2 (SPEC §5) and the PR to `main` — see `planning/task_plan.md`. Authoritative design is the local, gitignored `planning/SPEC-x-comms-engine.md` rev 2; it supersedes `planning/SPEC.md` where the two disagree. Per-commit history (C1–C6, what each shipped and every `/review` finding) lives in `planning/progress.md` + `planning/findings.md` and in the commit messages — **not here**: this bullet is a current-state snapshot, not a changelog.
- **Pre-mortem:** `planning/PreMortem-session-publisher-2026-05-11.md` documents 4 Tigers + 3 Elephants identified before the build window and how each was resolved.
- **Stage 5.5 corpus-mirror (feature thread):** Phase C shipped 2026-05-16. `skill/helpers/mirror.py` is a pure-loader helper (parses `examples.local.md`, drops `near_duplicate_of` cluster non-reps, emits JSON). `SKILL.md` carries the new Stage 5.5 section (load → infer+select → rewrite → prompt → response). `examples-template.md` documents `guide_compliance` + `near_duplicate_of`. **Pivot:** SPEC v0.2 §4 deterministic tag-overlap pipeline superseded — Claude does semantic selection in Stage 5.5 prose. Rationale annotated inline in the SPEC + in `planning/findings.md`. Next: first end-to-end run with new stage will calibrate register-fit honesty. Authoritative design: SPEC v0.2 (annotated) + SKILL.md §5.5 (shipped behavior).
- **Drafting guide v1.3 shipped 2026-05-18** based on `xai-org/x-algorithm` (Jan 2026) signal analysis. Added Layer 1 rule 16 (link placement — link in first reply, not body, to avoid 30–90% reach loss) and new "Post-publish protocol" section (author-reply within 1h + posting-window timing). Layer 2 renumbered 17–24 (was 16–23); 9 corpus notes updated. SKILL.md Stage 7 now includes `author_replied: yes/no` tracking. Delta artifact: `planning/DELTA_algo-vs-drafting-guide-2026-05-18.md`. Edits E4 (H5 tone caveat) and E5 (rule 5 density) deferred.

## Operating principles (deterministic — apply on every session)

### Context window discipline

- **50% rule:** when context usage crosses 50%, pause and route through a wrap-up. Above 50%, context-rot research shows reasoning over the middle of the window becomes unreliable. Don't push to 80%; recovery from a blown context costs more than a clean re-entry.
- **Pause / Persist / Exit / Re-enter pattern:**
  1. Pause: finish the current step; do not interrupt mid-action
  2. Persist: produce a handover (boot prompt for transitions, ledger for resumptions)
  3. Exit: close the session
  4. Re-enter: new session reads the handover document

### Failure handling — N-attempt protocol

- **1st attempt:** apply the most likely fix
- **2nd attempt:** try an alternative approach (different angle, different tool)
- **3rd attempt fails:** stop pushing on the same vector
  - Document what was tried
  - Step back: reframe the problem (is the goal still right?)
  - Propose external research (web docs, examples) for fresh perspective
  - Escalate to user with: what failed, what's been tried, what new angle is proposed

### Working-state discipline

Four locations carry the project's working state. Update discipline:

| File | Content | Cadence |
|------|---------|---------|
| `AGENTS.md` § Project context | Current state line — phase, gates, blockers | Same session as the state change (not deferred to next session) |
| `planning/task_plan.md` | Phase state machine — current phase, history, gates, decisions | At every phase boundary |
| `planning/progress.md` | Chronological session log (most recent on top) | End of every session — no exceptions |
| `planning/findings.md` | Session-level reframes, pivots, gotchas, re-evaluation list | Mid-session via 2-Action Rule + end-of-session catch-up |

Note: the three `planning/*.md` files are gitignored in this public repo. They exist locally and the discipline applies the same way.

Three discipline rules tie these to action:

- **2-Action Rule:** after every 2 search/read operations, write findings to
  `planning/findings.md`. Honor system, reinforced by PostToolUse hook nudge.
- **Phase boundary checkpoints:** before any major phase transition, update
  `task_plan.md` to mark phase complete and declare execution context for the
  next phase (D16: model + thinking effort + role + context per phase).
- **Session-end catch-up:** at every session end (via `/wrap-up` or manual
  close), append to `progress.md` AND `findings.md`. The `/wrap-up` skill
  writes the operator's session-log SESSION document; these project-local
  files are the same log scoped to this project. If a session shipped no
  project content (meta-work only), still append a one-line entry noting
  that — silence creates currency doubt.

### Security boundaries

- **API keys never in chat or screen-shared windows.** If a key is exposed (paste, screenshot, log), generate a new one immediately — treat the old key as compromised.
- **Admin mode (`--dangerously-skip-permissions`)** — gated on three predicates, ALL must hold:
  1. The plan is locked: design doc is current and approved
  2. The work is well-scoped: no ambiguity in the next step
  3. The project folder is sandboxed: not a system directory, not a folder with important files unrelated to the task
  Never use admin mode on a first-ever session in a folder; the calibration sense for "what the agent will likely do" must be earned first.

### Clarity discipline

- **Clarity beats token optimization.** Vague prompts force exploratory work that costs more tokens than the optimization saves. Invest tokens in the spec / brainstorm; save tokens during execution by working from a sharp plan.

## Build & run

This is a Claude Code skill, not a standalone CLI.

- **Invoke:** `/session-publisher` in any Claude Code session (recommended: at the end of an evening routine).
- **Install:** `ln -s <repo>/skill ~/.claude/skills/session-publisher` — Claude Code auto-loads `SKILL.md` on next session start.
- **Configure notes dir:** export `SESSION_PUBLISHER_NOTES_DIR=/your/notes/path` in your shell profile (defaults to `~/personal-notes`).
- **Smoke-test helpers:** `python3 skill/helpers/select.py --days 7`, `python3 skill/helpers/thread.py --days 7`, `python3 skill/helpers/save.py "<session_source>" --body "test"`, `python3 skill/helpers/queue.py --validate`.
- **Smoke-test the drafting engine without spending a model call:** `X_COMMS_FORCE_SEED=1 python3 skill/helpers/draft.py --dry-run` assembles the prompt and reports its size; `--stub-response <file>` feeds a canned model reply through the full gate + write path; `X_COMMS_CLI=<script>` swaps the CLI for one that hangs or exits non-zero, which is how the timeout and exit-code branches are tested. A real end-to-end run is `X_COMMS_FORCE_SEED=1 python3 skill/helpers/draft.py --queue-dir /tmp/q` (add `--mode arc` for the Sunday batch path).
- **Smoke-test one ambient tick without a scheduler:** `skill/engine/run.sh --mode ambient` (or `--mode deep` for the arc path) runs the real pipeline against whatever `SESSION_PUBLISHER_NOTES_DIR` points at. Point that at a scratch directory holding a `SESSION_INDEX.md` and set `X_COMMS_CLI` to a stub script that prints a `{"is_error": false, "result": "<json>"}` envelope, and every branch — idle, capacity skip, expire, gate rejection, CLI failure — is exercisable for free. `X_COMMS_LOG_DIR` isolates the tick log.
- **No build pipeline.** Helpers are standalone Python 3.11+ scripts; stdlib only. `run.sh` is bash 3.2-compatible and shellcheck-clean at `-S warning`.
- **No tests in v0.** Smoke tests are inline. Friction-driven extension only.

## Conventions & gotchas

- **Notes path with spaces / parentheses / @ signs.** `pathlib.Path` handles these safely; never shell-expand. Any `subprocess` or `os.system` call with unquoted special chars silently breaks. Define `NOTES_BASE` as a single constant at the top of each helper.
- **SESSION_INDEX.md has no conventional header row.** The `## Sessions` section starts pipe-delimited rows directly: `| YYYY-MM-DD | title | type | outcome | insight | ledger | asana | tags |` — 8 positional columns. Parser: find lines matching `\| \d{4}-\d{2}-\d{2} \|`, extract by position [1]=date [2]=title [8]=tags.
- **SKILL.md frontmatter must match Claude Code convention exactly.** YAML with `name`, `version: "0.x.x"`, `description: <one-sentence-for-trigger-matching>`. Wrong format = skill silently absent from skill list.
- **`select.py` reads SESSION_INDEX in one `Path.read_text()` call.** Not streaming. Avoids concurrent-append edge cases.
- **Posts content lives outside the repo.** `$NOTES_DIR/posts/x/YYYY-MM-DD_post-NNN.md`. The public repo carries the skill source only.
- **Drafting LLM is the running Claude.** No separate Anthropic API call, no `.env`, no API key. The skill reads `skill/prompts/drafting-guide.md` and applies the guide via the model already in the session.
- **Drafting guide is dual-layer.** Layer 1 (rules 1–16, hook templates 1–5) = general builder norms. Layer 2 (rules 17–24, hook templates 6–10, AI anti-patterns) = AI/agentic overrides; takes precedence when posting about LLM tools or agentic systems. Hook templates 11–12 apply under either layer. These counts drifted twice before C2 — the guide has carried 24 rules since v1.3 while four dependent files still said 23; if you renumber, grep `SKILL.md`, `README.md` and `examples-template.md` in the same commit.
- **Operator pastes into an X scheduler.** v0 does NOT call X API. Hand-off block prints the post body; operator copies into the X scheduler (or x.com) of their choice.
- **Reaction recap is optional in v0.** Skill never fails on missing annotations. Automated reaction reading via X read-only API is explicit v0.2 work.
- **The corpus body format is load-bearing, not cosmetic.** `mirror.py` treats an entry body as a *contiguous* run of `>` lines and stops at the first line that is not one, so a real blank line inside a body silently truncates the entry to its first paragraph. Blank lines must be written as a bare `>`, every other line as `"> "` (the regex consumes exactly one whitespace char after `>`). Trailing whitespace on the body's **last** line is also lost to a final `.rstrip()`; mid-body trailing whitespace survives, and one seeded post genuinely depends on that. Any writer that appends to `examples.local.md` — C5's approval path included — must round-trip through `mirror.py` and compare bytes, not assume.
- **Three gitignored files now sit in `skill/prompts/`.** `persona.local.md`, `examples.local.md` and `private-terms.local.md` carry operator-derived material and are covered by the `*.local.md` rule plus `skill/prompts/persona*.md`. `private-terms.local.md` has a parsing gotcha of its own: **every line starting with `- ` is read as a denylist term**, so its prose bullets use `*`. Over-broad terms are the real failure mode — a rejection is logged body-free by design, so a draft killed by a too-generic term is hard to trace back.
- **The corpus is append-only, so nothing that can still refuse may run after an append.** C5's approval path stages the queue entry first — every check run, bytes in a temp file — appends the corpus row, then `os.replace`s the entry into place. Writing the corpus first (the intuitive order, since a flip that precedes the append can silently starve the corpus) puts three independent rejection paths downstream of an irreversible write, and the retry cannot undo it: the append is idempotent on `source_entry`, so the second attempt reports success and moves on. The same file also refuses a retry that arrives with a *different* body rather than silently keeping the first one.
- **An entry id is unique only per second-of-day, and the archive counts.** `allocate_entry` steps a second on collision but originally checked the queue directory alone, so an id could be reused once its holder was archived. Nothing depended on that until C5 added a transition that reads the archive to detect a race — at which point a stale archive file reads as "this entry was archived by someone else" and blocks approval forever, and `archive_entry` silently overwrites the older record. Any new writer here must treat `.archive/` as part of the id namespace.
- **`skill/helpers/queue.py` shadows the stdlib `queue` module.** Any script run from `skill/helpers/` gets that directory at `sys.path[0]`, so a sibling helper's `import queue` resolves to ours. `concurrent.futures` imports stdlib `queue` internally, so a thread pool in a sibling helper fails with a misleading `module 'queue' has no attribute 'SimpleQueue'`. `subprocess.run(..., timeout=...)` is unaffected. The filename is fixed by the queue contract — don't rename it, just don't reach for a thread pool in this directory.
- **`skill/helpers/select.py` shadows the stdlib `select` module — and that breaks `subprocess`.** Same mechanism as the `queue.py` gotcha above, but with a much worse blast radius: `import subprocess` pulls in `selectors`, which does `import select`, which resolves to the session-selection helper and dies with `AttributeError: module 'select' has no attribute 'select'`. Any helper in this directory that shells out hits this the first time it runs. `draft.py` fixes it for itself by dropping its own directory out of `sys.path` before the stdlib imports; anything else here that needs `subprocess` must do the same. Renaming `select.py` would be the real fix but it is referenced by `SKILL.md`, `README.md` and the documented smoke tests.
- **`mine.py`'s git-log repo matching is exact-slug-only, on purpose.** A generic word-tokenizer (split a tag like `voice-discovery` on `-`) turns it into `voice` + `discovery`, and `voice` alone substring-matches an unrelated repo like `voice-capture-rag` — this actually happened during the first real run and silently attributed one project's commits to another's seed `text`. The fix was whole-tag equality against repo dirnames only, never substring containment. The same discipline applies to the tool-/app-/scripts-/ref- prefix-stripped alias: two repos under different prefixes can strip to the same bare slug, and the collision must null only the ambiguous *alias*, never a repo that is unambiguously, exactly named that slug (`by_name` and `by_alias` are tracked as separate dicts for exactly this reason — merging them naively re-creates the same class of silent misattribution one level down).
- **A headless `claude -p` call inherits the operator's whole user-level context, and `draft.py` can only fence off part of it.** It neutralises the working directory (no project `AGENTS.md` auto-discovery), scopes MCP with `--strict-mcp-config`, and disables every built-in tool with `--tools ""`. What it cannot scope from the command line is `~/.claude/`: a `SessionStart` hook and the global rules files are injected into every headless session, so the drafting model sees operator material that has nothing to do with the seed. **D6 is the only barrier between that context and a published body** — which is why the leak shapes are worth widening whenever a new shape shows up in those files (a MAC-address shape was added for exactly this reason). Nothing here is a leak today; it is the reason the gate is not optional.
- **A headless `claude -p` call has a fixed floor of roughly 55k cached input tokens**, independent of prompt size — system prompt, tool schemas and hooks are created fresh on every cold invocation. **That floor is quota, not money.** The CLI reports a `total_cost_usd` on every call (measured: `0.559385` for a nine-token reply), but with no `ANTHROPIC_API_KEY`, no `ANTHROPIC_AUTH_TOKEN` and no `apiKeyHelper` configured, the call authenticates via subscription OAuth from the Keychain — exactly what D1 specifies — so that figure is a notional equivalent, not a bill. **Do not convert `total_cost_usd` into a monthly spend without first checking which credentials are in play.** The real consideration is that headless ticks consume the same usage windows as the operator's own sessions, which makes tick *timing* (D8) the lever that matters alongside `X_COMMS_MODEL` (D7). `--bare` would cut the floor but forces API-key auth and never reads subscription OAuth, which D1 rules out.
- **`launchctl setenv` does not reach a `gui/` LaunchAgent's environment.** The obvious way to arm the `X_COMMS_FORCE_SEED` test hook for a `launchctl kickstart` is `launchctl setenv X_COMMS_FORCE_SEED 1`. It does not work: `launchctl getenv` reports `1`, and the job still mines normally — verified twice, including after a full `bootout`/`bootstrap` cycle. Editing the plist to arm a test would leave the engine armed, so `run.sh` also reads a **one-shot marker file** at `$X_COMMS_LOG_DIR/force-seed`, consumed before anything else can fail. `touch` it, kickstart, and the tick line reports `forced=1`. Anything else that needs to pass a one-off flag into this job has the same problem and should reuse the marker idiom.
- **A tick log field is only parseable if reason codes cannot contain its separator.** `rejected=` is comma-joined, and most of `draft.py`'s reason codes are clamped slugs — but not all: `gate:unsourced_number:` appends the offending digit runs *comma-separated*, so a raw code would split one rejection into two that never happened. `run.sh` rewrites commas to `;`, collapses whitespace and caps the length — in `jreasons` for `rejected=` **and in `jfield` for every string value**, because `reason=` takes a helper-supplied `reason_code` the same way and a newline in one would turn a tick line into two. The clamped-vocabulary assumption is true today and was never guaranteed. Note also that `gate:unsourced_number:<digits>` is the one place **body-derived content reaches the D9 line**: `draft.py` puts the offending digit runs there deliberately (they are the diagnosis, and the operator never sees the body otherwise). That is a considered exception to "bodies never logged", not an oversight — but it is the reason the log stays local rather than being treated as publishable-anywhere.
- **launchd opens `StandardOutPath` before it execs the program**, so a run.sh that `mkdir -p`s its own log directory cannot rescue *its own* first run's redirect — the directory does not exist yet when launchd tries to open the file. That is why the D9 tick line is written by `run.sh` directly to `tick.log` rather than echoed to stdout: the one line that says what happened must not be the line that disappears. stdout/stderr still earn their redirects as the helpers' diagnostic channel.
- **The fixture seed drafts marginally, and an ambient tick has only two shots.** Eight forced ticks against `seed_fixture.json` produced five anti-voice rejections (`first_person_plural` — the model reaches for "we"), two unsourced-number rejections, and one clean draft. The gates are doing their job and the engine reason-codes each one correctly, but treat a single forced run as a *coin flip*, not a regression: a red C6-style gate needs three or four attempts before it means anything. The same arithmetic applies to real ticks — `run.sh` mines exactly `--max-drafts` seeds (2 ambient / 3 deep), because `draft.py` drops anything past `seeds[:max_drafts]` so extra seeds are never attempted. At the observed rejection rate the expected yield of an ambient tick is well under one draft, and a run of `drafted=0` lines is the design working, not a fault. Raising throughput means retrying into the next seed after a gate skip, which is a `draft.py` change, not a `run.sh` one.
- **The queue never lives in this repo.** It is `$SESSION_PUBLISHER_NOTES_DIR/posts/x/queue/` — unposted draft bodies are private. `.gitignore` carries shape-based guards (`queue/`, `*queue*`, `seeds*`) with negations keeping `skill/helpers/queue*.py` trackable. A gitignore negation only works because no *parent directory* is excluded; adding a `skill/helpers/` exclusion would silently untrack the helpers.

## Out of scope

- ❌ X application programming interface — write/publish path (manual-paste gateway is v0; direct API only if friction surfaces)
- ❌ X application programming interface — read path for automated reaction fetching (explicit v0.2 feature work; needs X dev account approval)
- ❌ Auto-trigger from any daily-routine workflow (manual invocation in v0 — **superseded for the x-comms-engine chain**, whose whole point is an ambient launchd trigger; see § Working state)
- ❌ Threads, images, quote-tweets, retweets
- ❌ Multi-platform (LinkedIn, Mastodon, Bluesky)
- ❌ Engagement metrics, follower count, analytics dashboards (input-only measurement doctrine)
- ❌ Web user interface
- ❌ Mobile review path (v0 is computer-only)
- ❌ Telegram, email, or other gate channels (interactive in-chat gate is v0)
- ❌ A/B testing of draft variants
- ❌ Advanced focus-filter modes (regex, exclude lists, time-windowed)
- ❌ Automated post timing optimisation
- ❌ Multi-operator support
- ❌ Anything requiring infrastructure outside Claude Code (GitHub Actions, servers, databases — rejected by SPEC v0 and still rejected). **Narrowed for the x-comms-engine chain:** a local launchd user agent is the one exception, and only because the ambient trigger is the whole point of v1; hosted always-on services stay out.

## References

- **Authoritative design:** `planning/SPEC.md`
- **Pre-mortem:** `planning/PreMortem-session-publisher-2026-05-11.md`
- **Drafting guide:** `skill/prompts/drafting-guide.md` (24 rules + 12 hook templates)
