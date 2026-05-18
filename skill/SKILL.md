---
name: session-publisher
version: "0.1.0"
description: This skill should be used when the user says "/session-publisher", asks to "draft a post", "publish today's session", "turn this session into a post", or "post about today" — typically at the end of an evening routine after /wrap-up. Runs a seven-stage interactive conversation that reads the past-7-days narrative thread, recommends a topic grounded in today's session work, drafts with a researched best-practice guide, iterates until operator approval, and saves the result to $NOTES_DIR/posts/x/. Does NOT publish directly — operator pastes the approved draft into your X scheduler.
---

# Session Publisher

Turn today's Claude Code session wrap-up into a reviewed draft post for X
through a seven-stage interactive conversation. The skill never publishes
directly; the operator pastes the approved draft into your X scheduler.

---

## Trigger Phrases

- `/session-publisher`
- "draft a post"
- "publish today's session"
- "turn this session into a post"
- "post about today"

---

## Pre-conditions

This skill was built around a specific session-archive infrastructure
the author maintains. To use it as-is, you need:

1. **Daily session files.** Markdown files in `$NOTES_DIR/` named
   `YYYY-MM-DD - SESSION_<title>.md` (one per Claude Code session you
   want eligible for posting). The author generates these via a
   companion `wrap-up` skill, but you can produce them by any means —
   manual notes, journal exports, a CLI script. Today's session must
   exist for the skill to ground the draft in today's work.

2. **A SESSION_INDEX.md ledger.** A single file at
   `$NOTES_DIR/SESSION_INDEX.md` containing an append-only `## Sessions`
   section with pipe-delimited rows of the form:

   ```
   | YYYY-MM-DD | <title> | <type> | <outcome> | <insight> | <ledger> | <asana> | <tags> |
   ```

   Eight positional columns, **no header row**. `select.py` parses lines
   matching `^\| \d{4}-\d{2}-\d{2} \|` and extracts position 1 (date),
   position 2 (title), and position 8 (tags). The other columns can be
   empty for purposes of this skill.

3. **A `$NOTES_DIR/posts/x/` directory.** The first invocation creates
   it automatically; `save.py` calls `Path.mkdir(parents=True, exist_ok=True)`
   as a safety net.

### What if I don't have any of this?

Two paths:

- **Build an equivalent.** A 50-line wrap-up script can produce both
  the SESSION files and append a row to SESSION_INDEX.md at the end of
  each Claude Code session you want to post about. The schema above is
  the contract.

- **Fork and replace Stage 1.** Strip the `select.py` call out of
  SKILL.md and replace it with "paste today's session content here."
  The remaining six stages (narrative-thread recap from `posts/x/`,
  topic recommendation, drafting, review, save, handoff) work without
  any session-index dependency.

### Pre-flight check

If today's row is missing from SESSION_INDEX, the skill warns the
operator and offers to proceed on past-7-days context alone — so a
single missing day is not a hard error.

---

## Workflow — seven stages

Invoke the three Python helpers via the `Bash` tool, using absolute paths
through the installed skill location (so the working directory does not
matter):

```bash
SKILL_DIR=~/.claude/skills/session-publisher
```

Each helper emits JSON to stdout — parse the JSON, do not screen-scrape
prose.

### Stage 1 — Context primer

1. Run `python3 ~/.claude/skills/session-publisher/helpers/thread.py --days 7`.
   Parse the JSON output to get past-7-days posts plus reaction recap.
2. Run `python3 ~/.claude/skills/session-publisher/helpers/select.py --days 7`.
   Parse the JSON output to get candidate sessions from `SESSION_INDEX.md`,
   anti-duplicate filtered, optionally focus-filtered.
3. Identify today's session by date inside the `candidates` list.
4. If today's row is missing, tell the operator:
   > Today's session wrap-up not found in SESSION_INDEX. Run `/wrap-up`
   > first, or say "proceed" to draft from the last 7 days only.

### Stage 2 — Narrative-thread recap (+ reaction recap if annotated)

Render to the operator:

```
Narrative thread — past 7 days

Posts: <posts_count>
- <date> <body_excerpt> — <status>
- ...
```

If `reactions_annotated` is `true` in the `thread.py` output, additionally
render the reaction recap with the skill's own qualitative reading of what
hit / missed. If `false`, print one line:

