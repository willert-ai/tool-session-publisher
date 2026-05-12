# Pre-Mortem — session-publisher

**Failure frame:** "It is Thursday May 14 and session-publisher did NOT ship by Wednesday end of day."
**Run date:** 2026-05-11
**SPEC version:** v0.3

*Full findings also appended as §11 of `SPEC.md`. This file is the standalone reference.*

---

## Tigers — Real problems

### T1 — SESSION_INDEX has no header row (Launch-Blocking)
Real schema confirmed: the `## Sessions` section starts rows directly as `| YYYY-MM-DD | title | type | outcome | insight | ledger | asana | tags |` — 8 positional columns, no header. Mixed with a Stats table above it. Naive parser breaks.

**Action:** Lock positional parser now. Tuesday first task: match lines `\| \d{4}-\d{2}-\d{2} \|`, extract [1]=date [2]=title [8]=tags. Target: smoke test pass by Tue 09:15.

### T2 — Notes-dir path with special chars silently breaks subprocess calls (Launch-Blocking)
The operator's notes directory may contain spaces, parens, and `@` signs. Shell expansion fails silently.

**Action:** `NOTES_BASE = Path(os.environ.get("SESSION_PUBLISHER_NOTES_DIR", ...))` constant in every helper. Pure pathlib, no shell calls. Path smoke test is Tuesday's very first action.

### T3 — 4-hour Tuesday build window has no buffer (Launch-Blocking)
8 items × ~30 min = 4 hours with zero debugging slack. One stuck session = end-to-end dry run moves to Wednesday.

**Action:** Strict build order (T1/T2 first, stub-first strategy). If behind at SKILL.md, stub helpers and complete Wednesday. K2 (symlink + discoverable) is the minimum viable Wed ship.

### T4 — SKILL.md frontmatter must match Claude Code convention exactly (Launch-Blocking)
Confirmed format from live skills (`wrap-up`, `capture`):
```yaml
---
name: session-publisher
version: "0.1.0"
description: [one sentence, used for trigger matching]
---
```
Wrong format = K2 silently fails.

**Locked description text:**
> "Turn today's session wrap-up into a reviewed draft post for X. Reads narrative thread, recommends a topic grounded in today's work, drafts using best-practice guide, iterates interactively, saves to the configured notes directory. Use when operator says /session-publisher or 'draft a post' at the end of evening routine."

**Action:** Copy frontmatter from `~/.claude/skills/wrap-up/SKILL.md` before writing anything.

---

## Paper Tigers — Overblown, not worth investment

**PT1 — Drafting quality** — 23-rule drafting guide + interactive review loop. Not a Wed blocker.
**PT2 — Scheduling tool friction** — Whichever X scheduler the operator picks, x.com is always a viable fallback. The scheduler is a convenience layer, not a hard dependency.
**PT3 — Repo must be pristine** — Build-in-public doctrine: ship the messy-middle. Nothing in the repo is embarrassing.
**PT4 — focus.yaml returns empty set** — Falls back to unfiltered 7-day sessions. Handled by design.

---

## Elephants — Unspoken, need pre-Tuesday check

**E1 — `$NOTES_DIR/posts/x/` directory creation under a synced filesystem**
The notes directory may be inside a cloud-sync root (e.g. Google Drive Mirror). If sync is paused or in conflict state, `Path.mkdir(parents=True)` may "succeed" locally but never sync. Mitigation: pre-create the directory manually before first run; keep `Path.mkdir(parents=True, exist_ok=True)` in save.py as a no-op safety net.

**E2 — Running_Week file may not exist for current week**
Add explicit file-not-found graceful skip to SKILL.md Stage 3: "If Running_Week file not found, skip Groundhog/Double Down context and proceed based on session content alone."

**E3 — SESSION_INDEX concurrent appends**
Confirm select.py uses single `Path.read_text()` call (not streaming). One-line design choice; eliminates the concern.

---

## Action summary

| # | Action | When |
|---|---|---|
| T1 | Lock positional parser spec; smoke-test SESSION_INDEX first | Tue 09:00 |
| T2 | Lock NOTES_BASE env-var lookup; path smoke test first | Tue 09:00 |
| T3 | Follow build order; stub-first if behind schedule | Tue ongoing |
| T4 | Lock description text (done above); copy frontmatter from wrap-up skill | Before Tue |
| E1 | Pre-create notes/posts/x/ dir manually before first run | Mon |
| E2 | Add file-not-found skip to SPEC Stage 3 before Tuesday | Mon (today) |
| E3 | Confirm Path.read_text() in select.py design | Tue 09:00 |
