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

- **Authoritative design:** `planning/SPEC-x-comms-engine.md` rev 2 (local, gitignored) — the ambient system. `planning/SPEC.md` describes the superseded v0 pull model and survives only where the two do not disagree.
- **Skill shipped and installed** (`ln -s <repo>/skill ~/.claude/skills/session-publisher`, 2026-08-25). `skill/` carries `SKILL.md`, seven stdlib-only helpers (`select`, `save`, `thread`, `mirror`, `queue`, `draft`, `mine`), `engine/` (the ambient tick `run.sh` + the headless prompt scaffold), and `prompts/`.
- **x-comms-engine v1 — SHIPPED, chain complete (branch `feat/x-comms-engine`, 6 commits, not yet merged).** The skill is no longer pull-model. A launchd user agent (`ai.fero.x-comms`, daily 07:30) runs `skill/engine/run.sh` with zero Claude sessions open: it expires the queue, mines `SESSION_INDEX.md` + git logs for seeds, drafts finished ≤280-char bodies through a headless `claude -p`, and files them into a queue **outside this repo** at `$SESSION_PUBLISHER_NOTES_DIR/posts/x/queue/`. Sunday is a deep tick (14-day window, ≤3 drafted as one narrative arc); every other day is ambient (3 days, ≤2 standalone singles). The operator reviews with `python3 skill/helpers/queue.py review` — one action per entry (`[a]pprove [e]dit [k]ill [c]opy [s]kip`) — and approval appends the body to the private corpus automatically. Nothing publishes itself; the operator pastes an approved body into X. **D1 is proven in production**: it fired unattended at 07:32 on 2026-08-27 and drafted two posts with nobody present. **Blocked on content aim, not construction.** The operator rejected 9 of 9 drafts as unreadable and all-about-testing. Root cause was seed depth, not the prompt or the persona: `mine.py` fed the model a ~1.2 KB `SESSION_INDEX.md` row while the ~23 KB session document sat beside it. Fixed 2026-08-28 — `mine.py` now resolves the session document from the row and builds `text` from its narrative sections, the row survives as `seed_ref` only, and the task prompts aim at a moment a reader could use rather than an engineering insight. **Merge is held** until the queue produces a post the operator would actually publish — that gate is the operator's judgement, not a passing test; see `planning/task_plan.md`. Authoritative design is the local, gitignored `planning/SPEC-x-comms-engine.md` rev 2; it supersedes `planning/SPEC.md` where the two disagree. Per-commit history (C1–C6, what each shipped and every `/review` finding) lives in `planning/progress.md` + `planning/findings.md` and in the commit messages — **not here**: this bullet is a current-state snapshot, not a changelog.
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

- **Invoke the review surface:** `python3 skill/helpers/queue.py review` — the primary path. `/session-publisher` in any Claude Code session still runs the manual seven-stage fallback.
- **Install:** `ln -s <repo>/skill ~/.claude/skills/session-publisher` — Claude Code auto-loads `SKILL.md` on next session start.
- **Configure notes dir:** export `SESSION_PUBLISHER_NOTES_DIR=/your/notes/path` in your shell profile (defaults to `~/personal-notes`).
- **Smoke-test helpers:** `python3 skill/helpers/select.py --days 7`, `python3 skill/helpers/thread.py --days 7`, `python3 skill/helpers/save.py "<session_source>" --body "test"`, `python3 skill/helpers/queue.py --validate`.
- **Smoke-test the drafting engine without spending a model call:** `X_COMMS_FORCE_SEED=1 python3 skill/helpers/draft.py --dry-run` assembles the prompt and reports its size; `--stub-response <file>` feeds a canned model reply through the full gate + write path; `X_COMMS_CLI=<script>` swaps the CLI for one that hangs or exits non-zero, which is how the timeout and exit-code branches are tested. A real end-to-end run is `X_COMMS_FORCE_SEED=1 python3 skill/helpers/draft.py --queue-dir /tmp/q` (add `--mode arc` for the Sunday batch path).
- **Smoke-test one ambient tick without a scheduler:** `skill/engine/run.sh --mode ambient` (or `--mode deep` for the arc path) runs the real pipeline against whatever `SESSION_PUBLISHER_NOTES_DIR` points at. Point that at a scratch directory holding a `SESSION_INDEX.md` and set `X_COMMS_CLI` to a stub script that prints a `{"is_error": false, "result": "<json>"}` envelope, and every branch — idle, capacity skip, expire, gate rejection, CLI failure — is exercisable for free. `X_COMMS_LOG_DIR` isolates the tick log.
- **No build pipeline.** Helpers are standalone Python 3.11+ scripts; stdlib only. `run.sh` is bash 3.2-compatible and shellcheck-clean at `-S warning`.
- **No test suite.** Smoke tests are inline and documented above. Friction-driven extension only.

