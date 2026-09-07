# SPEC — session-publisher (skill, manual-paste gateway, v0.3)

**Locked:** 2026-05-11 (revision 3 — supersedes v0.2 in-place)
**Status:** Pre-mortem complete — awaiting operator sign-off
**Hard ship:** Wednesday May 13, 2026 — end of day
**Build budget:** Monday afternoon (drafting-guide research, ~45 min) + Tuesday morning 09:00–13:00 (build) + Wednesday morning (test + ship)
**Predecessor:** `PRD_cron-architecture-superseded-2026-05-11.md` (cron architecture, abandoned)
**Revision history (in place):**
- v0.1 — skill that posts directly via X application programming interface; superseded same day by manual-paste gateway pivot
- v0.2 — manual-paste gateway; added narrative-thread, reaction-recap, and topic-recommendation stages; reaction recap assumed manual operator annotations
- v0.3 — current — clarifies that reaction recap is OPTIONAL in v0; automated reaction reading via X read-only API is explicit v0.2 feature work, not v0

---

## 1. Summary

`session-publisher` is a Claude Code skill that turns evening session wrap-ups into reviewed posts on X — through a guided conversation with the operator, not an automated pipeline. It is invoked manually at the end of an evening routine. The skill reads the operator's narrative thread from the last seven days, summarises the reactions on the most recent three posts, recommends a topic grounded in today's actual ship work, drafts the post using a researched best-practice guide, iterates with the operator until approval, and saves the approved post to the configured notes directory. The operator then pastes the post body into their X scheduler of choice (or x.com directly) for publication. The skill does not call the X application programming interface in v0.

The skill exists to support a build-in-public cadence: first substantive X post under the operator's own name plus a public GitHub repository carrying the skill source.

---

## 2. Surface area (the entire system)

```
INPUT    — today's SESSION_*.md (just created by /wrap-up) + last 7 days of unposted sessions
CONTEXT  — narrative thread (past 7 days of posts from $NOTES_DIR/posts/x/) + reactions on last 3 posts
TOPIC    — skill recommends what to post based on today's session + thread state; operator approves angle
DRAFT    — Claude drafts post applying skill/prompts/drafting-guide.md (researched best practice)
REVIEW   — interactive edit loop in chat: "rewrite hook", "make more concrete", "post 1", "skip"
OUTPUT   — approved post saved to $NOTES_DIR/posts/x/YYYY-MM-DD_post-NNN.md with frontmatter
HANDOFF  — skill prints post body; operator pastes into the X scheduler of their choice
```

Anything outside these seven stages does not ship in v0.

---

## 3. Architecture

A single Claude Code skill lives in the public repository `willert-ai/tool-session-publisher`. The operator symlinks `~/.claude/skills/session-publisher/` to `~/tools/session-publisher/skill/`. The skill is invoked manually at the end of evening routine (`/session-publisher`).

The skill is `SKILL.md` plus three short Python helpers and one researched markdown drafting guide. There is no cron, no GitHub Actions, no X application programming interface call, no separate Claude application programming interface key, no `.env`. The skill reads and writes plain markdown — input from $NOTES_DIR session files, output to $NOTES_DIR post files, anti-duplicate tracked by the existence of files in the posts folder.

The skill repository itself is the build-in-public artifact. The post content lives in $NOTES_DIR (which is not in any git repository) because the posts are personal narrative content, not infrastructure.

---

## 4. Skill flow (what `SKILL.md` instructs Claude to do)

### Stage 1 — Context primer

1. Run `python skill/helpers/thread.py --days 7`. Output: list of files in `$NOTES_DIR/posts/x/` from the last seven days, with frontmatter (session-source, posted-status, x-url, reactions).
2. Identify today's session wrap-up file by date.
3. Read the body of today's session file (just the candidate, not all of $NOTES_DIR).
4. Read the bodies of any unposted sessions from the last seven days, filtered by `focus.yaml` if present.

### Stage 2 — Narrative-thread recap (+ reaction recap if annotated)

Present narrative thread to operator:

```
Narrative thread — past 7 days

Posts: [N]
- [date] [post topic line] — [status: posted / drafted / skipped]
- [date] [post topic line] — ...
- ...

Thread patterns: [skill's read of voice consistency, topic coverage, what's working]
```

If any of the most-recent 3 posts have `reactions:` populated in their frontmatter, also present:

```
Reaction observations (where annotated):
1. [date] — "[post excerpt]"
   Reactions: [annotation text]
   What hit / missed: [skill's reading]
2. ...
```

