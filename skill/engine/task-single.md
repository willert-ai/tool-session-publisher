Draft **exactly one** standalone post body from the single seed in section E.

## Step 1 — find the moment (do this before anything else)

The seed's `text` is a whole session's record, not a summary. It is long on purpose. Read it
looking for **one moment a stranger could use**, and build the post on that.

A moment has four parts, and they are usually spread across the record rather than sitting in one
paragraph:

- **the problem** — what was actually being attempted, in plain terms;
- **the friction** — what made it hard, tedious, slow or wrong;
- **the turn** — what changed: a thing tried, noticed, ruled out, or discovered;
- **what it cost or saved** — the concrete difference the turn made.

The worked example the operator gave, in that shape: probing a browser console by hand was a
hassle (problem + friction) until noticing a Chrome DevTools MCP server already existed (turn),
after which the debugging collapsed (cost). A stranger who has never seen the project can follow
that, and can use it tomorrow.

Look hardest at the parts of the record where something went differently than planned: what was
ruled out and why, what was held rather than shipped, what was still open at the end, what the
session's own critique of itself says. That is where the friction lives. The parts that read as
achievements are usually where it has already been polished out.

**If the record holds no such moment, skip with `gate:thin`.** That is a correct and common
outcome. A tick that files nothing costs nothing.

## Step 2 — the two ways this goes wrong

Both have happened. Check the draft against them before the gates.

**Process telemetry is not a moment.** How many reviews ran, how many findings came back, how many
tests or gates passed, how many commits shipped — that is the work's bookkeeping. It reads as
content because it has numbers in it, and it tells a reader nothing they can use. If the post
would be equally true of any project that runs reviews, it is telemetry. Drop it and find the
moment underneath: what the review *found*, and why that was hard to see.

**A reader who cannot follow it gets nothing, however true it is.** Write for someone meeting this
cold in a feed, with no idea what the project is. That means:

- no internal shorthand — commit names, PR numbers, ticket ids, branch names, phase or step labels,
  or a symbol from the codebase — unless the post explains itself without them;
- name the thing in ordinary words. A reader does not know what the identifier refers to and will
  not look it up;
- density is not compression. One idea carried all the way through beats three ideas stacked into
  280 characters. If a sentence needs a sentence you did not write, the post is too compressed.

## Step 3 — the pre-draft gate

Run it in order. Any failure means skip the seed.

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
8. **Stranger gate** — hand the body to a reader who knows nothing about this project and has
   read nothing else. Do they follow it on one pass, and is there something in it for them? If
   not, skip with `gate:thin` rather than trimming a word out of it.

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

Use `gate:thin` when the record carries no moment worth a stranger's attention, or when the only
post available would be telemetry. That is a normal outcome and a much better one than a padded
draft.