## Conventions & gotchas

Hard-won rules. Each one cost a bug. The *stories* behind them are in `planning/findings.md`;
what follows is only what you must not forget.

### Paths and file formats

- **Never shell-expand a notes path.** It contains spaces, parentheses and `@`. Use `pathlib.Path`
  throughout; define `NOTES_BASE` once at the top of each helper. Unquoted `subprocess` /
  `os.system` args break silently.
- **`SESSION_INDEX.md` has no header row.** `## Sessions` starts pipe-delimited rows directly —
  8 positional columns: `| date | title | type | outcome | insight | ledger | asana | tags |`.
  Match `\| \d{4}-\d{2}-\d{2} \|`, read by position ([1] date, [2] title, [8] tags).
  `select.py` reads the whole file in one `read_text()` — not streaming, which sidesteps
  concurrent-append races.
- **`SKILL.md` frontmatter must match Claude Code's convention exactly** (`name`, `version`,
  one-sentence `description`). Wrong format = the skill vanishes from the list with no error.
- **`private-terms.local.md`: every line starting with `- ` is a denylist term** — its prose
  bullets therefore use `*`. Over-broad terms are the real hazard: rejections are logged
  body-free by design, so a draft killed by a too-generic term is near-untraceable.

### The two module-shadowing traps

`skill/helpers/` lands at `sys.path[0]` for anything run from it, so two helpers shadow stdlib
modules. Both filenames are fixed by contract — don't rename, work around:

- **`select.py` shadows stdlib `select`, which breaks `subprocess`.** `import subprocess` pulls in
  `selectors` → `import select` → our helper → `AttributeError: module 'select' has no attribute
  'select'`. Any helper here that shells out must drop its own directory from `sys.path` first, as
  `draft.py`, `mine.py` and `queue.py` do.
- **`queue.py` shadows stdlib `queue`.** `concurrent.futures` imports it internally, so a thread
  pool here dies with a misleading `SimpleQueue` error. `subprocess.run(timeout=)` is unaffected.
  Don't reach for a thread pool in this directory.

### The corpus (`examples.local.md`)

- **Its body format is load-bearing, not cosmetic.** `mirror.py` reads a body as a *contiguous* run
  of `>` lines and stops at the first line that isn't one — so a real blank line truncates the entry
  to its first paragraph. Write blank lines as a bare `>`, every other line as `"> "` (the regex eats
  exactly one space). Trailing whitespace on the body's **last** line is lost to `.rstrip()`; mid-body
  trailing whitespace survives, and one seeded post depends on it. **Any writer must round-trip
  through `mirror.py` and compare bytes.**
- **It is append-only, so nothing that can still refuse may run after an append.** Stage the queue
  entry first (all checks run, bytes in a temp file), append the corpus row, then `os.replace`. The
  intuitive order — corpus first, so a flip can't starve it — puts three rejection paths downstream
  of an irreversible write, and the retry can't undo it (the append is idempotent on `source_entry`,
  so attempt two reports success). A retry arriving with a *different* body is refused, not silently
  ignored.

### The queue

