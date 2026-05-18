# Drafting Guide — X Posts for session-publisher

**Read this before every draft. Every rule is a filter; if the draft fails any rule, rewrite before presenting.**

*Two-layer guide. Layer 1 (rules 1–16, hook templates 1–5) = general builder best practices, distilled from deep research on builder-in-public X norms (2026-05-11). Layer 2 (rules 17–24, hook templates 6–10, AI anti-patterns) = AI/agentic tools build-in-public norms, distilled from deep research on the AI builder community on X (2026-05-11). Sources cited throughout the research: Simon Willison, swyx, Andrej Karpathy, Sebastian Raschka, Ahmad Osman, Riley Goodside, Pieter Levels, Daniel Vassallo, Marc Lou, Naval Ravikant.*

---

## What you are producing

A single tweet (≤280 characters) grounded in today's real session work. This is a **terminal log of shipped work**, not a marketing update. Every post exists to build a trust moat, not to chase followers. The audience: technical peers and potential paying customers — people who build or buy software. One idea per post. One post per session.

---

## 16 Drafting Rules

1. **Start with proof of work.** The first sentence must contain a concrete result, a technical decision, or a specific obstacle cleared — from the actual session. No rhetorical questions. No "I've been thinking about..."

2. **Include at least one number.** Milliseconds, dollars, lines of code, hours, percentages, dates. Numbers are the only currency that cannot be faked. If the session has no number, invent a specific framing instead ("finally fixed the auth bug I'd been fighting for 3 days").

3. **Use "I", never "we".** Solo builder. Accountability is the asset.

4. **Present tense for live ships; past tense for reflections.** "Just pushed the beta" creates momentum. "I realised the DB was bloated" is a reflection. Pick the right tense for the kind of post.

5. **One idea only.** If the session produced three distinct insights, pick the one with the highest bookmark potential — the one a developer would save as a professional reference. Discard the rest; they become candidates for future sessions.

6. **Show the mechanism, not the emotion.** Not "today was tough." Instead: "The API kept timing out on files over 5MB. Fixed it with a multipart stream." Describe *what you did and why* — not how you felt about it.

7. **State the trade-off explicitly.** When sharing a decision: "I chose X over Y because Z." Trade-offs are the concrete DNA of build-in-public content.

8. **Use specific technology names.** SQLite, tweepy, Claude API, Stripe webhooks — not "the database" or "the payment system." Specificity earns credibility.

9. **"So what?" check.** Before finalising: does this post provide a technical lesson, a business insight, or verifiable progress? If it's just "working hard" — don't post it.

10. **Matter-of-fact tone.** "X happened. I did Y to fix it. Here is what I learned." Short declarative sentences. Developer terminal log style, not marketing brochure.

11. **No engagement bait.** Categorically remove: "Thoughts?", "Agree?", "What do you think?", "RT if you...", "Am I the only one who..."

12. **No launch fluff.** Remove on sight: "I'm so excited to", "Proud to announce", "Big things coming", "I'm humbled by", "We are committed to delivering".

13. **No hashtags.** Zero by default. If one is genuinely needed for discoverability, maximum one (#buildinpublic). Never two or more.

14. **Connect the personal narrative to the work.** Vulnerability is fine; disconnection from the work is not. "I was scared to charge the first customer — did it anyway, here are the first 3 data points" is perfect. "I feel unmotivated today" is not a post.

15. **The "bookmark" test.** Ask: would a developer peer save this post as a reference to return to later? If yes, it has earned publication. If no, it is likely too vague or too personal.

16. **Links go in the first reply, not the body.** Outbound links cost reach — the algorithm penalizes posts that end the on-platform session. If the post needs a link (repo, blog, demo), publish the post link-free and add the link as the first reply within 30 seconds. Reach loss in body: 30–90%. Reach loss in first reply: marginal. This applies to any link that leaves x.com.

---

---

## Layer 2 — AI / Agentic Tools Rules (apply when the session is about LLM tools, agents, Claude API, automation infrastructure)

The AI builder community on X has a sophisticated immune system against hype. The same patterns that work for SaaS revenue posts backfire here. Rules 17–24 override the general rules when in conflict.

**17. Never make a capability claim without a reproduction path or explicit uncertainty.** If you say "the agent now handles X," either include the specific prompt/architecture that makes it work OR explicitly acknowledge the conditions under which it fails. Unverifiable claims are the #1 trust-killer in this community.

**18. Lead with the failure mode, not the success.** "I built X expecting Y but got Z — here's why and how I fixed it" outperforms success-only posts in AI builder communities. The failure exposes a real problem; the fix makes it useful to others. Document the messy middle, not just the landing.

**19. Name the constraint explicitly.** Saying where your agent or system *cannot* go builds more credibility than projecting unlimited capability. "This works for sessions under 100k tokens — longer sessions degrade" is more trustworthy than "handles any length." The AI community rewards constraint-first framing.

**20. Use specific names throughout.** Model name (claude-sonnet-4-6, not "the AI"), token counts, latency in milliseconds, API version, framework version. "Claude API call" beats "LLM inference." "77 tokens/second on M2 Max" beats "fast local inference." Specificity is the anti-hype.

**21. Generate "learning exhaust," not polished case studies.** Post from the middle of the problem, not only from the solved state. "I'm 3 hours into this — here's the architectural decision I just made and why I'll probably regret it" is valuable. The community rewards the lab notebook, not the press release.

**22. Distinguish your system's output from the model's capability.** Say "my pipeline produces X" not "Claude does X." You own the system design; the model is an ingredient. Taking credit for the model's capability (or blaming the model for your system's failure) both read as technically unsophisticated.

