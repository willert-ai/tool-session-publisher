# Examples corpus — template

This file documents the schema for the **operator's private examples corpus** used by the session-publisher skill at Stage 5.5 (corpus-mirror check). The actual curated corpus lives in `examples.local.md` (gitignored), which the skill reads if present and falls back gracefully if absent.

## Purpose

Successful posts from a curated set of reference bloggers encode register —
voice, hook shape, sentence rhythm — that escapes the 24 rules of
`drafting-guide.md`. After Stage 5 produces a rules-compliant draft,
Stage 5.5 reads the corpus internally, picks up to 2 entries that match the
draft's inferred shape, and produces **style-applied rewrites** of the
operator's draft in their register. The operator sees only their own
content rewritten — never the corpus entries themselves.

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
- `hook_structure` — one of: `hard-number-first`, `failure-exposed`, `contrarian-claim`, `ship-log-direct`, `question-reframe`, `observation-cold`, `meme-callout`, `confession`, `expectation-reversal`
- `sentence_rhythm` — one of: `staccato`, `mid-length-declarative`, `flowing`, `mixed`
- `topic_ownership` — one of: `i-built-this`, `i-learned-this`, `i-disagree-with-this`, `i-show-you-this`, `i-noticed-this`
- `constraint_disclosure` — one of: `limitation-upfront`, `limitation-embedded`, `limitation-absent`, `uncertainty-stated`
- `topic_area` — one of: `ai-tooling`, `ai-research`, `agentic-engineering`, `indie-business`, `daily-life`, `meta-industry`, `model-release-tracking`, `other`
- `guide_compliance` — integer `1`–`5`. `1` = violates `drafting-guide.md`, `5` = textbook-compliant. Dual-layer aware: if `topic_area` ∈ `{ai-tooling, ai-research, agentic-engineering, model-release-tracking}`, score against Layer 1 + Layer 2; otherwise Layer 1 only. Populated at curation time. Stage 5.5 uses this as a final tiebreaker — never as primary ranking.
- `guide_compliance_notes` — one-line string. Which rule(s) the entry hits or misses. Quote-wrap (`"…"`) tolerated.
- `personality_fit_note` — short qualitative note. Prefix `claude-initial-read:` for unreviewed entries, `operator:` once you've refined.

`confession` and `expectation-reversal` correspond to `drafting-guide.md` hook templates
11–12. They were added in v2.0 because two shapes that recur in real posts had no value to
tag them with: a flat first-person admission (distinct from `failure-exposed`, which pairs
the failure with a fix) and a confident opening undercut by the next line (distinct from
`hard-number-first`, which describes only how the first line opens).

### Optional fields

- `media_attached` — `image`, `video`, or omit if text-only
- `near_duplicate_of` — entry id (e.g., `simonw-003`). Set on non-representative members of a near-duplicate cluster (same handle + same tone + same hook + same rhythm). One representative per cluster leaves this field unset; the rest point at it. `mirror.py` drops every entry where this field is set, so only cluster representatives reach Stage 5.5.

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

After Stage 5 approval, the skill calls `helpers/mirror.py` to load all
eligible entries (cluster representatives only — `near_duplicate_of` entries
are pre-filtered). Claude then infers the draft's seven tags and selects up
to 2 entries as register exemplars, prioritising `tone_register` and
`hook_structure`. For each selected exemplar, Claude produces a
**style-applied rewrite** of the operator's own draft. You never see the
corpus entries themselves — only rewrites of your own content in their
register. You pick: original, A, B, iterate, or skip.

The 24 rules in `drafting-guide.md` are the floor for every rewrite. When
exemplar register conflicts with a rule, the rule wins.

`helpers/mirror.py` is pure stdlib. Semantic selection happens inside the
running Claude session — no separate API call, no embeddings.

## Curation cadence

Build the corpus once during a dedicated curation session. Revisit quarterly or when you notice your output drifting from the voice you actually want. The corpus is operator-private and reflects your specific personality — don't share it.
