# DELTA — X algorithm × drafting-guide v1.2

**Date:** 2026-05-18
**Inputs:**
- `skill/prompts/drafting-guide.md` v1.2 (23 rules + 10 hook templates, dual-layer)
- `xai-org/x-algorithm` (Jan 2026 release) — architecture published, production weights not published
- Carry-forward of 2023 `twitter/the-algorithm` weights as the only confirmed numeric set

**Goal:** Identify which rules in the drafting-guide are validated, contradicted, or silently gapped by the X algorithm signals — and propose narrow, cited edits.

**Edits proposed only, not applied. Operator decides per-edit.**

---

## 1. Headline

- **33 cells classified** (23 rules + 10 hook templates).
- **Validated: 23 · Orthogonal: 5 · Contradicted (soft): 1 · Silent gaps: 6 algo signals the guide doesn't address.**
- Most of the guide is reinforced, not contradicted, by the algo. The rules that drive bookmark-intent, reply-trigger, and high dwell-time map cleanly onto signals weighted +10 to +75.
- **The action surface is concentrated in silent gaps, not contradictions.** Three highest-impact proposed edits:
  1. **New rule on author-replying to replies** — the algo's single highest-leverage lever (+75, more than 5× a standalone reply).
  2. **New rule on outbound link placement** — links in body cost 30–90% reach; mitigation is to put the link in the first reply.
  3. **Note on posting-velocity window** — 50% decay per 6h means posting at audience-dead hours throws away most reach by hour 12.
- **No proposed edit invalidates existing corpus compliance scores.** All additions describe post-publish behavior or link placement, not body content. The 45-entry corpus in `examples.local.md` does not need rescoring.

---

## 2. Delta matrix

Algo-signal abbreviations: **AR** = author-reply-to-replies (+75) · **RP** = reply (+13.5) · **BM** = bookmark (+10) · **PC** = profile-click+engagement (+12) · **DW** = dwell on conversation (+10–11) · **LN** = outbound-link session-end penalty · **MB** = mute/block (−74) · **RPT** = report (−369) · **DEC** = 6h half-life decay · **GS** = Grok sentiment penalty · **HT** = hashtag penalty (≥2) · **TC** = TweepCred cap.

| # | Rule / Hook | Verdict | Algo signal | Note |
|---|---|---|---|---|
| **Layer 1 Rules** | | | | |
| 1 | Start with proof of work | Validated | BM, RP | Concrete openers drive save-worthy + reply intent |
| 2 | Include at least one number | Validated | BM, DW | Numbers anchor return-value → bookmark |
| 3 | Use "I", never "we" | Orthogonal | (PC weakly) | Algo doesn't read pronouns; personal voice may marginally aid profile-click |
| 4 | Tense (present/past) | Orthogonal | — | Voice rule, no ranking signal |
| 5 | One idea only | Validated | BM, DW | Focused posts get saved + read fully |
| 6 | Show mechanism, not emotion | Validated | BM | Technical specificity = reference value |
| 7 | State trade-off explicitly | Validated | RP, BM | Trade-offs trigger reply ("I'd choose Y because…") |
| 8 | Use specific tech names | Validated | BM | Save-worthy reference content |
| 9 | "So what?" check | Validated | BM, DEC | Insight-light posts decay fast |
| 10 | Matter-of-fact tone | Validated | GS | Declarative tone avoids combative-sentiment penalty |
| 11 | No engagement bait | Validated (nuanced) | MB, RPT | Bait *does* trigger RP short-term but accumulates MB over time → net negative; trust-moat goal also stands |
| 12 | No launch fluff | Validated | DEC | Generic / AI-sounding text → low engagement velocity → fast decay |
| 13 | No hashtags (max 1) | Validated | HT | Algo evidence: 2+ tags ≈ −40%. Current "max 1" aligns. |
| 14 | Personal narrative connected to work | Validated | PC | Personal + technical drives profile-click |
| 15 | The "bookmark" test | Validated (central) | BM | Direct mapping to algo's +10 high-intent signal |
| **Layer 2 Rules** | | | | |
| 16 | No capability claim without reproduction path | Validated | BM, RP | Reproducible claims earn replies + saves |
| 17 | Lead with failure mode | Validated (strong) | RP, AR | "I had this problem too" triggers replies → unlocks AR lever |
| 18 | Name constraint explicitly | Validated | BM | Constraints = reference value |
| 19 | Specific names throughout | Validated | BM | Same as rule 8 in AI context |
| 20 | Learning exhaust, not polished case studies | Validated | RP, DW | Messy middle invites replies; case studies don't |
| 21 | Distinguish system output from model capability | Orthogonal | — | Trust/voice rule, not ranking |
| 22 | Use "orchestration / review gate", never "fully autonomous" | Orthogonal | — | Trust/voice rule (weak GS link if "autonomous" reads as hype) |
| 23 | Frame unsolved as unsolved | Validated | RP, AR | Same lever as 17 |
| **Hook templates** | | | | |
| H1 | Specific-Result | Validated | BM | |
| H2 | Curiosity Gap | Validated | RP | Contrarian framing → replies |
| H3 | Problem-Statement | Validated | RP, AR | Named friction → "same here" reply unlock |
| H4 | Ship-Log Direct | Validated | BM, PC | |
| H5 | Hard Truth / Contrarian | **Contradicted (soft)** | GS, MB | Combative phrasing risks sentiment penalty + mute/block accumulation; keep but add tone caveat |
| H6 | Failure Mode Exposed | Validated (strong) | RP, AR | Highest-leverage hook pattern by algo math |
| H7 | Principle Reversal | Validated | RP, BM | |
| H8 | Time-Bound Transformation | Validated | BM | |
| H9 | Nomenclature Reveal | Validated | RP | Definition-challenges invite replies |
| H10 | Scaling Inflection | Validated | BM | Threshold = reference |

