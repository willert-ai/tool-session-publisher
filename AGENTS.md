<!-- Project context for any AI agent. NOT agent persona — see role prompts -->
# AGENTS.md — session-publisher

## Project context

Claude Code skill that turns a session wrap-up file into a reviewed draft post for X through a seven-stage interactive conversation. Drafts are saved to the operator's configured notes directory (`$SESSION_PUBLISHER_NOTES_DIR`, default `~/personal-notes`). The skill never publishes directly — the operator pastes the approved draft into their X scheduler of choice (or x.com directly) for publication.

## Stack & key dependencies

- Language: Python 3.11+
- Dependencies: standard library only (no `requirements.txt`)
- Critical external services: none in v0 (no X API, no separate LLM API key)
- Notes directory: `$SESSION_PUBLISHER_NOTES_DIR` env var; falls back to `~/personal-notes`

## Working state

- **Authoritative design:** `planning/SPEC.md` (Claude Code skill, manual-paste gateway, 7-stage interactive conversation, drafts saved to `$NOTES_DIR/posts/x/`).
- **Skill shipped:** `skill/` directory. Files: `SKILL.md`, `helpers/{select,save,thread}.py`, `prompts/drafting-guide.md`. All helpers stdlib-only. Install via `ln -s <repo>/skill ~/.claude/skills/session-publisher`.
- **Pre-mortem:** `planning/PreMortem-session-publisher-2026-05-11.md` documents 4 Tigers + 3 Elephants identified before the build window and how each was resolved.
- **Stage 5.5 corpus-mirror (feature thread):** Phase C shipped 2026-05-16. `skill/helpers/mirror.py` is a pure-loader helper (parses `examples.local.md`, drops `near_duplicate_of` cluster non-reps, emits JSON). `SKILL.md` carries the new Stage 5.5 section (load → infer+select → rewrite → prompt → response). `examples-template.md` documents `guide_compliance` + `near_duplicate_of`. **Pivot:** SPEC v0.2 §4 deterministic tag-overlap pipeline superseded — Claude does semantic selection in Stage 5.5 prose. Rationale annotated inline in the SPEC + in `planning/findings.md`. Next: first end-to-end run with new stage will calibrate register-fit honesty. Authoritative design: SPEC v0.2 (annotated) + SKILL.md §5.5 (shipped behavior).

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
  writes the FERO-Log SESSION document; these project-local files are the
  same log scoped to this project. If a session shipped no project content
  (meta-work only), still append a one-line entry to `progress.md` noting
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
- **Smoke-test helpers:** `python3 skill/helpers/select.py --days 7`, `python3 skill/helpers/thread.py --days 7`, `python3 skill/helpers/save.py "<session_source>" --body "test"`.
- **No build pipeline.** Helpers are standalone Python 3.11+ scripts; stdlib only.
- **No tests in v0.** Smoke tests are inline. Friction-driven extension only.

## Conventions & gotchas

- **Notes path with spaces / parentheses / @ signs.** `pathlib.Path` handles these safely; never shell-expand. Any `subprocess` or `os.system` call with unquoted special chars silently breaks. Define `NOTES_BASE` as a single constant at the top of each helper.
- **SESSION_INDEX.md has no conventional header row.** The `## Sessions` section starts pipe-delimited rows directly: `| YYYY-MM-DD | title | type | outcome | insight | ledger | asana | tags |` — 8 positional columns. Parser: find lines matching `\| \d{4}-\d{2}-\d{2} \|`, extract by position [1]=date [2]=title [8]=tags.
- **SKILL.md frontmatter must match Claude Code convention exactly.** YAML with `name`, `version: "0.x.x"`, `description: <one-sentence-for-trigger-matching>`. Wrong format = skill silently absent from skill list.
- **`select.py` reads SESSION_INDEX in one `Path.read_text()` call.** Not streaming. Avoids concurrent-append edge cases.
- **Posts content lives outside the repo.** `$NOTES_DIR/posts/x/YYYY-MM-DD_post-NNN.md`. The public repo carries the skill source only.
- **Drafting LLM is the running Claude.** No separate Anthropic API call, no `.env`, no API key. The skill reads `skill/prompts/drafting-guide.md` and applies the guide via the model already in the session.
- **Drafting guide is dual-layer.** Layer 1 (rules 1–15, hook templates 1–5) = general builder norms. Layer 2 (rules 16–23, hook templates 6–11, AI anti-patterns) = AI/agentic overrides; takes precedence when posting about LLM tools or agentic systems.
- **Operator pastes into an X scheduler.** v0 does NOT call X API. Hand-off block prints the post body; operator copies into the X scheduler (or x.com) of their choice.
- **Reaction recap is optional in v0.** Skill never fails on missing annotations. Automated reaction reading via X read-only API is explicit v0.2 work.

## Out of scope

- ❌ X application programming interface — write/publish path (manual-paste gateway is v0; direct API only if friction surfaces)
- ❌ X application programming interface — read path for automated reaction fetching (explicit v0.2 feature work; needs X dev account approval)
- ❌ Auto-trigger from any daily-routine workflow (manual invocation in v0)
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
- ❌ Anything requiring infrastructure outside Claude Code (cron, GitHub Actions, servers, databases — all rejected by SPEC v0)

## References

- **Authoritative design:** `planning/SPEC.md`
- **Pre-mortem:** `planning/PreMortem-session-publisher-2026-05-11.md`
- **Drafting guide:** `skill/prompts/drafting-guide.md` (23 rules + 11 hook templates)