If `reactions:` is empty across all recent posts (likely on the first several invocations — operator has not yet built the annotation habit, and the v0.2 feature for automated reaction reading via X read-only API has not shipped), skip the reaction-observations block with a one-line note:

```
Reactions: no annotations yet — automated reaction reading is a v0.2 feature
```

The skill never fails on missing annotations. Reaction recap is value-add when present, no-op when absent.

### Stage 3 — Topic recommendation

Skill reasons about today's session(s) + narrative thread + operator's recent Groundhog and Double Down lessons (read from current `Running_Week_YYYY-WNN.md` last-evening section if the file exists — if not found, skip that context and proceed on session content alone), and proposes:

```
Today's session(s):
- [Title 1] — [primary outcome]
- [Title 2] — [primary outcome]

Recommended topic for today's post:
> [One sentence framing]

Rationale: [why this topic, why now, how it fits the thread]
Alternative angles: [2 other framings the operator could pick]

Approve angle, switch to alternative, or propose your own?
```

Wait for operator response.

### Stage 4 — Drafting

Skill reads `skill/prompts/drafting-guide.md` (researched best-practice guide — see Stage A of the build queue) and produces a single tweet (≤280 characters) on the approved angle, grounded in the source session.

### Stage 5 — Interactive review

Present draft inline. Wait for operator instruction. Accepted instructions:

- `looks good` / `approve` — proceed to Stage 6
- `rewrite hook` / `rewrite ending` — partial regen
- `make more concrete` / `cut the hedge` / `tighten` — targeted edit
- `regenerate` — full new draft on same angle
- `different angle` — back to Stage 3
- `skip` — discard, do not save
- operator types a rewrite themselves — accept as final

Loop until `approve` or `skip`.

### Stage 6 — Save to $NOTES_DIR

Call `python skill/helpers/save.py <session-source> <post-body>` which writes:

```
$NOTES_DIR/posts/x/2026-05-13_post-001.md
---
created_at: 2026-05-13T20:14:32+02:00
session_source: 2026-05-13 - <title>
status: drafted          # operator updates to 'posted' after publication
x_url:                   # operator pastes URL back here after publication
reactions:               # operator appends bullets over the following days
  - 
notes:
---

<post body, ≤280 chars>
```

### Stage 7 — Handoff

Skill prints the final post body in a copyable block and a short reminder:

```
✅ Saved to $NOTES_DIR/posts/x/2026-05-13_post-001.md

Paste this into your X scheduler → schedule / publish:

   <post body>

After publication, update the frontmatter:
- status: posted
- x_url: <the URL>
- reactions: add daily observations over next few days
```

End of skill invocation.

---

## 5. File layout (what Tuesday morning builds)

```
tool-session-publisher/                      (public repo)
├── README.md                                (already present — rewrite for skill model)
├── LICENSE                                  (already present)
├── AGENTS.md, CLAUDE.md → AGENTS.md         (already present)
├── .gitignore                               (already present)
├── focus.yaml                               (optional; project filter)
├── skill/
│   ├── SKILL.md                             (the skill itself, ~150 lines)
│   ├── helpers/
│   │   ├── thread.py                        (reads $NOTES_DIR/posts/x/ for narrative thread, ~40 lines)
│   │   ├── select.py                        (reads SESSION_INDEX + filters by focus.yaml + posted state, ~40 lines)
│   │   └── save.py                          (writes $NOTES_DIR/posts/x/YYYY-MM-DD_post-NNN.md, ~25 lines)
│   └── prompts/
│       └── drafting-guide.md                (Monday afternoon research output; <2 pages)
└── planning/
    ├── SPEC.md                              (this file, public)
    └── PreMortem-session-publisher-2026-05-11.md  (public)
    # findings.md, progress.md, task_plan.md, and PRD_*.md are kept
    # local-only (see .gitignore) — internal running logs, not shipped.

$NOTES_DIR/                                    (separate location, not in repo)
└── posts/
    └── x/                                   (created Tuesday on first save)
        ├── 2026-05-13_post-001.md
        ├── 2026-05-14_post-001.md
        └── ...
```

---

## 6. Decisions locked