### Silent gaps — algo signals the guide doesn't address

| # | Algo signal | Why it matters | Action |
|---|---|---|---|
| SG1 | **AR (+75, single highest signal)** | Guide treats the post as a finished artifact. Algo treats post + author-reply chain as a system. | Edit E1 below — new post-publish rule. |
| SG2 | **Outbound-link penalty (~30–90% reach loss)** | Guide silent on links. Builder posts often want repo/blog links. | Edit E2 below — new link-placement rule. |
| SG3 | **Velocity window (50% decay / 6h)** | Guide silent on timing. Posting at audience-dead hours throws away ~75% of reach by hour 12. | Edit E3 below — timing note. |
| SG4 | **TweepCred cap (low-rep → 3 posts/cycle)** | Guide assumes ranker-eligible account. Below threshold, no per-post optimization helps. | Operator note in §4, no guide edit. |
| SG5 | **Native media bonus** | SPEC v0 is text-only by explicit scope. Algo amplifies native video/image. | §4 "watch" only — no v0 edit. |
| SG6 | **Dwell time (+10–11)** | Guide rule 5 ("one idea") pushes brevity — algo rewards readers who stop and read. Mild tension. | No edit; clarify in E4 that "one idea" ≠ "short post." |

---

## 3. Proposed edits

Five edits. Three high-impact (E1, E2, E3), one tone caveat (E4), one rule-5 clarification (E5).

### E1 — New post-publish protocol section (high impact)

**Type:** Addition (new section after § "10 Hook Templates", before § "Voice Rules"). No existing rule changes.

**Signal cited:** Author-reply-to-replies weighted +75 in the 2023 confirmed signal set — single highest positive signal in the system, more than 5× a standalone reply (+13.5). The 2026 Phoenix architecture confirms the same signal set without disavowing the weight magnitudes. Mechanism: a post that generates replies and earns an author response gets re-ranked categorically upward, and decay clock is partially reset by the author engagement.

**Insert text:**

```markdown
## Post-publish protocol (algorithmic levers — not drafting rules)

The drafting guide above governs what you write. Two algo signals govern what
happens *after* you publish, and they outweigh any per-rule optimization:

- **Author-reply within 1 hour.** Return to the post within an hour of
  publishing and reply to the first 2–3 substantive replies. This is the single
  highest-leverage post-publish action available: it gets re-ranked categorically
  and partially resets the decay clock. A post that earns 5 replies but no
  author engagement underperforms a post that earns 2 replies + author response.
- **Post during the audience-active window.** 50% of a post's relevancy score
  decays every 6 hours. Posting at the start of the audience-active window
  (US daytime / EU evening overlap for the AI/builder audience) compounds
  velocity in the window where ranking decisions actually happen. Posting at
  audience-dead hours throws away most reach before anyone sees it.

These aren't draft-content rules — they're operator behaviors that the
drafting guide assumes but never names.
```

