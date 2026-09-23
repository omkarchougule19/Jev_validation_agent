# Jev-Guard — Build Plan

## What this is, in plain words

An LLM answers a question. Before you show that answer to a real user, you
usually want to double-check it: did it actually answer the question? Does
it contradict the source material you gave it? Is it in the format you
asked for?

Today, most tools do that double-check by asking *another full LLM* to
grade the first one. That's slow and it costs real money, every single
time, for what's usually a simple yes/no or pick-one decision.

This project swaps that grading step for **Jev**, a small, fast, cheap
"decision" model from TypeSafe AI. It's not built to write text — it's
built to answer bounded questions like "yes or no" or "pick one of these
options," in a fraction of a second, for a fraction of a cent. That's
exactly the shape of question a guardrail check actually is.

**The pitch in one sentence:** a drop-in checker for LLM answers that's
fast and cheap enough to run on every single response, proven against the
slow-and-expensive way of doing the same thing.

## The three checks (v1)

1. **On-topic** — does this answer actually address what was asked?
   (Jev's yes/no primitive, called "Noul.")
2. **Contradicts the source** — if the answer was supposed to be based on
   some given text (like a RAG pipeline's retrieved documents), does it
   actually agree with that text, or does it make something up? This one
   gives a *graded* score (0 = totally consistent, 1 = flatly contradicts),
   not just yes/no. (Jev's scoring primitive, called "Score.")
3. **Right format** — if you asked for a specific structure (valid JSON,
   required fields present), did you get it? (Jev's pick-one primitive,
   called "Choice.")

Each check is just one Jev call. Nothing fancier than that.

## What "done" looks like

- A function you can call on any piece of LLM output:
  `guard(answer, context=None, checks=[...])` → tells you pass / needs a
  human look / block, for each check you asked for.
- A small, honest proof that it actually works: a test set of ~50-100
  made-up examples (some clearly good, some clearly bad, on purpose) run
  through Jev-Guard, showing how often it catches the bad ones and how
  often it wrongly flags the good ones.
- The same test set also run through a normal "ask an LLM to grade it"
  baseline, so there's a real side-by-side: how much faster, how much
  cheaper, and how the accuracy compares.

That's it. No async pipeline, no plugin framework, no dashboard. A
working checker, proof it works, and a number showing why it's worth
using instead of the slow way.

## Why this design (not a bigger one)

The last project (an accuracy/consistency/calibration benchmark against
BANKING77) got bogged down because it needed a big, rate-limited pile of
API calls just to prove anything. This project avoids that on purpose:
- The test set is *made up on purpose* — a handful of good/bad answer
  templates with the details swapped in — not scraped or hand-labeled
  from a real dataset. That's a deliberate trade-off: less realistic
  variety, but it means we don't need thousands of calls to get a
  meaningful table.
- Every check is exactly one API call, no repeats, no consistency testing.
  Simpler claim, simpler proof.

## Where things stand on access

- **Jev**: reached through OpenRouter (`typesafe/jev-1.13`), not TypeSafe's
  own API directly — this was already sorted out and tested working in the
  last project. Same approach here, no changes needed.
- **Baseline "ask an LLM to grade it" judge**: also through OpenRouter, so
  everything in this project goes through one provider. Model choice is a
  config value, not hardcoded — defaults to a cheap, well-known model.
- No Groq this time. That's what caused all the pain last time (daily
  rate limits), and it isn't needed here — OpenRouter alone covers both
  Jev and the baseline model.

## Repo layout (target)

```
jev-guard/
├── plan.md / decisions.md / logs.md   ← this file + its two companions
├── .env.example / .gitignore / requirements.txt
├── src/jev_guard/
│   ├── client.py     ← thin Jev wrapper (Choice / Noul / Score calls via OpenRouter)
│   ├── checks.py     ← the 3 checks, defined simply (what to ask, what counts as a pass)
│   ├── guard.py       ← the guard() function that ties it together
│   ├── baseline.py    ← the "ask a full LLM to grade it" comparison judge
│   └── testset.py     ← builds the ~50-100 made-up test examples
├── report.py           ← runs the test set through both, prints the comparison table
└── tests/               ← quick, no-API-needed tests for the decision logic
```

## Build order

1. **Jev client** — one small wrapper, reused straight from the last
   project's working OpenRouter integration.
2. **Checks** — the 3 checks as plain Python, each just "here's the
   instructions I give Jev, here's what counts as pass/flag/block."
3. **guard()** — runs the requested checks, collects the verdicts.
4. **Baseline judge** — the same 3 checks, but asked to a normal LLM via a
   prompt instead of Jev, for comparison.
5. **Test set** — ~50-100 made-up examples split across the 3 checks
   (known-good and known-bad on purpose).
6. **Report** — run everything, print a table: catch rate (and false-alarm
   rate) for both Jev-Guard and the baseline, plus how much faster/cheaper
   Jev-Guard was.
7. **README** — the whole pitch in one page: what it is, the comparison
   table, how to use it.

## Open questions to settle while building

- Which OpenRouter model is the baseline judge? Pick something cheap and
  recognizable (e.g. a small GPT-4o-class model) — confirm actual pricing
  on OpenRouter when we get there, don't assume.
- Exact pass/flag/block thresholds for each check — start with reasonable
  defaults, adjust once we see real results from the test set.