- **Neither it nor posted content ever lives in this repo.** Queue:
  `$NOTES_DIR/posts/x/queue/`. Approved posts: `$NOTES_DIR/posts/x/YYYY-MM-DD_post-NNN.md` (what
  `save.py` writes and `mine.py` dedups against). The public repo carries skill source only, and
  unposted bodies are private. `.gitignore` uses shape guards (`queue/`, `*queue*`, `seeds*`) with a negation keeping
  `skill/helpers/queue*.py` trackable. **That negation only works because no parent directory is
  excluded** — adding a `skill/helpers/` exclusion would silently untrack the helpers.
- **An entry id is unique only per second-of-day, and `.archive/` is part of that namespace.**
  `allocate_entry` steps a second on collision; once it also had to check the archive, because a
  reused id makes a stale archive file read as "someone archived this" (blocking approval forever)
  and lets `archive_entry` overwrite the older record.
- **`seed_key` has exactly one formula** — `queue.py seed_key_for()`. `cmd_add` and `mine.py`'s
  dedup both call it. Two hand-typed copies is how the anti-re-emission contract silently drifts.

### Headless drafting (`claude -p`)

- **It inherits the operator's whole user-level context and `draft.py` can only fence off part.**
  Working directory is neutralised (no project `AGENTS.md` auto-discovery), MCP scoped with
  `--strict-mcp-config`, built-in tools disabled with `--tools ""` — but `~/.claude/` cannot be
  scoped from the command line, so a `SessionStart` hook and the global rules files reach the
  drafting model. **The D6 anti-leak gate is the only barrier between that and a published body.**
  Nothing leaks today; that is *why* the gate isn't optional, and why new leak shapes are worth
  adding whenever one appears in those files.
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
- **`mine.py`'s repo matching is exact-slug-only, on purpose.** Tokenizing a tag like
  `voice-discovery` into `voice` + `discovery` lets `voice` substring-match `voice-capture-rag` and
  silently attribute one project's commits to another. Whole-tag equality against dirnames, never
  substring containment. `by_name` and `by_alias` stay separate dicts for the same reason: a
  prefix-stripped alias collision must null only the ambiguous *alias*, never an exact match.

### The seed's source material

- **The `SESSION_INDEX.md` row and the session document answer different questions — only the
  document is postable.** The row is written by the wrap-up skill for "what did I do this week",
  so it is a conclusion with the journey already compressed out; feeding it to a drafting model
  bought nine drafts about tests and reviews, rejected 9 of 9. `mine.py` builds `text` from the
  document's narrative sections; the row survives as `seed_ref` **only**, which is what it is good
  for — the ledger dedup key, asserted verbatim by C4's gate. Never merge the two: restating the
  row's `outcome`/`insight` beside the story puts the finished answer at the top of the source.
- **A document filename is not a transform of its index title, so resolution scores and refuses.**
  The wrap-up skill invents a shortened verb slug that drops, reorders and truncates words
  ("Closed RUNBOOK § 8, disproved the 390px defect, and turned off LiveKit observability" →
  `closed-runbook-8-and-disabled-livekit-observability`). `find_session_doc` scores what fraction
  of the *slug's* tokens the title accounts for — asymmetric, since the slug is the lossy side —
  and returns None on a score below threshold or on any tie. Degrading to the thin row is always
  better than attributing session A's story to session B's `seed_ref`, which would publish a claim
  about work that did not happen.
- **Sections written *at* a future agent are excluded, and that is a safety call.** `Transition
  Boot Prompt` and `Handover Context` are imperative instructions; quoting them into a headless
  drafting call hands the model a second, competing set of orders. They sit on the same deny list
  as the inventory tables, for a different reason. Everything not denied is kept, so sections the
  wrap-up skill grows later are included by default — the failure being corrected here was
  material that existed and was never read.