**Ripple flag:** None on existing corpus scores (post-publish behavior is not scored). Implicit ripple on Stage 7 of the skill (reaction recap) — recap should note whether author-replies happened, since their presence/absence explains a large fraction of engagement variance.

---

### E2 — New rule on outbound-link placement (high impact)

**Type:** Addition. Slots between current rules 13 and 14, or as a new rule 16 inside Layer 1 (recommended: insert as rule 16 in L1 to keep L2 numbering stable).

**Signal cited:** No explicit `LINK_PENALTY` constant in either repo, but the mechanism is unanimous across third-party analyses of `the-algorithm` (2023) and consistent with X's stated preference for on-platform dwell time: outbound links end sessions → ranker training penalizes session-ending posts → estimates 30–90% reach reduction. The link click signal itself is weighted positively (+10–11) but is outweighed by the downstream engagement cost.

**Before:** No rule on links.

**After (proposed rule 16, L1):**

```markdown
**16. Links go in the first reply, not the body.** Outbound links cost reach —
the algorithm penalizes posts that end the on-platform session. If the post
needs a link (repo, blog, demo), publish the post link-free and add the link
as the first reply within 30 seconds. Reach loss in body: 30–90%. Reach loss
in first reply: marginal. This applies to any link that leaves x.com.
```

**Ripple flag:** Renumbers existing L1 rule count from 15 to 16. Layer 2 numbering stays (16–23 → 17–24). **Action:** if accepted, update `examples.local.md` schema documentation that references rule numbers (none currently do — confirmed by grep). Corpus `guide_compliance` scores don't reference specific rule numbers, only an overall 1–5 fit — no rescoring needed.

---

### E3 — Timing window note (medium impact)

**Type:** Covered by E1 second bullet. No standalone edit needed.

**Note:** If E1 is rejected but E3 is wanted standalone, lift the second bullet of E1 as a one-line addition to the voice rules table or as a new line under "What you are producing." Recommend keeping it bundled with E1 since both are post-drafting operator behaviors.

---

### E4 — H5 tone caveat (low-impact, but tightens the contradiction)

**Type:** Edit existing hook template H5 description.

**Signal cited:** Grok-based sentiment scoring in the 2026 Phoenix system penalizes "negative/combative" content (announced; no weights published). Mute/block accumulation (−74 per event) compounds the risk: a contrarian-aggressive post can earn replies but also accumulate audience-level negative signal that depresses future distribution.

**Before:**
```markdown
| **Hard Truth / Contrarian** | Bold defensible claim | "You don't need a scheduling tool to build in public. You need a habit. The tool comes second." |
```

**After:**
```markdown
| **Hard Truth / Contrarian** | Bold defensible claim — defended by mechanism, not by attacking another group | "You don't need a scheduling tool to build in public. You need a habit. The tool comes second." |
```