**23. Use "orchestration / review gate / human-in-the-loop" — never "fully autonomous".** Production agents require human intervention ~68% of the time at around step 10. "Fully autonomous" triggers immediate skepticism. Credible agentic posts name the constraint: "escalates to operator when context exceeds budget," "human-reviewed before commit," "reliable for repetitive well-defined tasks."

**24. Frame unsolved problems as unsolved.** "We tried X and it failed because Y, here's what we tried next" earns more trust and more replies than "we solved X." The AI builder community has watched too many solved claims quietly fail. Absence of limitation disclosure is read as evidence of undisclosed limitations.

---

## 10 Hook Templates

Use one of these as the opening pattern, then fill in with session specifics.

| Template | Pattern | Example |
|---|---|---|
| **Specific-Result** | Hard number + what caused it | "Reduced cold-start latency by 40% today. The culprit was an unindexed FK on every session load." |
| **Curiosity Gap** | Common approach + contrarian choice | "Most people use Redis for session state. I'm using a plain text file. Here's why." |
| **Problem-Statement** | Shared friction named directly | "The worst part of wiring Claude API into a CLI isn't the code — it's handling stream interruptions." |
| **Ship-Log Direct** | Present tense, just-did | "Just shipped the first end-to-end dry run of session-publisher. Today's wrap-up became a draft post in 90 seconds." |
| **Hard Truth / Contrarian** | Bold defensible claim | "You don't need a scheduling tool to build in public. You need a habit. The tool comes second." |
| **Failure Mode Exposed** *(AI layer)* | Shared problem + concrete failure + fix | "I built the session-selection step expecting Claude to pick recent work. It kept picking January sessions instead. Here's why the cursor logic was wrong." |
| **Principle Reversal** *(AI layer)* | Common assumption + specific context where opposite is true | "Most people reach for vector search for session retrieval. For 500 files of known structure, a grep + date filter is 40× faster and 0 dependencies." |
| **Time-Bound Transformation** *(AI layer)* | Before-state anchored to a time + what changed architecturally | "Six months ago the session-publisher was a spec doc. Today it ran end-to-end for the first time. Here's the one architectural decision that unblocked it." |
| **Nomenclature Reveal** *(AI layer)* | Challenge what a common term actually means | "Everyone says their workflow is 'agentic.' Mine isn't — it's orchestrated tool-calling with explicit escalation gates. Here's the difference in practice." |
| **Scaling Inflection** *(AI layer)* | The threshold where the current approach breaks + what replaced it | "The simple cursor model works up to ~50 sessions. Past that, the LLM loses the oldest ones. Here's the fix." |

---

## Post-publish protocol (algorithmic levers — not drafting rules)

The drafting guide above governs what you write. Two algo signals govern what happens *after* you publish, and they outweigh any per-rule optimization:

- **Author-reply within 1 hour.** Return to the post within an hour of publishing and reply to the first 2–3 substantive replies. This is the single highest-leverage post-publish action available: it gets re-ranked categorically and partially resets the decay clock. A post that earns 5 replies but no author engagement underperforms a post that earns 2 replies + author response.
- **Post during the audience-active window.** 50% of a post's relevancy score decays every 6 hours. Posting at the start of the audience-active window (US daytime / EU evening overlap for the AI/builder audience) compounds velocity in the window where ranking decisions actually happen. Posting at audience-dead hours throws away most reach before anyone sees it.

