# SPEC — corpus-mirror (Stage 5.5 for session-publisher, v0.2)

**Locked decisions:** Phase A (operator + Claude, 2026-05-15) + Phase B mid-flight revisions (2026-05-15)
**Status:** Phase B draft — awaiting operator sign-off before Phase C (SKILL.md modifications + implementation)
**Predecessor:** `SPEC.md` v0.3 (defines the 7-stage skill; this SPEC adds Stage 5.5 between Stage 5 Interactive Review and Stage 6 Save)
**Revision note:** v0.1 of this SPEC framed Stage 5.5 as a *mirror* (show examples, ask operator to compare). Operator overruled mid-Phase-B: Stage 5.5 now produces *style-applied rewrites* of the operator's own draft. Examples are read internally and applied; never shown.

---

## 1. Scope & non-goals

### In scope

A new stage — **Stage 5.5 — Style-applied variants** — running *after* Stage 5 approval and *before* Stage 6 save. The stage reads `skill/prompts/examples.local.md`, infers tags for the approved draft, finds the top 1–2 corpus entries by tag overlap + guide compliance, and produces 1–2 *style-applied rewrites* using those entries as exemplars. The operator picks one (original, A, B, or iterate).

The stage exists because rules-compliant drafts can still feel "off" — voice and constraint-disclosure register escape the 23 rules in `drafting-guide.md`. The corpus encodes register that has actually worked in real publication; Stage 5.5 transfers that register onto the operator's content.

### Non-goals

- **Not a Stage 4 input.** Corpus is read at Stage 5.5 only.
- **No corpus content shown to the operator.** Matched posts are read internally; only style-applied variants of the operator's own draft are rendered.
- **No external calls.** No X API, no embeddings, no separate LLM call. Pure stdlib matching on tags (Phase A decision 8).
- **No corpus-building inside the skill.** Curation is out-of-band (Phase A decision 4).
- **No audit bookkeeping.** Cut entries are deleted from `examples.local.md` directly (Phase A decision 10).

Items already out-of-v0 in `SPEC.md` §7 stay out: X API, automated reaction fetching, multi-platform, mobile review, web UI, engagement metrics.

---

## 2. Inputs

| Input | Source | Required? |
|---|---|---|
| Approved draft body | Stage 5 output (operator-approved text) | Yes |
| Approved-angle context | Stage 3 output (one-sentence framing + rationale) | Yes |
| Examples corpus | `skill/prompts/examples.local.md` (gitignored) | No — fallback below |
| Schema reference | `skill/prompts/examples-template.md` (axis enums + new compliance/dedup fields) | Yes (in repo) |

**Fallback when corpus is absent, empty, or yields no matches:** Stage 5.5 is skipped silently. The skill proceeds directly to Stage 6 with the original Stage-5-approved draft. No operator-facing message when `examples.local.md` does not exist (default state for forkers; Phase A decision 5). When the file exists but has zero parseable entries, render one line: `Corpus mirror: no entries available — skipping.`

---

## 3. Tag inference for drafts

Claude infers seven tags for the approved draft using the vocabulary in `examples-template.md`:

1. `tone_register` — judgment
2. `hook_structure` — judgment (apply the 10 hook templates in `drafting-guide.md` as priors)
3. `sentence_rhythm` — judgment, lightly informed by sentence count + avg length
4. `topic_ownership` — judgment
5. `constraint_disclosure` — judgment, anchored to whether the draft names a limitation, an uncertainty, or neither
6. `length` — **deterministic.** `shortform` if `len(body) ≤ 280` else `longform`
7. `topic_area` — judgment

The five judgment axes are model-evaluated against the draft text — no regex, no keyword tables. Inference runs implicitly; the operator does not see or override the inferred tags (operator-side tag override is out-of-scope per Phase B decision).

---

## 4. Schema extensions and matching

### Schema extensions

Two new fields per entry:

```
- guide_compliance: <1-5>           # 1=violates drafting-guide; 5=textbook compliant
- guide_compliance_notes: "<one line — which rule(s) hit/missed>"
- near_duplicate_of: <id or omit>   # set on non-representatives in a cluster
```

`guide_compliance` is dual-layer aware: if `topic_area ∈ {ai-tooling, ai-research, agentic-engineering, model-release-tracking}`, score Layer 1 + Layer 2; otherwise Layer 1 only. Populated at curation time.

`near_duplicate_of` clusters by same tone + same hook + same rhythm + same blogger. One representative per cluster leaves the field unset; the rest point at it.

### Matching pipeline

1. **Pre-filter.** Drop every entry with `near_duplicate_of` set. Only cluster representatives are eligible.
2. **Score.** For each remaining entry, compute tag-overlap score against the inferred draft tags:

| Axis | Match weight |
|---|---|
| `tone_register` | 3 |
| `hook_structure` | 3 |
| `sentence_rhythm` | 2 |
| `topic_ownership` | 2 |
| `constraint_disclosure` | 2 |
| `length` (tiebreaker) | 0.5 |
| `topic_area` (tiebreaker) | 0.5 |