| # | Decision | Locked value |
|---|----------|---------------|
| a | Form factor | Claude Code skill |
| b | Invocation | Manual `/session-publisher` at end of daily-routine evening (after E6) |
| c | Language for helpers | Python 3.11+ |
| d | Posting mechanism | Operator pastes into an X scheduler (or x.com). X application programming interface integration is OUT of v0 (deferred to friction-driven extension) |
| e | Drafting LLM | The running Claude (no separate application programming interface call) |
| f | Gate | Multi-turn interactive conversation in chat (topic approval → draft review → edits → final approve) |
| g | Drafts and posts storage | `$NOTES_DIR/posts/x/YYYY-MM-DD_post-NNN.md`. **Not** in the public repository. |
| h | Anti-duplicate | A session whose filename appears as a `session_source` in any file under `$NOTES_DIR/posts/x/` is considered already-handled |
| i | Project filter | Optional `focus.yaml` at repo root listing folder or repo names; case-insensitive substring match against title + tags columns of `SESSION_INDEX.md`, with github-ops type prefixes (`tool-`, `app-`, `scripts-`, `ref-`) stripped |
| j | Session scope | Today's wrap-up file plus the last seven days of unposted entries from `SESSION_INDEX.md` |
| k | Posting format | Single tweet, ≤280 characters. No threads, no images |
| l | Drafting guide | Researched best-practice guide stored as `skill/prompts/drafting-guide.md`. Researched Monday afternoon via Perplexity (~45 min) before Tuesday build. |
| m | Repository visibility | Public on GitHub by Wednesday end of day. Repository carries skill source only — no personal post content. |
| n | Skill location | Source-of-truth in `~/tools/session-publisher/skill/`. Symlink `~/.claude/skills/session-publisher/` to it. |
| o | Review surface | Computer only in v0. No mobile. |
| p | Reaction tracking | **Optional** in v0. Operator MAY annotate `reactions:` frontmatter of each post manually over the days following publication. Skill reads annotations on next invocation if present; gracefully skips reaction recap if absent. Automated reaction reading via X read-only application programming interface is explicit v0.2 work (see Out-of-v0). |
| q | Narrative-thread depth | Past 7 days; reaction recap covers most recent 3 posts |

---

## 7. Scope

### v0 ships Wednesday

- The seven-stage skill working end-to-end in a single conversation
- `focus.yaml` project filter (optional)
- Researched drafting guide (`skill/prompts/drafting-guide.md`)
- Narrative-thread summary from past 7 days
- Reaction recap from last 3 posts (reads operator-annotated frontmatter)
- Topic recommendation step with rationale + alternatives
- Interactive review loop
- Saves approved drafts to `$NOTES_DIR/posts/x/`
- Hand-off block ready to paste into an X scheduler
- Public repository on GitHub
- README readable by a stranger
- One smoke test per helper script

### Out of v0 (deferred to "Future" or never)

- X application programming interface posting — write/publish path (manual-paste gateway is v0; direct API only if friction surfaces)
- **X application programming interface reading — automated reaction fetching for past 3 posts. Explicit v0.2 feature.** Read-only access (post lookup by URL, fetch reply count / like count / quote-tweet count and recent reply text). Lights up the reaction-recap stage automatically without operator annotation burden. Deferred to v0.2 because (a) it requires X dev account approval that v0 deliberately avoids, and (b) the v0 build budget cannot absorb it without slipping Wed EOD.
- Auto-trigger from `daily-routine` (manual invocation is v0; auto-chain only if operator hits a wall)
- Threads, images, quote-tweets
- Multi-platform (LinkedIn, Mastodon, Bluesky)
- Reaction auto-fetching from X (manual annotation in v0; automated only if a scheduler tool or the X application programming interface exposes the data cleanly later)
- Engagement metrics, follower count, analytics dashboards
- Web user interface
- Mobile review
- Multi-operator
- Telegram, email, or Asana gate channels
- A/B testing of draft variants
- Advanced focus-filter modes (regex, exclude lists, time-windowed focus)
- Automated post timing optimisation

---

## 8. Build queue

| Stage | Window | Work |
|-------|--------|------|
| A — Drafting-guide research | ~45 min research block | Web research on X / Twitter posting best practices for solo builders in public. Distil into one-to-two-page `skill/prompts/drafting-guide.md`. Topics: hook structures, one-idea-per-post rule, concrete vs abstract, specific results, voice consistency, what to ignore (likes are noise), engagement signals (replies + quote-tweets = signal), build-in-public conventions. Output: `skill/prompts/drafting-guide.md`. |
| B — Build | Tuesday 2026-05-12, 09:00–13:00 local time | Write `thread.py`, `select.py`, `save.py`, `SKILL.md`. Rewrite `README.md` for skill model. Create `$NOTES_DIR/posts/x/` directory. Symlink `~/.claude/skills/session-publisher/`. Smoke-test each helper standalone. End-to-end dry run with a recent session as test input. |
| C — Ship | Wednesday 2026-05-13, 09:00–13:00 | End-to-end run with TODAY'S session wrap-up. Iterate until first real draft saved to $NOTES_DIR. Flip repository to public. Polish README. Commit. |
| D — Operator first paste | Shortly after ship | Operator pastes the first approved draft into their X scheduler and publishes. First X post live under operator's own name. K4 satisfied. |
| Flex | Post-ship days | Not pre-blocked. Used for opportunistic friction-driven extension or other work. |