```
Reactions: no annotations yet — automated reaction reading is a v0.2 feature
```

Never fail on missing annotations. Reaction recap is value-add when present.

### Stage 3 — Topic recommendation

Read the body of today's session wrap-up file (look up its full path under
`$NOTES_DIR/` based on the date + title from the SESSION_INDEX row).

**Optional enrichment — recent reflections.** If you keep a recurring
reflections file (weekly review, end-of-day journal, retrospective notes),
read the most recent entry and surface any patterns relevant to topic
selection. This sharpens the recommendation by connecting today's session
to running themes the operator has been tracking.

The author's setup, included here as a concrete example — adapt to your
own:

- File pattern: `Running_Week_YYYY-WNN.md` (one per ISO week)
- Location resolved via `~/.claude/ENVIRONMENT.yaml` → weekly-plan-dir key
- Sections of interest: `Groundhog` (a recurring pattern the operator
  keeps noticing) and `Double Down` (a high-leverage move worth
  amplifying), pulled from last evening's entry

**Best effort — if ANY of these fail, skip the enrichment and proceed
on session content alone. Never error here. (SPEC E2 mitigation.)**

Failure cases that must be silently skipped:
- The reflections file path cannot be resolved (config missing, file
  not yet created for this period, no equivalent infrastructure in
  place)
- The expected sections are absent or empty in this period's entry
- Any IO error reading the file

Forkers without an equivalent reflections file lose nothing — the skill
falls back to recommending purely from today's session content.

Apply `~/.claude/skills/session-publisher/prompts/drafting-guide.md` style
awareness when reasoning about which session insight is most "bookmarkable"
(Rule 15). Recommend ONE topic plus TWO alternative angles:

```
Today's session(s):
- <title 1> — <primary outcome>

Recommended topic for today's post:
> <one-sentence framing>

Rationale: <why this topic fits the thread + grounding from session>
Alternative angles:
  a) <framing>
  b) <framing>

Approve angle, switch to alternative, or propose your own?
```

Wait for the operator's response. Accept: `approve`, `a`/`b`, free-text
alternative.

### Stage 4 — Drafting

Read `~/.claude/skills/session-publisher/prompts/drafting-guide.md` in full.
Apply Layer 2 rules (16–23 + AI anti-patterns) when the approved angle is
about LLM tools, agents, or automation. Otherwise apply Layer 1.

Produce a single tweet **≤ 280 characters**, grounded in concrete session
work (proof of work, at least one number, one idea only, "I" not "we",
no engagement bait, no hashtags by default).

Present the draft inline with the character count.

### Stage 5 — Interactive review

Accepted operator instructions (loop until `approve` or `skip`):

- `looks good` / `approve` → Stage 6
- `rewrite hook` / `rewrite ending` → partial regen
- `make more concrete` / `cut the hedge` / `tighten` → targeted edit
- `regenerate` → fresh draft on the same angle
- `different angle` → back to Stage 3
- `skip` → discard, do not save
- operator pastes their own rewrite → accept verbatim as final

After every edit, re-check the 280-character ceiling and the drafting
guide's rules 1–23. If a rule is broken, fix it before presenting.

### Stage 5.5 — Style-applied variants (conditional)

Runs only when `skill/prompts/examples.local.md` exists, parses, and yields
at least one entry that is an honest register match for the approved draft.
If any precondition fails, **silently skip** Stage 5.5 and proceed to Stage 6
with the original Stage-5-approved draft.

Stage 5.5 exists because rules-compliant drafts can still feel "off" — voice
and constraint-disclosure register escape the 23 rules in `drafting-guide.md`.
The operator's private corpus encodes register that has actually worked in
publication; Stage 5.5 transfers that register onto the operator's content.

#### 5.5.1 — Load the corpus

```bash
python3 ~/.claude/skills/session-publisher/helpers/mirror.py
```

Parse the JSON envelope. Handle each `status` value:

- `"ok"` — proceed to 5.5.2.
- `"skip"` with `reason: "absent"` — corpus not configured (default for
  forkers). Output nothing operator-facing. Proceed to Stage 6.
- `"skip"` with `reason: "empty"` — file exists but yields zero eligible
  entries. Render one line: `Corpus mirror: no entries available — skipping.`
  Proceed to Stage 6.