3. **Apply compliance modifier.** `final_score = tag_overlap + (guide_compliance − 3) × 1.0`. Compliance 5 adds +2; compliance 1 subtracts −2; compliance 3 is neutral. Compliance never replaces register match; it promotes or demotes ties.
4. **Sort and select.** Descending by `final_score`. Break ties by `length`, then `topic_area`, then `approx_likes` (missing `approx_likes` ranks to bottom in ties). Return up to **N = 2**.
5. **Threshold floor.** Drop any entry below tag-overlap score 5 (compliance modifier does not count toward the floor). If zero entries clear the floor, Stage 5.5 is skipped silently and the original draft proceeds to Stage 6.

---

## 5. Style application and operator-facing presentation

For each selected match (up to 2), Claude produces a **style-applied rewrite** of the draft. The rewrite keeps the core idea, concrete numbers, named technologies, and constraint disclosure from the original. It adjusts hook structure, sentence rhythm, and tone register toward the exemplar. It stays within `≤280` chars if the original was shortform. It continues to honor all 23 rules in `drafting-guide.md` — if exemplar register conflicts with a rule, the rule wins.

The corpus entry is read internally and never displayed. Operator-facing block:

```
Stage 5.5 — Style-applied variants

Your approved draft:
> <original body>

Variant A — style of @<handle> (<tone>/<hook>/<rhythm>):
> <rewrite A>

Variant B — style of @<handle> (<tone>/<hook>/<rhythm>):
> <rewrite B>

original  — keep your draft as approved
A         — use variant A
B         — use variant B
iterate   — refine one of these further (specify which + instruction)
skip      — drop variants, keep original
```

When only one entry clears the threshold, Variant B is omitted; the prompt collapses to `original / A / iterate / skip`. When zero clear, Stage 5.5 is skipped silently and Stage 6 receives the original draft.

---

## 6. Operator response handling

| Response | Behavior |
|---|---|
| `original` | Proceed to Stage 6 with the Stage-5-approved draft unchanged. |
| `A` / `B` | Replace the draft body with the selected variant. Proceed to Stage 6. |
| `iterate <A\|B> <instruction>` | Re-enter Stage 5 with the chosen variant as the new starting draft. Operator gives a Stage-5 instruction (`tighten`, `rewrite hook`, free-text rewrite). After re-approval at Stage 5, Stage 5.5 runs again on the new draft. |
| `skip` | Discard variants. Proceed to Stage 6 with the original draft. |

The selected variant (or the original) is what `helpers/save.py` writes to `$NOTES_DIR/posts/x/`. The variant attribution (which `@handle` was the exemplar) is **not** stored in the saved file — the post stands on its own; the corpus is a private aid to drafting.

---

## 7. Failure modes

| Detected | Behavior | Message |
|---|---|---|
| `examples.local.md` absent | Skip silently | none |
| File present, zero entries parsed | Skip | `Corpus mirror: no entries available — skipping.` |
| IO error on read | Skip | `Corpus mirror: read failed — skipping. (<error class>)` |
| Individual entry malformed | Drop that entry; continue | After render: `Note: N corpus entries skipped due to malformed metadata.` |
| Zero entries clear the floor | Skip silently; original draft proceeds | none |
| Rewrite breaks 280-char ceiling on shortform | Variant discarded; if no variants remain, treat as "zero clear floor" | none |
| Parser exception (catastrophic) | Skip | `Corpus mirror: parse failed — skipping.` |

The skill never fails on corpus issues — same posture as reaction recap (`SPEC.md` §6.p).

Parsing: entries delimited by `^### <id>$`, metadata as `- key: value` list, body as the first blockquote. Pure stdlib (`re`, `pathlib`). Implementation: `skill/helpers/mirror.py`, matching the pattern of existing helpers.

---

## 8. Backward compatibility & rollout

The skill must remain fully functional when `examples.local.md` is absent — the state of every fork. Forkers without a corpus see the existing 7-stage flow unchanged.

Phase C changes:

- **`SKILL.md`** — new section `### Stage 5.5 — Style-applied variants (conditional)` between Stage 5 and Stage 6. Conditional note: "Stage 5.5 runs only when `examples.local.md` exists, parses, and yields at least one match above threshold."
- **`examples-template.md`** — add `guide_compliance` and `near_duplicate_of` fields with short descriptions.
- **`skill/helpers/mirror.py`** — new helper. Parses corpus, scores entries, returns top-N matches as JSON.
- **Additional Resources** — reference the new schema; note `examples.local.md` is operator-private and gitignored.

`drafting-guide.md` is untouched. Stage 5.5 also reads it during style application — rules 1–23 stay the floor regardless of exemplar register. Version bump decided in Phase C.

---

*SPEC v0.2 authored 2026-05-15 under the `@skill-designer` role. Phase A decisions encoded throughout; Phase B mid-flight revisions explicitly named in the revision note above ("mirror → style-apply" pivot; compliance + dedup schema additions; four Phase-C open questions resolved). Phase C is the next step and is explicitly out of scope for this document.*