---

## 9. Done criteria (falsifiable)

| # | Criterion | Check | Target |
|---|-----------|-------|--------|
| K1 | Repository public on GitHub | `gh repo view willert-ai/tool-session-publisher --json visibility` returns `PUBLIC` | Wed EOD |
| K2 | Skill discoverable in Claude Code | `/session-publisher` appears in skill list inside a fresh Claude Code session | Wed EOD |
| K3 | End-to-end dry run succeeds | Invoke skill, see narrative-thread recap (empty on first run), see topic recommendation, iterate on draft, approve, file saved at `$NOTES_DIR/posts/x/YYYY-MM-DD_post-001.md` | Wed EOD |
| K4 | First real X post live | Operator pastes approved draft into an X scheduler (or x.com) and publishes; updates frontmatter with `x_url:` and `status: posted` | Soon after K3 |
| K5 | Substantive cadence | `$NOTES_DIR/posts/x/` contains posts across four distinct ISO weeks before June 24 | By M1 (June 24) |
| K6 | Input-only measurement | No engagement-metric code in repository. No follower-count tracking. Reaction annotations are qualitative operator notes, not scraped numbers. | Continuous |
| K7 | Drafting guide informs quality | At least one operator iteration cycle (`rewrite hook` / `make concrete`) on the first real draft confirms the guide is being applied | First real post |

K1 + K2 + K3 = Wednesday end of day hard ship.
K4 is gated only by the operator pasting into an X scheduler.
K5 + K6 + K7 are runway items.

---

## 10. Open risks

1. **Drafting quality (top risk).** Without the X application programming interface in the picture, the biggest variable is whether the LLM-drafted posts are good enough to publish. Mitigations: (a) the researched drafting guide grounds quality; (b) interactive review loop is mandatory; (c) operator can always edit the body before pasting.
2. **Operator does not annotate reactions.** Informational only — not a v0 blocker. If frontmatter is never updated, Stage 2's reaction recap prints "no annotations yet" and continues. Stage 7 handoff still nudges the operator. The proper fix is the v0.2 automated reaction-reading feature, not a v0 hard requirement on manual annotation.
3. **First run has empty narrative thread.** First invocation has no past 7 days. Skill handles gracefully: "Narrative thread: empty — this will be your first post under this system." No-op for that stage.
4. **Today's session not yet wrapped up.** If operator invokes `/session-publisher` before `/wrap-up`, today's SESSION file does not exist. Skill detects, prompts: "Today's session wrap-up not found. Run `/wrap-up` first, or proceed without today's input."
5. **Drafting-guide research takes longer than budget.** Mitigation: hard time-box; ship v0 with whatever guide is ready by deadline, extend it later if friction surfaces.

Full Tigers / Paper Tigers / Elephants follow in section 11 after `/pre-mortem` runs.

---

## 11. Pre-Mortem Findings

**Failure frame:** "It is Thursday May 14 and `session-publisher` did NOT ship by Wednesday end of day."
**Run date:** 2026-05-11

---

### Tigers — Real problems that could derail the ship

**T1 — SESSION_INDEX has no conventional header row (Launch-Blocking)**

The SPEC assumes select.py can parse SESSION_INDEX.md as a standard markdown table. The real file has none. The `## Sessions` section starts rows directly as `| 2026-05-11 | title | type | outcome | insight | ledger | asana | tags |` — 8 positional columns, no header, no column names. The "Summary" stats block above it also uses pipe-tables with completely different structure. A naive CSV or pandas parser will either silently mis-read all rows or fail on the mixed table content. This is the single highest-probability build-day timesink.