- **Seed `text` is real markdown and carries its own code fences.** `draft.py` quotes it inside a
  fence computed by `fence_for()` — longer than the longest backtick run in the text. A fixed
  ```` ``` ```` is closed by the seed's first fence, and everything after it stops being quoted
  source and starts reading as instructions.
- **Prompt assembly is ONE `re.sub` pass over the template, and must stay that way.** Sequential
  `str.replace` plus a post-substitution leftover scan breaks in both directions once `text` is a
  whole document: a `{{REPO_NAME}}` quoted in a repo-bootstrap session reads as an unfilled
  template slot and kills the tick (and since the seed never reaches `queue.py add`, no ledger
  event is written, so it is re-mined and re-kills every tick until it ages out), while a seed
  containing the literal `{{TASK}}` would have the real task substituted into it. One pass over the
  template means substituted text is output, never input.
- **`extract_narrative` redacts leak shapes before the prompt, and that is not the D6 gate.** D6
  inspects the output body and decides what may be published; this only shrinks what the model is
  shown. The index row never carried absolute paths, emails or tailnet addresses — a session
  document does. Redact rather than skip the document: those strings sit in ordinary prose, and
  dropping a whole session over one path costs far more material than it protects.
- **The tick line carries `docs=<n>` because this path degrades silently by design.** Every
  resolution failure returns `""` and falls back to the thin row, so a regression in document
  resolution would produce ticks that read exactly like healthy ones. `docs=-` is correct on the
  forced-fixture path (a fixture has no document); `docs=0` with `seeds_mined>0` means the fix has
  stopped working.

### launchd

- **`launchctl setenv` does not reach a `gui/` agent's environment.** `getenv` reports the value and
  the job never sees it — verified across a full `bootout`/`bootstrap` cycle. To pass a one-off flag,
  use the marker-file idiom: `run.sh` consumes a one-shot `$X_COMMS_LOG_DIR/force-seed`, and the tick
  line reports `forced=1`. Editing the plist to arm a test leaves the engine armed — don't.
- **launchd opens `StandardOutPath` before exec'ing the program**, so a script that `mkdir -p`s its
  own log directory cannot rescue its own first run's redirect. Hence the D9 tick line is written
  directly to `tick.log`, never echoed to stdout: the line that says what happened must not be the
  line that disappears. stdout/stderr remain the helpers' diagnostic channel.
- **A tick-log field is only parseable if reason codes can't contain its separator.** `rejected=` is
  comma-joined and most codes are clamped slugs — but `gate:unsourced_number:` appends digit runs
  *comma-separated*. `run.sh` rewrites commas to `;`, collapses whitespace and caps length, in
  `jreasons` for `rejected=` **and in `jfield` for every string**, since `reason=` takes a
  helper-supplied code the same way. The clamped-vocabulary assumption is true today, never guaranteed.
- **That same code is the one place body-derived content reaches the tick line** — a considered
  exception to "bodies never logged" (the digits are the diagnosis, and you never see the body
  otherwise). It is why the log stays local rather than treated as publishable-anywhere.

### Coupled counts (grep these together or they drift)

- **The drafting guide is dual-layer.** Layer 1 (rules 1–16, hook templates 1–5) = general builder
  norms. Layer 2 (rules 17–24, templates 6–10, AI anti-patterns) overrides it when the subject is
  LLM tooling or agentic systems. Templates 11–12 apply under either. **These counts drifted twice:**
  the guide carried 24 rules from v1.3 while four dependent files still said 23. Renumbering means
  grepping `SKILL.md`, `README.md` and `examples-template.md` in the same commit.
- **Three gitignored files sit in `skill/prompts/`** — `persona.local.md`, `examples.local.md`,
  `private-terms.local.md` — covered by `*.local.md` plus `skill/prompts/persona*.md`. `insights.local.md`
  is the D14 socket: read iff present, absent is correct today.

## Out of scope

- ❌ X application programming interface — write/publish path (manual-paste gateway is v0; direct API only if friction surfaces)
- ❌ X application programming interface — read path for automated reaction fetching (explicit v0.2 feature work; needs X dev account approval)
- ❌ Auto-trigger from a daily-routine workflow — **superseded.** The launchd agent IS the trigger; it just is not wired to the routine.
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