- `"skip"` with `reason: "io_error"` / `"parse_failed"` — render one line:
  `Corpus mirror: read failed — skipping.` Proceed to Stage 6.

The skill never fails on corpus issues — same posture as reaction recap.

#### 5.5.2 — Infer draft tags, select 0–2 matches semantically

The corpus is private context, not operator-facing content. Read the
`entries` list internally and apply the SPEC §3 axis vocabulary:

1. **Infer the approved draft's 7 tags.** Six axes are model judgment:
   `tone_register`, `hook_structure`, `sentence_rhythm`, `topic_ownership`,
   `constraint_disclosure`, `topic_area`. The seventh — `length` — is
   deterministic: `shortform` if `len(body) ≤ 280` else `longform`.
2. **Vocabulary** is fixed in `prompts/examples-template.md`. Hook
   structures map 1:1 to `drafting-guide.md` Layer-2 hook templates 6–11
   when the topic_area is `ai-tooling` / `ai-research` /
   `agentic-engineering` / `model-release-tracking`; otherwise Layer-1
   templates 1–5.
3. **Select up to 2 matches** by honest register fit. Prioritize
   `tone_register` and `hook_structure` (the load-bearing register axes),
   then `sentence_rhythm`, `topic_ownership`, `constraint_disclosure`.
   Use `length` and `topic_area` as tiebreakers. Use `guide_compliance`
   (1–5) as a final tiebreaker — higher = better — but never as primary
   ranking; a poor register fit with compliance 5 still loses to a strong
   register fit with compliance 3.
4. **Honesty floor.** If no eligible entry is a real register fit, select
   zero matches and silently skip Stage 5.5. Do not force two when one
   (or none) is honest. Acceptable to return one match — the prompt
   collapses gracefully (see 5.5.4).

The corpus entry itself is never rendered to the operator. Only
style-applied rewrites of the operator's own draft are shown.

#### 5.5.3 — Produce style-applied rewrites

For each selected match, produce a **style-applied rewrite** of the
approved draft. Preserve:

- The core idea and angle (from Stage 3).
- All concrete numbers, named technologies, and constraint disclosures
  from the original draft.
- The 280-character ceiling if the original was `shortform`.
- All 23 rules from `drafting-guide.md`. If exemplar register conflicts
  with a rule, **the rule wins.**

Adjust toward the exemplar:

- Hook structure (move number forward, swap question-reframe for
  observation-cold, etc.).
- Sentence rhythm (staccato vs. mid-length-declarative vs. flowing).
- Tone register (clinical-peer vs. dry-wit vs. reflective-solo vs.
  provocateur).

If a rewrite cannot honor both the exemplar register and the 280-char
ceiling, discard that variant. If both variants get discarded, treat as
"zero clear matches" — skip Stage 5.5 silently.

#### 5.5.4 — Operator-facing prompt

Render exactly:

```
Stage 5.5 — Style-applied variants

Your approved draft:
> <original body>

Variant A — style of @<handle> (<tone_register>/<hook_structure>/<sentence_rhythm>):
> <rewrite A>

Variant B — style of @<handle> (<tone_register>/<hook_structure>/<sentence_rhythm>):
> <rewrite B>

original  — keep your draft as approved
A         — use variant A
B         — use variant B
iterate   — refine one of these further (specify which + instruction)
skip      — drop variants, keep original
```

When only one entry was selected, omit Variant B and collapse the choice
to `original / A / iterate / skip`.

#### 5.5.5 — Handle the operator response

| Response | Behavior |
|---|---|
| `original` / `skip` | Discard variants. Stage 6 receives the original Stage-5-approved draft. |
| `A` / `B` | Replace the draft body with the selected variant. Proceed to Stage 6. |
| `iterate <A\|B> <instruction>` | Re-enter Stage 5 with the chosen variant as the new starting draft. After re-approval at Stage 5, Stage 5.5 runs again on the new draft. |

The variant attribution (which `@handle` was the exemplar) is **not**
stored in the saved post file — the post stands on its own; the corpus
is a private aid to drafting.

### Stage 6 — Save to notes directory

Call:

```bash
python3 ~/.claude/skills/session-publisher/helpers/save.py "<session_source>" --body "<approved post body>"
```

`<session_source>` is the canonical SESSION_INDEX row key — format
**`YYYY-MM-DD - <title>`**. No `.md` suffix. No `SESSION_` prefix.