*Classification: Launch-Blocking*
*Mitigation: Before writing a single line of select.py on Tuesday morning, read the real SESSION_INDEX.md schema (done — confirmed above). Parser must: (1) locate `## Sessions` heading, (2) match lines starting with `| YYYY-MM-DD |` pattern, (3) split on `|` and strip whitespace, (4) extract columns by position [1]=date, [2]=title, [8]=tags. No header parsing. ~15 extra lines but no rabbit hole.*

---

**T2 — $NOTES_DIR path with special characters silently breaks subprocess calls (Launch-Blocking)**

The author's $NOTES_DIR sits under a cloud-sync root whose path contains spaces, parentheses, and an `@` sign. `pathlib.Path` handles such paths safely in pure Python. Any shell call (subprocess, os.system, shlex, or SKILL.md bash instructions that reference the path unquoted) will silently fail or produce cryptic errors. The helpers make 6-8 path operations total across the three files; one unquoted shell call is enough to break the whole pipeline.

*Classification: Launch-Blocking*
*Mitigation: Resolve the path via `NOTES_BASE = Path(os.environ.get("SESSION_PUBLISHER_NOTES_DIR", str(Path.home() / "personal-notes")))` as a single constant at the top of each helper. Use `pathlib` exclusively — no string concatenation, no shell expansion. First test on Tuesday morning: `python -c "import os; from pathlib import Path; p = Path(os.environ['SESSION_PUBLISHER_NOTES_DIR']); print(list(p.iterdir())[:3])"` — if this fails, fix before writing any helper logic.*

---

**T3 — SKILL.md frontmatter must exactly match Claude Code's convention (Launch-Blocking)**

K2 (skill discoverable) fails silently if SKILL.md's YAML frontmatter is wrong. Inspecting two live skills (`wrap-up`, `capture`) confirms the exact required format:

```yaml
---
name: session-publisher
version: "0.1.0"
description: [one sentence — Claude Code uses this for auto-matching trigger phrases]
---
```

The description field is the matching surface. Too vague and the skill never auto-fires; too narrow and it misses the right moments. The SPEC does not yet specify the description text.

*Classification: Launch-Blocking*
*Mitigation: Lock description text now, before Tuesday. Proposed: "Turn today's session wrap-up into a reviewed draft post for X. Reads narrative thread, recommends a topic grounded in today's work, drafts using best-practice guide, iterates interactively, saves to $NOTES_DIR. Use when operator says /session-publisher or 'draft a post' at the end of evening routine."*

---

**T4 — 4-hour Tuesday window has no debugging buffer (Launch-Blocking)**

The build list for Tuesday is: thread.py + select.py + save.py + SKILL.md + README rewrite + symlink + smoke test each helper + end-to-end dry run. That is 8 distinct items at ~30 min each = 4 hours with zero debugging time. A single hour-long debugging session (path issue, parsing edge case, symlink mis-loading) shifts the end-to-end dry run to Wednesday, compressing the ship window.

*Classification: Launch-Blocking*
*Mitigation: Strict build order and stub-first strategy. Tuesday order: (1) $NOTES_DIR path smoke test — 5 min; (2) select.py + test against real SESSION_INDEX — 45 min; (3) save.py + test against real $NOTES_DIR path — 30 min; (4) thread.py — 30 min; (5) SKILL.md — 45 min; (6) symlink + K2 test — 15 min; (7) end-to-end dry run — 30 min; (8) README — 20 min. Total: ~3.5 hours with slim buffer. If step 2 or 3 bleeds past budget, stub the remaining helper (print instead of execute) and complete it Wednesday morning before the ship window.*

---

### Paper Tigers — Overblown concerns, not worth significant investment

**PT1 — "The drafting quality won't be good enough to publish"**
The drafting-guide.md encodes 23 rules and 11 hook templates from three deep research reports. Claude is highly capable at following detailed style guides. The interactive review loop is mandatory — the operator can always iterate before approving. This becomes a real concern only 10-15 posts in, when real reaction patterns emerge. Not a Wednesday blocker.

**PT2 — "Scheduling tool friction blocks the first post"**
Even in the worst case — whichever X scheduler the operator tries is awkward, expires, or requires onboarding — the operator can post directly from x.com. The scheduler is a convenience layer, not a hard dependency.

**PT3 — "The repo must be pristine before going public"**
The repo ships skill source: three ~40-line Python helpers, one SKILL.md, one drafting-guide.md, README, LICENSE. None of this is embarrassing to ship Wednesday. Build-in-public doctrine actively prefers shipping the messy-middle version over waiting for polish.

**PT4 — "focus.yaml filter might return an empty session set"**
If the filter matches nothing, select.py falls back to the last 7 days unfiltered. The skill handles the empty case gracefully with a notification. Not a blocker.

