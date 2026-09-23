<!-- Project context for any AI agent. NOT agent persona — see role prompts -->
<!-- EDIT TARGET: AGENTS.md — CLAUDE.md is a symlink to this file. The harness refuses Edit/Write on CLAUDE.md; go to AGENTS.md directly. -->
# AGENTS.md — session-publisher

## Project context
<!-- STATE-ONLY guardrail: this section is a SHORT current-state snapshot, not a log. Keep the strategic frame (what the project is, who it serves) above the fab:state markers and ONE paragraph of current state between them; REPLACE that paragraph in place at every session close — never append dated entries or per-session narrative anywhere in this section. Session history → planning/progress.md; durable conventions and measured facts → § Conventions & gotchas; known gaps → § Out of scope. Enforced by hooks/check_context_size.py (from github-ops templates/hooks/) through the pre-commit hook wherever hooks/ is armed with both files: this section stays ≤ 6,000 bytes; the marked paragraph stays ≤ 3,500 characters, exactly one paragraph, and grows ≤ 800 characters per ordinary commit (merges skip only growth); and the whole file stays under 32,768 bytes. -->

An ambient drafting system for X, packaged as a Claude Code skill. A scheduled local agent mines the operator's own session history, drafts finished 400–650-character post bodies through a headless `claude -p` with no session open, and files them in a review queue; the operator's only obligation is one action per entry. A seven-stage interactive conversation remains as the manual fallback path. Everything is written under the operator's configured notes directory (`$SESSION_PUBLISHER_NOTES_DIR`, default `~/personal-notes`), never in this repo. The system never publishes directly — the operator pastes an approved body into their X scheduler of choice (or x.com directly).

<!-- fab:state-begin -->
As of the 2026-09-07 audit (`strategy/REPOSITORY_AUDIT.md`): 10 drafts queued, 13 killed, 1 expired and 1 approved-and-copied, that approval the only captured ambient one, so August's no-approval-yet claim is stale (its 13 rejections remain real); ambient publication unconfirmed; the usefulness gate open; the review reminder firing in production, six of its eight scheduled outcomes AppleEvent timeout failures. The owner found drafts better-written but too technical, detached and insufficiently personal. Since the audit one runtime change has landed: the miner finds session documents under `sessions/` only (commit `9053e58`, PR #9, 2026-09-18). Next, per that audit: implementation, private-state reconciliation and installation, each needing its own authority.
<!-- fab:state-end -->

## North Star
<!-- Contract: the heading '## North Star' is consumed by the github-ops retrofit audit + (future) fab-spec repo-research — keep it verbatim. This is DURABLE-INTENT (Vision + scope/PRD pointers): human-owned, rarely changes, NOT working-state — no agent's session-close step rewrites it — the session-close procedure (`~/.config/agent-rules/procedures/session-close.md`) never edits it, whichever agent runs it. WHERE the vision/scope docs live is project-dependent: a separate strategy home if one exists (point OUT to it), in-repo only for a self-contained product. An honest "none yet" beats a stale vision doc. See github-ops `templates/README.md` § Repo doc model. -->
- **Vision** (ideal end-state): a running narration of who you are and what you do — surfaced
  from the real work, made visible on its own and at no effort.
- **Scope / PRD** (what the current release — v1/beta — IS): the *how* that vision implies —
  the operator's own session history mined unattended, drafted headlessly into finished
  400–650-character bodies against a researched best-practice guide (24 rules, 12 hook
  templates) and a register calibrated from operator-verdicted drafts, then filed into a
  review queue held outside this repo, so the only human act is one verdict per entry. A
  seven-stage interactive conversation survives as the manual path. Nothing is ever published
  by the system — an approved body is pasted into the operator's own X scheduler.
  Authoritative design: `planning/specs/SPEC-x-comms-engine.md` rev 2 — **local and gitignored**,
  absent from the public clone; `planning/specs/SPEC.md` v0.3 is the superseded pull model, valid
  only where the two agree. Public surface and what is out of scope: `README.md` § Scope.
- **Current state**: this file, § Project context

## Stack & key dependencies