Use the exact `session_source` value already emitted by `select.py` for
today's candidate. select.py and save.py share this format contract;
breaking it silently breaks anti-duplicate (SPEC §6.h).

For multi-line bodies, prefer `--body-file <path>` or `--body-stdin`.

The helper writes
`$NOTES_DIR/posts/x/YYYY-MM-DD_post-NNN.md` with frontmatter:

```
---
created_at: <ISO8601 with offset>
session_source: <key>
status: drafted
x_url:
reactions:
  -
notes:
---

<body>
```

Anti-duplicate is guaranteed by the next-free `post-NNN` numbering.

### Stage 7 — Handoff

Render:

```
✅ Saved to $NOTES_DIR/posts/x/YYYY-MM-DD_post-NNN.md

Paste this into your X scheduler → schedule / publish:

<post body>

After your X scheduler publishes:
- update status: posted
- paste the URL into x_url:
- **within 1 hour**: return to the post and author-reply to the first 2–3 substantive replies (single highest-leverage post-publish action per drafting-guide "Post-publish protocol" section)
- note `author_replied: yes/no` in reaction observations
- append reaction observations under reactions: over the next few days
```

End of skill invocation.

---

## Anti-checks (run before completing)

- Body ≤ 280 chars
- One idea only
- No engagement bait, no hashtags (unless intentionally one)
- File written to `$NOTES_DIR/posts/x/`, NOT to the repo
- Operator approved at Stage 5 (no auto-save without `approve`)

---

## Notes

- Drafting LLM is the running Claude. There is no separate Anthropic API
  call and no `.env`. The drafting guide is applied in-session.
- The repository carries the skill source only. Personal post content
  lives in the configured notes directory.
- v0.2 — Out of scope, do not implement: X application programming
  interface read-path (automated reaction fetching), threads, images,
  multi-platform, mobile review, engagement metrics, auto-trigger from
  `daily-routine`.

---

## Additional Resources

### References (loaded on demand)

Bundled documentation read by the running Claude when needed:

- **`prompts/drafting-guide.md`** — 24-rule X-drafting best-practice guide
  (Layer 1 = general builder norms, rules 1–16 + hook templates 1–5;
  Layer 2 = AI/agentic overrides, rules 17–24 + hook templates 6–10 +
  AI anti-patterns; plus "Post-publish protocol" section covering
  author-reply within 1h and posting-window timing). **Read in full at
  Stage 4 before drafting.** Layer 2 takes precedence when the approved
  angle concerns LLM tools, agents, or automation infrastructure.

### Scripts (executable helpers)

Pure-Python stdlib helpers — no installed packages required. Invoke via
the `Bash` tool. Each emits JSON on stdout.

- **`helpers/thread.py`** — Stage 1. Reads past-N-days posts from
  `$NOTES_DIR/posts/x/`, parses frontmatter, returns narrative-thread +
  reaction recap.
- **`helpers/select.py`** — Stage 1. Reads `$NOTES_DIR/SESSION_INDEX.md` (notes dir resolved from `$SESSION_PUBLISHER_NOTES_DIR` env var, default `~/personal-notes`),
  returns candidate sessions (past-N-days, focus-filtered if
  `focus.yaml` exists at repo root, anti-duplicate against existing
  posts).
- **`helpers/save.py`** — Stage 6. Writes the approved draft as
  `$NOTES_DIR/posts/x/YYYY-MM-DD_post-NNN.md` with frontmatter. Enforces
  the 280-character ceiling.
- **`helpers/mirror.py`** — Stage 5.5 (conditional). Parses
  `prompts/examples.local.md` (operator-private, gitignored), drops
  `near_duplicate_of` cluster non-representatives, returns eligible
  entries as JSON. Semantic match/select happens inside Stage 5.5 prose
  — the helper is a loader, not a scorer. Schema reference:
  `prompts/examples-template.md`.

### Folder-naming convention

This skill uses `helpers/` (not `scripts/`) and `prompts/` (not
`references/`). The functional behaviour is identical to the official
guide's structure — Claude Code only requires `SKILL.md` at the skill
root for discovery. The deviation is project-local convention.

---

## References (external)

- SPEC: `planning/SPEC.md`
- Pre-mortem: `planning/PreMortem-session-publisher-2026-05-11.md`
