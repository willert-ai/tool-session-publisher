# Examples corpus — template

This file documents the schema for the **operator's private examples corpus** used by the session-publisher skill at Stage 5.5 (corpus-mirror check). The actual curated corpus lives in `examples.local.md` (gitignored), which the skill reads if present and falls back gracefully if absent.

## Purpose

Successful posts from a curated set of reference bloggers act as a *mirror held up to the draft* — not a template fed into drafting. After Stage 5 produces a rules-compliant draft, Stage 5.5 surfaces 2–3 corpus entries whose tags best match the draft's inferred shape and asks the operator: "does the draft hit the same feel?"

## Where to put your real entries

Create `skill/prompts/examples.local.md` (gitignored — never committed). Use this template as the schema reference.

## Entry schema

Each entry is a markdown block with a heading, a metadata list, and the post text as a blockquote.

### Required fields

- `handle` — X handle without @ prefix (used as filename-safe identifier)
- `post_url` — full X URL to the post
- `captured_at` — ISO date of when this entry was added
- `approx_likes` — engagement snapshot at capture time (approximate is fine — Grok returns approximate numbers)
- `approx_reposts` — same as above
- `length` — `shortform` (≤280 chars) or `longform` (>280 chars, requires X Premium to author)
- `tone_register` — one of: `clinical-peer`, `reflective-solo`, `provocateur`, `dry-wit`
- `hook_structure` — one of: `hard-number-first`, `failure-exposed`, `contrarian-claim`, `ship-log-direct`, `question-reframe`, `observation-cold`, `meme-callout`
- `sentence_rhythm` — one of: `staccato`, `mid-length-declarative`, `flowing`, `mixed`
- `topic_ownership` — one of: `i-built-this`, `i-learned-this`, `i-disagree-with-this`, `i-show-you-this`, `i-noticed-this`
- `constraint_disclosure` — one of: `limitation-upfront`, `limitation-embedded`, `limitation-absent`, `uncertainty-stated`
- `topic_area` — one of: `ai-tooling`, `ai-research`, `agentic-engineering`, `indie-business`, `daily-life`, `meta-industry`, `model-release-tracking`, `other`
- `personality_fit_note` — short qualitative note. Prefix `claude-initial-read:` for unreviewed entries, `operator:` once you've refined.

### Optional fields

- `media_attached` — `image`, `video`, or omit if text-only

## Single worked example

### example-001

- handle: example_handle
- post_url: https://x.com/example_handle/status/1234567890
- captured_at: 2026-05-15
- approx_likes: 1500
- approx_reposts: 80
- length: shortform
- tone_register: clinical-peer
- hook_structure: hard-number-first
- sentence_rhythm: mid-length-declarative
- topic_ownership: i-built-this
- constraint_disclosure: limitation-embedded
- topic_area: ai-tooling
- personality_fit_note: "claude-initial-read: tight technical observation with embedded caveat — strong template for shipping-update voice"

> I rebuilt the indexer to use mmap instead of full-buffer reads. Cuts cold-start time from 4.2s to 0.6s on the 200MB corpus. Still tuning the read-ahead window — current default underutilizes the SSD on large skips.

---

## How Stage 5.5 uses this corpus

When you produce a draft, Claude infers the draft's tags using the same five axes. Stage 5.5 then scans the corpus for entries with overlapping tags (especially `tone_register`, `hook_structure`, `sentence_rhythm`) and surfaces the top 2–3. You're shown each match with its tags so you can judge fit by *feel*, not by score.

Matching is pure string overlap — no embeddings, no external calls, stdlib only.

## Curation cadence

Build the corpus once during a dedicated curation session. Revisit quarterly or when you notice your output drifting from the voice you actually want. The corpus is operator-private and reflects your specific personality — don't share it.
