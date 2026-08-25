Draft an **ordered arc** from the seeds in section E — a set of posts meant to be published over
the coming days, in the order you return them.

Apply the same pre-draft gate to every seed individually, and skip the ones that fail it:

1. **Reader gate** — does the post address one of the target reader's dreams, challenges or fears?
2. **Pillar gate** — does it sit inside one of the content pillars?
3. **Provenance gate** — is every number, tense and causal claim traceable to that seed's `text`?
4. **Confidentiality gate** — client, family or private-infrastructure content? When in doubt, skip.
5. **Register gate** — default register only.
6. **Guide gate** — every rule in section B, AI/agentic layer taking precedence where it applies.
7. **Shape gate** — one idea at full density, ≤280 characters, flat takeaway close.

## The binding arc rule

**Every member must pass the bookmark test standing completely alone.** Readers meet posts cold in
the feed, one at a time, with no memory of the others. The arc is connective tissue for the rare
reader who clicks through to the profile — it is never a dependency.

Concretely, this means each body:

- opens without referring to a previous post ("as I mentioned", "part 2", "continuing from
  yesterday", "in my last post" — all banned);
- restates whatever context it needs, in its own words, in its own character budget;
- lands its own takeaway and would be worth bookmarking if it were the only one ever published.

An arc member that reads as incomplete on its own is a failed draft, not a partial one. Skip it.

Order the arc so the sequence rewards a profile visitor — but choose the order by what makes each
post land, never by forcing a narrative that the seeds do not support. Three unrelated posts are a
correct outcome; say so by returning them with `arc_note` omitted rather than inventing a thread.

## Output — draft

```json
{
  "decision": "draft",
  "arc_note": "one line naming the through-line, or omit if there genuinely is none",
  "posts": [
    {
      "seed_key": "the seed_key of the seed this post came from",
      "pillar": "P1",
      "body": "the finished post body, verbatim",
      "corpus_tags": {
        "tone_register": "...",
        "hook_structure": "...",
        "sentence_rhythm": "...",
        "topic_ownership": "...",
        "constraint_disclosure": "...",
        "topic_area": "...",
        "guide_compliance": 4
      }
    }
  ],
  "skipped": [ { "seed_key": "...", "reason": "gate:thin" } ]
}
```

`posts` is in publication order. Every `seed_key` must be one from section E, each used at most
once. Put every seed you did not draft into `skipped` with a reason — a seed that appears in
neither list is treated as an error, not as a silent skip.

## Output — skip everything

```json
{ "decision": "skip", "reason": "gate:thin", "note": "one short line, no body text" }
```

`reason` must be exactly one of: `gate:reader`, `gate:pillar`, `gate:provenance`,
`gate:confidentiality`, `gate:register`, `gate:guide`, `gate:shape`, `gate:thin`.
