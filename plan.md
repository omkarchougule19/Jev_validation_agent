# Jev-Guard: Build Plan

## What this is, in plain words

An LLM answers a question. Before you show that answer to a real user, you
usually want to double-check it. Did it actually answer the question? Does
it contradict the source material you gave it? Is it in the format you
asked for?

Today, most tools do that double-check by asking *another full LLM* to
grade the first one. That's slow, and it costs real money every single
time, for what's usually a simple yes/no or pick-one decision.

This project swaps that grading step for **Jev**, a small, fast, cheap
"decision" model from TypeSafe AI. It's not built to write text. It's
built to answer bounded questions like "yes or no" or "pick one of these
options," in a fraction of a second, for a fraction of a cent. That's
exactly the shape of question a guardrail check actually is.

**The pitch in one sentence:** a drop-in checker for LLM answers that's
fast and cheap enough to run on every single response, proven against the
slow and expensive way of doing the same thing.

## The three checks (v1)

1. **On-topic.** Does this answer actually address what was asked? (Jev's
   yes/no primitive, called "Noul.")
2. **Contradicts the source.** If the answer was supposed to be based on
   some given text (like a RAG pipeline's retrieved documents), does it
   actually agree with that text, or does it make something up? This one
   gives a *graded* score (0 means totally consistent, 1 means it flatly
   contradicts), not just yes or no. (Jev's scoring primitive, called
   "Score.")
3. **Right format.** If you asked for a specific structure (valid JSON,
   required fields present), did you get it? (Jev's pick-one primitive,
   called "Choice.")

Each check is just one Jev call. Nothing fancier than that.

## What "done" looks like

- A function you can call on any piece of LLM output:
  `guard(answer, context=None, checks=[...])`, which tells you pass, needs
  a human look, or block, for each check you asked for.
- A small, honest proof that it actually works: a test set of about 50 to
  100 made-up examples (some clearly good, some clearly bad, on purpose)
  run through Jev-Guard, showing how often it catches the bad ones and how
  often it wrongly flags the good ones.
- The same test set also run through a normal "ask an LLM to grade it"
  baseline, so there's a real side by side: how much faster, how much
  cheaper, and how the accuracy compares.

That's it. No async pipeline, no plugin framework, no dashboard. Just a
working checker, proof it works, and a number showing why it's worth
using instead of the slow way.

## Why this design, and not a bigger one

The last project (an accuracy, consistency, and calibration benchmark
against BANKING77) got bogged down because it needed a big, rate-limited
pile of API calls just to prove anything. This project avoids that on
purpose:
- The test set is *made up on purpose*, a handful of good and bad answer
  templates with the details swapped in, not scraped or hand-labeled from
  a real dataset. That's a deliberate trade-off. Less realistic variety,
  but it means we don't need thousands of calls to get a meaningful table.
- Every check is exactly one API call, no repeats, no consistency testing.
  Simpler claim, simpler proof.

## Where things stand on access

- **Jev** is reached through OpenRouter (`typesafe/jev-1.13`), not
  TypeSafe's own API directly. This was already sorted out and tested
  working in the last project, so the same approach is used here with no
  changes needed.
- **Baseline "ask an LLM to grade it" judge** also goes through
  OpenRouter, so everything in this project uses one provider. Model
  choice is a config value, not hardcoded, and defaults to a cheap,
  well-known model.
- No Groq this time. That's what caused all the pain last time (daily
  rate limits), and it isn't needed here since OpenRouter alone covers
  both Jev and the baseline model.

## Repo layout (target)

```
jev-guard/
├── plan.md
├── .env.example / .gitignore / requirements.txt
├── src/jev_guard/
│   ├── client.py     (thin Jev wrapper: Choice / Noul / Score calls via OpenRouter)
│   ├── checks.py     (the 3 checks, defined simply: what to ask, what counts as a pass)
│   ├── guard.py       (the guard() function that ties it together)
│   ├── baseline.py    (the "ask a full LLM to grade it" comparison judge)
│   └── testset.py     (builds the made-up test examples)
├── report.py           (runs the test set through both, prints the comparison table)
└── tests/               (quick, no-API-needed tests for the decision logic)
```

## Build order

1. **Jev client.** One small wrapper, reused straight from the last
   project's working OpenRouter integration.
2. **Checks.** The 3 checks as plain Python, each just "here's the
   instructions I give Jev, here's what counts as pass, flag, or block."
3. **guard().** Runs the requested checks and collects the verdicts.
4. **Baseline judge.** The same 3 checks, but asked to a normal LLM via a
   prompt instead of Jev, for comparison.
