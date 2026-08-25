Draft **exactly one** standalone post body from the single seed in section E.

Before drafting, run the operator's pre-draft gate in order. Any failure means skip the seed.

1. **Reader gate** — does the post address one of the target reader's dreams, challenges or fears?
2. **Pillar gate** — does it sit inside one of the content pillars? Off-pillar material is not
   postable, however good it is.
3. **Provenance gate** — is every number, every tense and every causal claim traceable to the
   seed's `text`? Plausible is still fabricated.
4. **Confidentiality gate** — client, family or private-infrastructure content? When in doubt,
   skip: an unattended system cannot ask.
5. **Register gate** — default register only; no operator-override registers.
6. **Guide gate** — every rule in section B, with the AI/agentic layer taking precedence when the
   subject is LLM tooling or agentic systems.
7. **Shape gate** — one idea at full density, ≤280 characters, closing on a flat takeaway line.

## Output — draft

```json
{
  "decision": "draft",
  "pillar": "P1",
  "body": "the finished post body, verbatim, ready to paste",
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
```

`body` is the post itself — never a topic string, never a title, never a description of a post
you would write. Line breaks inside it are real line breaks in the published post; use them.

## Output — skip

```json
{ "decision": "skip", "reason": "gate:provenance", "note": "one short line, no body text" }
```

`reason` must be exactly one of: `gate:reader`, `gate:pillar`, `gate:provenance`,
`gate:confidentiality`, `gate:register`, `gate:guide`, `gate:shape`, `gate:thin`.

Use `gate:thin` when the seed is simply too thin to carry a post. That is a normal outcome and a
much better one than a padded draft.
