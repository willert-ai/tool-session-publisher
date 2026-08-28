Draft an **ordered arc** from the seeds in section E — a set of posts meant to be published over
the coming days, in the order you return them.

## Step 1 — find the moment in each seed (do this before anything else)

Each seed's `text` is a whole session's record, not a summary. It is long on purpose. Read each
one looking for **one moment a stranger could use**, and build that seed's post on it.

A moment has four parts, usually spread across the record rather than sitting in one paragraph:

- **the problem** — what was actually being attempted, in plain terms;
- **the friction** — what made it hard, tedious, slow or wrong;
- **the turn** — what changed: a thing tried, noticed, ruled out, or discovered;
- **what it cost or saved** — the concrete difference the turn made.

The worked example the operator gave, in that shape: probing a browser console by hand was a
hassle (problem + friction) until noticing a Chrome DevTools MCP server already existed (turn),
after which the debugging collapsed (cost). A stranger who has never seen the project can follow
that, and can use it tomorrow.

Look hardest at the parts of each record where something went differently than planned: what was
ruled out and why, what was held rather than shipped, what was still open at the end, what the
session's own critique of itself says. That is where the friction lives. **A seed whose record
holds no such moment is skipped with `gate:thin`** — an arc of two real posts beats three padded
ones, and returning nothing at all is a correct outcome.

## Step 2 — the two ways this goes wrong

Both have happened. Check every body against them before the gates.

**Process telemetry is not a moment.** How many reviews ran, how many findings came back, how many
tests or gates passed, how many commits shipped — that is the work's bookkeeping. It reads as
content because it has numbers in it, and it tells a reader nothing they can use. If a post would
be equally true of any project that runs reviews, it is telemetry. Drop it and find the moment
underneath: what the review *found*, and why that was hard to see. An arc made of telemetry is
worse than a single, because the sameness compounds across the week.

**A reader who cannot follow it gets nothing, however true it is.** Write for someone meeting each
post cold in a feed, with no idea what the project is. That means:

- no internal shorthand — commit names, PR numbers, ticket ids, branch names, phase or step labels,
  or a symbol from the codebase — unless the post explains itself without them;
- name the thing in ordinary words. A reader does not know what the identifier refers to and will
  not look it up;
- density is not compression. One idea carried all the way through beats three ideas stacked into
  280 characters. If a sentence needs a sentence you did not write, the post is too compressed.

## Step 3 — the pre-draft gate

Apply it to every seed individually, and skip the ones that fail it:

1. **Reader gate** — does the post address one of the target reader's dreams, challenges or fears?
2. **Pillar gate** — does it sit inside one of the content pillars?
3. **Provenance gate** — is every number, tense and causal claim traceable to that seed's `text`?
4. **Confidentiality gate** — client, family or private-infrastructure content? When in doubt, skip.
5. **Register gate** — default register only.
6. **Guide gate** — every rule in section B, AI/agentic layer taking precedence where it applies.
7. **Shape gate** — one idea at full density, ≤280 characters, flat takeaway close.
8. **Stranger gate** — hand the body to a reader who knows nothing about this project and has read
   nothing else, not even the other arc members. Do they follow it on one pass, and is there
   something in it for them? If not, skip that seed with `gate:thin` rather than trimming a word
   out of it.

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

Use `gate:thin` when no record carries a moment worth a stranger's attention, or when the only
posts available would be telemetry. Returning nothing is a normal outcome and a much better one
than a padded arc.