---

### Elephants — Unspoken concerns that deserve a pre-Tuesday check

**E1 — $NOTES_DIR/posts/x/ directory may not be creatable under a cloud-sync root**

The `$NOTES_DIR/posts/x/` directory needs to be created on Tuesday (or by save.py on first run). The author's $NOTES_DIR lives inside a cloud-sync root (Google Drive Mirror). If sync is paused, rate-limited, or in conflict state on Tuesday morning, `Path.mkdir(parents=True)` silently "succeeds" locally but never syncs — producing a local directory that disappears on next sync refresh. This has not been tested.

*Investigation: Today (Monday), manually run `mkdir -p "$SESSION_PUBLISHER_NOTES_DIR/posts/x"` and confirm it appears in the synced view within 2 minutes. If it does, ship save.py with `Path.mkdir(parents=True, exist_ok=True)` and the problem is solved. If it doesn't, save posts to a non-synced local directory instead (one-line change to SPEC) and migrate later.*

**E2 — Running_Week file for current week may not exist when skill first fires**

Stage 3 reads `Running_Week_YYYY-WNN.md` to extract Groundhog + Double Down reflections. W20 starts Monday May 12. If no evening routine runs before the first `/session-publisher` invocation, `Running_Week_2026-W20.md` doesn't exist. The skill will error or silently skip if the file-not-found case isn't handled.

*Investigation: Add explicit file-not-found handling in SKILL.md Stage 3 instructions: "If Running_Week file not found or this week's section not present, skip the Groundhog/Double Down context and proceed to topic recommendation based on session content alone."*

**E3 — SESSION_INDEX.md is append-only and actively being updated today**

> 400 rows as of this morning; 8 new sessions added today alone. By Tuesday the file will be larger. The parser must handle concurrent appends (rows added mid-parse) gracefully. In practice, Python reads the entire file into memory first, so this is not a real concurrency issue — but it is worth confirming that the file read happens atomically (single `Path.read_text()` call, not line-by-line streaming) to avoid edge cases.

*Investigation: Confirm select.py uses `Path(SESSION_INDEX).read_text()` then parses in memory — not `open().readline()` streaming. One-line architectural choice that eliminates the concern.*

---

### Action Plans for Launch-Blocking Tigers

| Tiger | Action | Owner | By when |
|---|---|---|---|
| T1 — SESSION_INDEX no header | Lock parser spec now: positional 8-column, match `\| \d{4}-\d{2}-\d{2} \|`, skip non-session rows. Test against real file as very first Tuesday task. | Build session (Tue 09:00) | Tue 09:15 smoke test pass |
| T2 — $NOTES_DIR path | Lock path constant in all helpers: `NOTES_BASE = Path("~/personal-notes")`. Run path smoke test before writing any helper logic. | Build session (Tue 09:00) | Tue 09:05 smoke test pass |
| T3 — Build window too tight | Follow strict build order. If behind at SKILL.md step, stub helpers (print-only) and complete Wednesday. K2 (symlink + frontmatter) is the minimum viable Wed ship; K3 (end-to-end) can move to Wed morning if Tuesday bleeds. | Operator + build session | Tue 13:00 checkpoint |
| T4 — SKILL.md frontmatter | Lock description text before Tuesday. Proposed text locked in Tiger description above. Copy frontmatter structure from `~/.claude/skills/wrap-up/SKILL.md` exactly. | Lock today (Mon) | Before Tue 09:00 |

---

### Elephant Pre-Actions (complete today, Monday)

| Elephant | Pre-action |
|---|---|
| E1 — Drive directory | `mkdir -p "~/personal-notes/posts/x"` — verify in Drive within 2 min. If it fails, change storage target to `~/tools/session-publisher/posts/x/`. |
| E2 — Running_Week missing | Add file-not-found graceful skip to SKILL.md Stage 3 spec before Tuesday build. |
| E3 — SESSION_INDEX concurrent appends | Confirm select.py design uses single `Path.read_text()` call. |

---

*SPEC v0.3 authored Monday May 11, 2026, by Claude (Opus 4.7) at operator's direction. Pre-mortem complete; awaiting operator sign-off before any code is written. Predecessor: `PRD_cron-architecture-superseded-2026-05-11.md`. Prior revisions of this SPEC (v0.1 = skill with X application programming interface posting; v0.2 = manual-paste gateway with mandatory reaction recap) replaced in place; preserved in git history.*