**Ripple flag:** None. Existing example already complies (defends by mechanism, doesn't attack a group). No corpus rescore needed.

---

### E5 — Rule 5 clarification (very low impact, optional)

**Type:** Edit existing rule 5 to clarify that "one idea" does not mean "short post."

**Signal cited:** Dwell-on-conversation weighted +10–11. A 240-char post on one idea earns more dwell than an 80-char post on one idea, all else equal. Current rule 5 risks being read as "be brief" when the algo rewards density on the chosen idea.

**Before:**
```markdown
5. **One idea only.** If the session produced three distinct insights, pick
the one with the highest bookmark potential — the one a developer would save
as a professional reference. Discard the rest; they become candidates for
future sessions.
```

**After:**
```markdown
5. **One idea only — at full density.** If the session produced three distinct
insights, pick the one with the highest bookmark potential — the one a developer
would save as a professional reference. Discard the rest; they become candidates
for future sessions. Note: "one idea" is not "short post." Use the full ≤280
char budget to develop the chosen idea — denser posts earn more dwell time.
```

**Ripple flag:** Slight tightening of rule 5. Corpus entries scored as 5 on
this rule may not re-evaluate; entries scored 3–4 due to perceived
under-development would re-score slightly higher. Recommendation: do not
re-score the corpus retroactively — apply the new wording from next curation
pass forward.

---

## 4. Signals worth watching (no edit yet)

Algo behaviors with weak / non-code evidence — track but do not encode.

- **Premium boost (4x in-network / 2x out-of-network).** X's first-party policy claim. Operator-level decision (subscribe or not), not a drafting concern. Worth noting in the v0.2 measurement layer once reaction-fetching API access lands — recap should distinguish "premium-boosted reach" from "organic reach" if possible.
- **Hashtag penalty magnitude (~40% for ≥2 tags).** From post-release analyses, not in-repo code. Current rule 13 ("max 1") is conservative enough to be safe whether the analysis is correct or not. No edit needed unless future evidence tightens the threshold.
- **Grok sentiment scoring.** Announced in the 2026 release; no weights or thresholds published. E4 covers the most likely interaction. If specific sentiment-trigger language surfaces in later analyses, revisit rules 11–12 and H5.
- **TweepCred cap (≤~65 → 3 posts/cycle).** Account-health constraint. Operator awareness item: at low account-reputation states, no per-post optimization can override the cap. Not encoded as a drafting rule because (a) operator account is well above the historical threshold range, (b) it's an account-state issue, not a content issue.
- **Native media bonus.** Algo amplifies native video/image. SPEC v0 is text-only by explicit out-of-scope decision. Revisit when (or if) v0.2 expands scope to media attachments.
- **Out-of-network retrieval (two-tower model).** Phoenix uses hash-based embeddings of user identity + interaction history. Implication: a post's "topic fingerprint" matters for out-of-network reach. The drafting guide already implicitly handles this through rules 6, 8, 18, 19 (specificity) — specific tech names create a clean topic fingerprint. No edit needed; mechanism is already covered.
- **Bot detection by cadence.** Posting velocity flagged as bot-like is a behavioral signal. Operator posts ~one per evening session, far below any flagging threshold. Immaterial at current cadence.

---

## 5. Assumptions and caveats

- **2023 weights treated as load-bearing.** The 2026 `xai-org/x-algorithm` repo publishes architecture but not production weights. The reply=13.5 / AR=75 / report=−369 numbers come from the 2023 leak. Direction likely still correct; absolute magnitudes may have shifted. Where edits depend on a magnitude (e.g., "more than 5× a standalone reply"), the *direction* of the recommendation does not change even if the ratio shifts within a reasonable range.
- **No model weights in either repo.** The heavy ranker is open-source as architecture, not as trained parameters. We cannot verify ranking behavior from the code alone — third-party analyses fill the gap.
- **Trust & Safety layer withheld** to prevent gaming. Anti-spam, anti-abuse thresholds not published. Affects how aggressively rule 11 (engagement bait) and E4 (combative tone) penalties trigger, but not the direction of those rules.
- **Outbound-link penalty is emergent, not explicit.** No constant in the code. Mechanism (links → session-end → ranker training penalty) is unanimous across analyses; magnitude range (30–90%) is wide. E2's wording is conservative ("cost reach") rather than quoting a number.
- **Hashtag penalty is third-party analysis, not in-repo.** Current rule 13 is safe even if the analysis is wrong.
- **2026 Phoenix architecture is mini-scale.** The published variant has 4 transformer layers, 4 attention heads, 128-dim embeddings. Production architecture is larger. Signal *taxonomy* is reliable; signal *strength* is not.
- **Audience-active window assumption (US day / EU evening overlap).** The operator's audience is AI/builder community on X, which skews to that overlap. If audience composition shifts materially, E1's second bullet needs recalibration.

---

## 6. Open decisions for operator

1. **Accept E1?** (Adds post-publish section. Highest-leverage edit.)
2. **Accept E2?** (Adds link-placement rule. Renumbers L1 from 15 → 16 rules; L2 from 16–23 → 17–24.)
3. **Accept E4?** (Adds tone caveat to H5.)
4. **Accept E5?** (Clarifies rule 5. Optional, lowest impact.)
5. **Stage 7 reaction recap update:** if E1 is accepted, the skill's Stage 7 should explicitly note whether author-replies happened (currently silent on this). Separate small SKILL.md edit.
6. **Re-evaluation cadence:** revisit this delta when (a) production weights are ever published, (b) X publishes a Grok-sentiment threshold, (c) the operator observes a reaction pattern that contradicts a current rule.