5. **Test set.** Made-up examples split across the 3 checks, known-good
   and known-bad on purpose.
6. **Report.** Run everything, print a table: catch rate (and false-alarm
   rate) for both Jev-Guard and the baseline, plus how much faster and
   cheaper Jev-Guard was.
7. **README.** The whole pitch in one page: what it is, the comparison
   table, how to use it.

## Open questions to settle while building

- Which OpenRouter model is the baseline judge? Pick something cheap and
  recognizable (for example, a small GPT-4o-class model), and confirm
  actual pricing on OpenRouter when we get there instead of assuming.
- Exact pass, flag, and block thresholds for each check. Start with
  reasonable defaults, then adjust once we see real results from the test
  set.

## What got added after v1 shipped

Once the working version was up, the test set was expanded to 100
examples (adding a genuinely hard tier: subtle near-misses, not just
obvious good and bad answers), and a few things were added to make the
project's claims stronger and easier to trust at a glance:

- **CI** (`.github/workflows/tests.yml`): the test suite runs on every
  push, with a badge in the README.
- **A chart** (`assets/comparison.png`): latency and catch rate, side by
  side, instead of asking someone to read a table.
- **A hard difficulty tier** in the test set: 20 of the 100 cases are
  deliberately subtle (a transposed digit, a date off by a year, an
  answer that sounds relevant but never actually answers the question),
  not just obviously good or bad. This is a direct response to an honest
  critique that the original test set was too easy for a tie to mean
  much.
- **A bootstrap confidence interval** on the catch-rate gap between Jev
  and the baseline, so "they tied" comes with a number showing whether
  that's a real tie or just noise at this sample size, the same kind of
  rigor the very first (abandoned) version of this whole idea was going
  for, but cheap to add here since it's just resampling existing results,
  not making more API calls.
- **A LICENSE file** (MIT) to back the badge, since a badge pointing at
  nothing isn't worth much.

## Packaging and live demo (built after that)

The two ideas that were parked as "future work" have now been built:

- **Proper packaging.** A real `pyproject.toml`, so the library installs
  straight from GitHub with
  `pip install git+https://github.com/omkarchougule19/Jev_validation_agent`.
  The core install needs only `typesafe-sdk`. Everything else is an
  optional extra: `[report]` for the benchmark and chart, `[demo]` for the
  demo page, `[dev]` for the tests. `guard` and `make_client` can now be
  imported straight from `jev_guard`. Publishing to PyPI itself is left
  for later, since it needs a PyPI account and the name `jev-guard`
  claimed there.
- **A live interactive demo.** `python -m jev_guard.demo` starts a small
  FastAPI app with one page: paste in an answer plus any of question,
  context, or expected format, and see each check's verdict and latency,
  with the benchmark table next to it. Because a hosted copy spends the
  host's OpenRouter credits, inputs are capped at 4,000 characters and
  each IP gets 10 checks a minute. A `Dockerfile` is included for hosting
  (Hugging Face Spaces or Render both work on a free tier). Actually
  putting it online needs the owner's account on one of those, so that
  last step is still open.

One thing the demo turned up: spot checks found more format misses than
the benchmark did (a missing closing brace, a missing comma, and a
trailing comma all passed as valid JSON). The README and the demo page
now both say plainly that the format check is a soft signal, not a
replacement for a real parser.

## Groq baseline and the speed race (built after that)

The comparison judge moved off paid usage: it's now OpenAI's open model
gpt-oss-120b, running on Groq's free tier, while Jev stays on OpenRouter.
Groq is one of the fastest AI hosts there is, so this is a tougher
opponent than gpt-4o-mini. Re-running the 100-case benchmark against it
gave about the same accuracy (no difference that holds up statistically)
with Jev about 1.9x faster end to end (22.4 s vs 41.6 s). The README now
lists speed per opponent (about 2x vs gpt-oss on Groq, about 4x vs
gpt-4o-mini) instead of one headline number.

The demo got a second page, `/race`: both judges check the same 25
answers, picked at random from the test set, live and side by side, with
each result appearing as it lands. Groq's free tier allows 30 requests a
minute, so a race is 25 cases, races run one at a time and at least a
minute apart, and there's a small daily cap. When a limit is hit the page
tells visitors to contact the developer. Races are expected to be rare
(a couple a day), so there's no replay, database or queue.

The research behind these choices (free models, limits, terms, measured
latency, streaming on Render) is in `reports/Groq baseline and race demo.md`,
kept local like `decisions.md` and `logs.md`.
