# session-publisher

Claude Code skill that turns the day's session wrap-up into a reviewed
draft post for X — through a seven-stage interactive conversation, not an
automated pipeline. Drafts are saved to a configurable notes directory;
the operator pastes into your X scheduler of choice (or x.com directly) to publish. No X
application programming interface in v0.

This repository is the build-in-public artifact for the skill itself.
Personal post content lives outside this repository.

---

## Why this exists

Most "post-to-X" tools assume the operator already knows what to post.
This one starts a step earlier: today's actual session wrap-up is the
input. The skill reconstructs the last seven days of narrative thread,
recommends a topic grounded in today's shipped work, drafts using a
researched best-practice guide, iterates with the operator until
approval, and saves the result. Then the operator pastes it into their
publishing tool of choice.

Built to support a substantive build-in-public X cadence under the
operator's own name, with the skill source as the first public GitHub
repository in the author's portfolio.

---

## Installation

```bash
git clone https://github.com/willert-ai/tool-session-publisher.git \
    ~/tools/session-publisher
ln -s ~/tools/session-publisher/skill ~/.claude/skills/session-publisher
export SESSION_PUBLISHER_NOTES_DIR="/absolute/path/to/your/notes"
```

Add the `export` line to your shell profile (`~/.zshrc` or `~/.bashrc`)
so it persists. If you omit it, the helpers default to `~/personal-notes`.

Claude Code auto-loads `SKILL.md` on next session start. Verify with:

```bash
ls -la ~/.claude/skills/session-publisher
```

The symlink must resolve to the project's `skill/` directory.

---

## Requirements

- macOS or Linux with Python 3.11+
- Claude Code installed
- A notes directory you can write to. Set the path via the
  `SESSION_PUBLISHER_NOTES_DIR` environment variable (defaults to
  `~/personal-notes`). It will receive `posts/x/YYYY-MM-DD_post-NNN.md`
  drafts.
- A `SESSION_INDEX.md` ledger inside that notes directory, plus daily
  `YYYY-MM-DD - SESSION_<title>.md` session files. The skill was built
  around the author's session-archive infrastructure — see
  [`skill/SKILL.md`](skill/SKILL.md) pre-conditions for the exact schema
  and two paths to adapt the skill if you don't already keep an
  equivalent index.
- Any X scheduling tool (or x.com directly) for the publish step

No `.env`, no API keys, no installed packages — the helpers are pure
Python stdlib + pathlib.

---

## Usage

Invoke at the end of an evening session (typical pattern: right after
`/wrap-up`):

```
/session-publisher
```

The skill runs through seven stages:

1. **Context primer** — pulls past 7 days of posts + candidate sessions
2. **Narrative-thread recap** — shows the running thread + reaction recap
3. **Topic recommendation** — proposes one topic + two alternatives
4. **Drafting** — produces a single post of 400–650 chars in three or four short paragraphs
5. **Interactive review** — operator iterates (`rewrite hook`, `tighten`, etc.)
6. **Save** — writes `$NOTES_DIR/posts/x/YYYY-MM-DD_post-NNN.md`
7. **Handoff** — prints the body for paste into your X scheduler

Optional: place a `focus.yaml` at the repo root to filter candidate
sessions by project name:

```yaml
- my-side-project
- tool-mycli
- weekly-newsletter
```

---

## Architecture

A single Claude Code skill + a handful of stdlib-only Python helpers + one
researched drafting guide. There are no GitHub Actions, no server, no database,
no separate API key, no `.env` — the only scheduled piece is a local launchd
user agent (see below). In the interactive path the "drafting LLM" is the
running Claude, applying a 24-rule drafting guide in-session; in the ambient
path it is the same guide handed to a headless `claude -p` call with no session
open.

```
session-publisher/
├── skill/
│   ├── SKILL.md                    # the skill itself
│   ├── helpers/
│   │   ├── select.py               # candidate sessions from SESSION_INDEX
│   │   ├── thread.py               # narrative thread from posts/x/
│   │   ├── save.py                 # write approved draft to $NOTES_DIR
│   │   ├── mirror.py               # load the private register corpus
│   │   ├── queue.py                # the ambient queue contract + review loop
│   │   ├── mine.py                 # SESSION_INDEX + git logs → scored seeds
│   │   └── draft.py                # seeds → finished bodies, headless
│   ├── engine/
│   │   ├── run.sh                  # one ambient tick, driven by launchd
│   │   └── *.md                    # the assembled headless drafting prompt
│   └── prompts/
│       └── drafting-guide.md       # researched X-posting best practice
└── planning/                       # SPEC + pre-mortem
```

---

## Ambient mode (optional)

The skill also runs unattended. A scheduled `skill/engine/run.sh` expires the
queue, mines the last few days of sessions for seeds, drafts finished bodies
through a headless `claude -p` call, and files them in
`$SESSION_PUBLISHER_NOTES_DIR/posts/x/queue/`. You then review the queue with
`python3 skill/helpers/queue.py review` and paste what you approve into X.

Try one tick by hand first — nothing is scheduled until you schedule it:

```bash
export SESSION_PUBLISHER_NOTES_DIR="/absolute/path/to/your/notes"
export SESSION_PUBLISHER_TZ="Europe/Berlin"
skill/engine/run.sh --mode ambient
python3 skill/helpers/queue.py list
```

`run.sh` requires both variables and refuses to run without them, because a
scheduler inherits nothing from your login shell and the failure would
otherwise be silent: the queue would appear under `~/personal-notes` with UTC
timestamps. On macOS, wrap it in a launchd user agent with one
`StartCalendarInterval` entry — `run.sh` reads the weekday itself and picks the
daily or the weekly cadence, so a second entry would double-fire. Pass an
absolute `X_COMMS_CLI` (a scheduler's `PATH` will not find `claude`, and
`run.sh` rejects anything that is not an absolute path) and give the agent
absolute `StandardOutPath` / `StandardErrorPath`.

One structured tick line per run lands in `$X_COMMS_LOG_DIR/tick.log` —
`$HOME/Library/Logs/ai.fero.x-comms` unless you set that variable. It carries
counts and reason codes only, never a post body. Read the `status=` field
first: `ok` drafted something, `idle` found nothing fresh to say, `capacity`
declined because the queue is already full, `no_output` drafted nothing that
passed the gates, `locked` backed off because another tick was running,
`interrupted` was killed mid-run, and `failed` could not run at all.

---

## Scope

**In v0:** the seven-stage skill end-to-end, focus filter, narrative
thread, optional reaction recap (operator-annotated frontmatter),
researched drafting guide, save to `$NOTES_DIR`, paste hand-off.

**Out of v0:** X application programming interface (read or write),
threads / images / multi-platform, mobile review, engagement-metric
scraping, auto-trigger from `daily-routine`. See `planning/SPEC.md` §7
for the full list.

---

## Project context

`AGENTS.md` is the cross-tool standard project-context file. `CLAUDE.md`
is a symlink to it. Both auto-load for Claude Code.

Key design documents:

- `planning/SPEC.md`
- `planning/PreMortem-session-publisher-2026-05-11.md`
- `skill/prompts/drafting-guide.md` — 24 rules, 12 hook templates,
  AI/agentic Layer 2 overrides

---

## License

MIT — see [LICENSE](LICENSE).