These aren't draft-content rules — they're operator behaviors that the drafting guide assumes but never names.

---

## Voice Rules (quick ref)

| Do | Do not |
|----|--------|
| First-person singular: "I" | "We", "the team", "the company" |
| Short declarative sentences | Long subordinate clauses |
| Specific nouns and numbers | "Something", "a lot", "significant" |
| Present tense for live ships | "Going to", "planning to", "excited about" |
| Name the failure and the fix | "Today was challenging" |
| "I chose X over Y because Z" | "I decided to simplify things" |

---

## AI-Specific Anti-Patterns: Purge on Sight (Layer 2)

These are especially damaging when posting about LLM tools and agentic systems — the audience is technically sophisticated and will disengage immediately:

- **Benchmark-washing:** Reporting accuracy or performance on a controlled test set without disclosing conditions or failure modes. Example of what not to write: "My agent achieves 94% task completion." Instead: "On my test set of 37 session-selection tasks, the agent picks the right session 94% of the time. It fails consistently on sessions from 3+ months ago when tags drift."
- **Capability theater:** "My system can now autonomously do X" without a reproduction path or any acknowledgment of where it breaks. Sounds like a press release. Post the reproduction steps or post the failure rate.
- **Vague AI attribution:** "AI made this possible" / "Using AI to automate X" — says nothing about which model, which prompt pattern, which constraints. Replace with: "Using Claude's tool-use to parse SESSION_INDEX rows — 2 API calls per evening session, ~$0.003 total."
- **Model-credit confusion:** "Claude figured out the selection logic" — the model didn't figure it out; you designed the system. Own the design.
- **"We're just getting started" energy:** Any post that describes future capability without current evidence. The AI community has seen too many capability announcements that never shipped. Post what works today.
- **Accuracy claims without test conditions:** "95% accuracy" without specifying dataset, methodology, and failure modes. The community reads this as undisclosed limitations, not as achievement.
- **Vague agentic superlatives:** "100+ AI agents", "fully autonomous", "requires no human input", "self-directed." All trigger immediate skepticism from practitioners who know production reality.

---

## General Anti-Patterns: Purge on Sight (Layer 1)

- "Keep grinding everyone!" — support-group post, zero utility
- Life or career advice before the first paying customer is reached — advice avalanche, unearned
- Revenue screenshot with no technical narrative — gym-selfie pattern, status-seeking
- "10 things I learned from building X" — AI-content-farm listicle
- "Revolutionary", "game-changer", "disruptive" — vague moat
- "Working on something huge..." / "Can't wait to share!" — vague vision, no utility
- "I'm so humbled / grateful / excited" as an opener — false-humility brag
- Performance-pressure narrative ("I need to post more") — signals narrative drives work, not the reverse

---

## Engagement Signal Cheat Sheet (for reaction recap)

| Signal | Value | What it means |
|---|---|---|
| Bookmarks | High | "Save-worthy" — developer will return to this; strongest proof of value density |
| Direct shares | High | External validation; single shareable technical solution |
| Replies | Medium-high | Genuine engagement; feedback the build can use |
| Quote-tweets | Medium-high | Bold/defensible claim earned a reaction |
| Likes | Low | Passive nod; do not optimise for this; ignore as KPI |
| Impressions | Ignore | Algorithm noise; no correlation with business traction |

When a post earns high bookmarks or replies — that's a signal to double down on that topic or format in the next session. When a post gets likes but zero replies or bookmarks — it was probably too general.

---

*Version 1.3 — 2026-05-18. Added Layer 1 rule 16 (link placement) and "Post-publish protocol" section based on X algorithm signal analysis (xai-org/x-algorithm, Jan 2026). Layer 2 rules renumbered 17–24 (was 16–23). Source: `planning/DELTA_algo-vs-drafting-guide-2026-05-18.md`.*

*Version 1.2 — 2026-05-11. Layer 2 extended: rules 22–23 added; hook templates expanded to 10 (Time-Bound Transformation, Nomenclature Reveal, Scaling Inflection); AI anti-patterns section expanded with accuracy-claims and agentic-superlative patterns. Sources: deep research on AI-builder community norms, hook patterns, and anti-patterns. Update trigger: operator observes consistent reaction pattern not explained by current rules.*
