Draft **exactly one** standalone post body from the single seed in section E.

Target **400–650 characters**, in three or four short paragraphs.

## Step 1 — find the moment

The seed's `text` is a whole session's record, not a summary. It is long on purpose. Read it for
**one moment a stranger could use**: a specific instant where something was happening and you
noticed something.

A moment has four parts, usually spread across the record rather than sitting in one paragraph:
the **problem** (what was being attempted, in plain terms), the **friction** (what made it hard,
tedious, slow or wrong), the **turn** (what was tried, noticed, ruled out or discovered), and
**what it cost or saved**.

Look hardest at where things went differently than planned: what was ruled out and why, what was
held rather than shipped, what was still open at the end, what the session's own critique says.
That is where the friction lives. The parts that read as achievements are where it has already
been polished out.

If the record holds no such moment, skip with `gate:thin`. That is a correct and common outcome.

## Step 2 — the five laws

Each of these was learned from a draft the operator rejected. They are not style preferences.

### Law 0 — cut it

Drafts at this length get judged understandable and then, every single time, too wordy. Assume
yours is too. **Write the post, then compress it, and return ONLY the compressed version.**

1. **Cut sentences.** Keep exactly four jobs: the world and the stake, the surprise, the evidence
   that settled it, the landing. A sentence doing none of those goes, however true or hard-won. A
   second interesting fact is not a bonus; it is what makes the post too long.
2. **Cut words.** "blocked by one checklist item: a mobile layout bug marked verified, where
   content on phones under 390 pixels wide got clipped off screen" says one thing in twenty-eight
   words. Say it in ten. Prefer the shorter word, drop every qualifier that survives deletion,
   never restate in the landing what the evidence already showed.

Crisp is not clipped. Full sentences, plain words, nothing ornamental.

### Law 1 — no noun the reader has not met

A reader arrives cold. They have never seen this project, do not know what it does, and will not
look anything up. **Every project-specific noun must be introduced in plain words the first time
it appears, in the same sentence.** Real rejections:

- "A mobile clipping bug blocked my invites." — *what are invites?*
- "Three runs on my iPhone." — *three runs of what?*
- "The agent was talking. Status line still said warming up." — *what agent, talking about what?*

The fix is not to delete the noun. It is to say what it is: "the links I send strangers so they
can try the thing", "a voice agent that talks through an idea with you". One clause each.

Banned unless the post explains itself without them: commit names, PR numbers, branch names,
phase or step labels, file names, code symbols, internal jargon.

### Law 2 — land it

The post must end on something the reader can carry away and use — not a summary of what
happened, but what it *means*. Drafts have failed by stopping at the evidence ("2030 ms cold,
333 ms warm") and then nothing. The measurement is the setup, not the ending.

The landing must follow from what the post just showed, be true beyond this one project, and be
said in **ordinary language**. It does not have to be clever. The one sentence the operator
stumbled on in an otherwise-approved draft was its most clever. A plain honest limit — what this
does *not* prove — is a good landing.

### Law 3 — one story

A session record often holds two or three separate stories. **Pick one and drop the rest.** A
post that moves to a second, unrelated finding loses the reader at the seam, even when both
findings are good.

### Law 4 — open in a moment, not with a definition

Open with yourself doing something, and let the thing get explained inside that sentence. Keep it
to short simple sentences — not one compound sentence carrying a clause, a colon and a nested
definition.

- Works: "I was getting ready to invite strangers to try a voice agent I built…"
- Fails: "A voice agent talks through an idea with anyone who opens the link to try it."

Both introduce the product; only the first gives the reader a person and a situation. A
definition as the first sentence reads as a brochure and gets skipped.

## Step 3 — the gate

1. **Reader** — does it address one of the target reader's dreams, challenges or fears?
2. **Pillar** — inside a content pillar? Off-pillar material is not postable, however good.
3. **Provenance** — every number, quote, tense and causal claim traceable to the seed's `text`?
   Plausible is still fabricated.
4. **Confidentiality** — client, family or private-infrastructure content? When in doubt, skip:
   an unattended system cannot ask.
5. **Register** — section A §4. Default register only.
6. **Shape** — 400–650 characters, three or four paragraphs, never one block.
7. **Stranger** — hand it to a builder who knows nothing about this project and has read nothing
   else. Do they follow it on one pass, and is there something in it for them?

## Banned constructions

- **"X is the easy part. Y is not."** Overused; do not use it in any form.
- Opening on a completed action ("I renamed X", "Shipped Y", "Built and smoked Z").
- Process telemetry as the subject — how many reviews ran, tests passed, commits landed. What a
  review *found*, and why it was hard to see, is the story.

## Output — draft

```json
{
  "decision": "draft",
  "pillar": "P1",
  "body": "the finished post body, verbatim, paragraphs separated by a BLANK LINE (\\n\\n)",
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
you would write. Line breaks inside it are real line breaks in the published post.

## Output — skip

```json
{ "decision": "skip", "reason": "gate:thin", "note": "one short line, no body text" }
```

`reason` must be exactly one of: `gate:reader`, `gate:pillar`, `gate:provenance`,
`gate:confidentiality`, `gate:register`, `gate:guide`, `gate:shape`, `gate:thin`.

Use `gate:thin` when the record carries no moment worth a stranger's attention, or when the only
post available would be telemetry. That is a normal outcome and much better than a padded draft.