- Language: Python 3.11+
- Dependencies: standard library only (no `requirements.txt`)
- Critical external services: none in v0 (no X API, no separate LLM API key)
- Notes directory: `$SESSION_PUBLISHER_NOTES_DIR` env var; falls back to `~/personal-notes`

## Working state

- **Repository audit — 2026-09-07:** [strategy/REPOSITORY_AUDIT.md](strategy/REPOSITORY_AUDIT.md) is a proposed complete delivery route, independently reviewed and refuted (all findings resolved).
- **Task plan, findings, progress:** local and gitignored (`.gitignore:39–41`; § Where this repository's working state lives). Dated working state from here moved on 2026-09-23 to the Mac Studio clone's `planning/progress.md`; the engine overview, smoke tests and gotchas moved to `docs/ambient-engine.md`.

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

<!-- fab:working-state-begin -->
### Working-state discipline

Four locations carry the project's working state. Two writers keep them current at the close of a
session, and both cite this block rather than restate it: the session-close procedure
(`~/.config/agent-rules/procedures/session-close.md`) is the attended implementation, run by
whichever agent holds the session, and `session-factory/contracts/wrapup-executor.md` is the
factory's, rendered from the Linear trail at chain close. Update discipline:

| File | Content | Cadence |
|------|---------|---------|
| `AGENTS.md` § Project context | SHORT current-state snapshot: the strategic frame above the `fab:state` markers, ONE paragraph of current state between them. REPLACE the marked state paragraph in place — never append per-session narrative; history → `progress.md` | Same session as the state change (not deferred to next session). The size guard (`hooks/check_context_size.py`, from github-ops `templates/hooks/`, run by the pre-commit hook wherever `hooks/` is armed with both files) enforces the ceilings — the writer rule and the guard are one policy seen from two sides. |
| `planning/task_plan.md` | The plan's state — the current phase or stream, its gates, history and decisions | When a phase or stream opens, ships or blocks |
| `planning/progress.md` | Chronological session log — append new entries at the bottom (newest last, never at the top) | End of every session that wrote in this repository — no exceptions |
| `planning/findings.md` | Session-level reframes, pivots, gotchas, re-evaluation list — append at the bottom (newest last, never at the top) | Mid-session via 2-Action Rule + end-of-session catch-up |

Three discipline rules tie these to action:

- **2-Action Rule:** after every 2 search/read operations, write findings to
  `planning/findings.md`. Honor system — no hook enforces it.
- **Plan checkpoints:** when a phase or stream opens, ships or blocks, update
  `task_plan.md` to record it and declare the execution context for what comes
  next (model, thinking effort, role and context).
- **Session-end catch-up:** a close that wrote inside this repository (via the
  agent's session-close step — Claude Code's is `/wrap-up` — or manually)
  appends to `progress.md`, and to `findings.md` when there are findings. The
  same step writes the session record under `FERO-Log/sessions/`; these
  project-local files are the same log scoped to this project. A session that
  wrote nothing here ends in its session record alone.

#### Who writes at close

| Close | Writer | What it writes | When |
|-------|--------|----------------|------|
| Attended close | any runtime running the session-close procedure (`~/.config/agent-rules/procedures/session-close.md`) | the session record under `FERO-Log/sessions/`, and — when the session wrote in this repository — the four locations above, each at its cadence | at the end of a work session — proposed by the agent at a natural end, or invoked by the operator, a boot's exit block or a skill's last step |
| Factory chain close | `session-factory/contracts/wrapup-executor.md` | the four locations above, rendered from the Linear trail, and a header-only session record | once per chain, when the factory closes it |

The frame outside the `fab:state` markers is never touched by the factory, and by an attended close only when the operator asks in that session.
The close commits on the session's branch; a ruled branch (or rules that cannot be read) or a runtime account means a close branch and a pull request.
How each writer edits — markers, size bounds, commit and push — lives in the writer, not here.
<!-- fab:working-state-end -->

### Where this repository's working state lives

The three `planning/*.md` files are gitignored in this public repository (`.gitignore:39–41`). They exist locally and the discipline above applies to them the same way, but each clone keeps its own copies: the Mac Studio's and the MacBook's are separate, unsynced files that git does not carry. So a close, attended or factory, commits `AGENTS.md` alone: the session-close delivery block drops each ignored `planning/*.md` path with a printed line (`…: ignored in this repository — not committed`) and commits the rest, and the factory's worktree has no trio and never force-adds one.

### Security boundaries

- **API keys never in chat or screen-shared windows.** If a key is exposed (paste, screenshot, log), generate a new one immediately — treat the old key as compromised.
- **Admin mode (`--dangerously-skip-permissions`)** — gated on three predicates, ALL must hold:
  1. The plan is locked: design doc is current and approved
  2. The work is well-scoped: no ambiguity in the next step
  3. The project folder is sandboxed: not a system directory, not a folder with important files unrelated to the task
  Never use admin mode on a first-ever session in a folder; the calibration sense for "what the agent will likely do" must be earned first.

### Clarity discipline

- **Clarity beats token optimization.** Vague prompts force exploratory work that costs more tokens than the optimization saves. Invest tokens in the spec / brainstorm; save tokens during execution by working from a sharp plan.

<!-- fab:folder-discipline-begin -->
### Folder discipline
- **Where a new document goes — decide before creating it.** External material you did not
  write (research outputs, transcripts, third-party reports) → `research/`, read-only. Your
  own durable design, vision, playbook or audit → `strategy/`. Working state, specs, boots and
  kickoffs → `planning/` (`planning/specs/`, `planning/handoffs/`). User-facing guides →
  `docs/`; how-to-run-it → `OPERATIONS*.md` at root. Create the folder when the first file
  needs it, never before.
- **`planning/` root holds exactly the working-state trio** (`task_plan.md`, `progress.md`,
  `findings.md`), with `handoffs/` and `specs/` as its canonical subfolders. The deciding
  test is structural: is this file rewritten as a matter of course at the close of an ordinary
  working session? Yes → the trio. No → `strategy/` (durable intent, human-owned) or another
  folder above. `~/tools/github-ops/scripts/repo-compliance.sh` check 16 flags any **file**
  at the planning root besides those three (advisory — a warning, not a failure). It does not
  flag subfolders; `planning/` subfolder names are check 14's job.
- **Before creating any other top-level folder or `planning/` subfolder, look at the normative
  taxonomy:** `~/tools/github-ops/templates/README.md` § Folder taxonomy. Conceptual folders
  are `planning/` `strategy/` `research/` `docs/` `scripts/` `tests/` `hooks/` `assets/`
  `archive/` `templates/` `src/`, and inside planning `handoffs/` `specs/`. Use those names
  exactly — no case, plural or synonym variants (`HANDOFFS/`, `plans/`, `_archive/`).
- **A new kind of conceptual folder is added to the taxonomy first, then used here.** The
  project's own code and data folders (a package dir, `web/`, `data/`, `supabase/`) are yours
  to name; conceptual folders are not. Root holds only the allowed files (README, AGENTS,
  CLAUDE, LICENSE, `OPERATIONS*.md`, ecosystem files) — everything else lives in a folder.
- `~/tools/github-ops/scripts/repo-compliance.sh .` reports variants, stray root files and
  the rest of the doc model; the session-start hook prints its result at the top of every
  session, so a gap is never a surprise at audit time.
<!-- fab:folder-discipline-end -->

## Build & run

This is a Claude Code skill, not a standalone CLI.

- **Invoke the review surface:** `python3 skill/helpers/queue.py review` — the primary path. `/session-publisher` in any Claude Code session still runs the manual seven-stage fallback.
- **Install:** `ln -s <repo>/skill ~/.claude/skills/session-publisher` — Claude Code auto-loads `SKILL.md` on next session start.
- **Configure notes dir:** export `SESSION_PUBLISHER_NOTES_DIR=/your/notes/path` in your shell profile (defaults to `~/personal-notes`).
- **Smoke-test helpers:** `python3 skill/helpers/select.py --days 7`, `python3 skill/helpers/thread.py --days 7`, `python3 skill/helpers/save.py "<session_source>" --body "test"`, `python3 skill/helpers/queue.py --validate`.
- **Engine smoke tests** (drafting, one tick, the review nag's install) moved on 2026-09-23 to `docs/ambient-engine.md` with the engine overview and gotchas.
- **No build pipeline.** Helpers are standalone Python 3.11+ scripts; stdlib only. `run.sh` and `review_reminder.sh` are bash 3.2-compatible and shellcheck-clean at `-S warning`.
- **No test suite.** Smoke tests are inline and documented above. Friction-driven extension only.

## Conventions & gotchas

Hard-won rules. Each one cost a bug. The *stories* behind them are in `planning/findings.md`;
what follows is only what you must not forget.
The engine's reference gotchas (the headless quota floor and per-tick yield, the first two `launchd` gotchas, the 07:45 review nag) moved on 2026-09-23 to `docs/ambient-engine.md` with the engine overview and smoke tests.

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
- **`mine.py`'s repo matching is exact-slug-only, on purpose.** Tokenizing a tag like
  `voice-discovery` into `voice` + `discovery` lets `voice` substring-match `voice-notes` and
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

- **A tick-log field is only parseable if reason codes can't contain its separator.** `rejected=` is
  comma-joined and most codes are clamped slugs — but `gate:unsourced_number:` appends digit runs
  *comma-separated*. `run.sh` rewrites commas to `;`, collapses whitespace and caps length, in
  `jreasons` for `rejected=` **and in `jfield` for every string**, since `reason=` takes a
  helper-supplied code the same way. The clamped-vocabulary assumption is true today, never guaranteed.
- **That same code is the one place body-derived content reaches the tick line** — a considered
  exception to "bodies never logged" (the digits are the diagnosis, and you never see the body
  otherwise). It is why the log stays local rather than treated as publishable-anywhere.
- **Both installed jobs execute this mutable checkout** (`strategy/REPOSITORY_AUDIT.md:81`), so until the runtime installation is pinned or snapshotted a branch switch here can change unattended behavior.

### Coupled counts (grep these together or they drift)

- **The drafting guide is dual-layer.** Layer 1 (rules 1–16, hook templates 1–5) = general builder
  norms. Layer 2 (rules 17–24, templates 6–10, AI anti-patterns) overrides it when the subject is
  LLM tooling or agentic systems. Templates 11–12 apply under either. **These counts drifted twice:**
  the guide carried 24 rules from v1.3 while four dependent files still said 23. Renumbering means
  grepping `SKILL.md`, `README.md` and `examples-template.md` in the same commit.
- **Three gitignored files sit in `skill/prompts/`** — `persona.local.md`, `examples.local.md`,
  `private-terms.local.md` — covered by `*.local.md` plus `skill/prompts/persona*.md`. `insights.local.md`
  is the D14 socket: read iff present, absent is correct today.
- **All three are SYMLINKS into `$SESSION_PUBLISHER_NOTES_DIR/x-comms/prompts/`; the real files live
  there and must stay there.** Gitignoring them keeps them out of a public repo, which is the point —
  but it also means they are in no commit, appear in no diff, cannot be reviewed by a subagent reading
  a change set, and are **not recoverable from git**. `persona.local.md` is the register the drafting
  model actually obeys; losing it loses the calibration that produced it. The notes directory is
  Drive-synced, so it is versioned and off-machine, and it is where the queue and the posts already
  live for exactly this reason. Consequences worth knowing: the symlink targets are **absolute**, so
  changing `SESSION_PUBLISHER_NOTES_DIR` breaks them (re-point, don't re-create); and a dangling link
  fails the tick closed with `engine:persona` rather than drafting without a register, which is the
  correct failure. **A change to any of these three is invisible to `/review` — say so when dispatching
  one, and have it read the file directly.**

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
- **Repo conventions (normative):** `~/tools/github-ops/templates/README.md` § Folder taxonomy · check: `~/tools/github-ops/scripts/repo-compliance.sh`

- **Authoritative design:** `planning/specs/SPEC-x-comms-engine.md` rev 2 (local, gitignored) · superseded v0 pull model: `planning/specs/SPEC.md`
- **Pre-mortem:** `strategy/PreMortem-session-publisher-2026-05-11.md`
- **Drafting guide:** `skill/prompts/drafting-guide.md` (24 rules + 12 hook templates)
