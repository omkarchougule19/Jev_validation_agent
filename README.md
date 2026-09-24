# Jev-Guard

[![Tests](https://github.com/omkarchougule19/Jev_validation_agent/actions/workflows/tests.yml/badge.svg)](https://github.com/omkarchougule19/Jev_validation_agent/actions/workflows/tests.yml)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

A fast, cheap way to double-check an LLM's answer before you show it to a
user — using **Jev** (TypeSafe AI's decision-only model) instead of asking
a second full LLM to grade the first one.

## The problem

You've got an LLM answering questions. Before that answer goes out, you
probably want to check a few things: did it actually answer the question?
Does it contradict the source material you gave it? Is it in the format
you asked for?

The usual way to check this is to ask *another LLM* — "hey GPT, does this
answer make sense?" That works, but it's slow and it costs real money,
every single time, for what's really just a yes/no or pick-one decision.

Jev-Guard swaps that grading step for Jev, a model built specifically for
bounded decisions like this — not for writing text. It's a fraction of a
second and (per TypeSafe's own pricing) a fraction of a cent, for exactly
the kind of question a guardrail check actually is.

## How it works

Three checks, each one Jev call:

| Check | Question | Jev primitive |
|---|---|---|
| **On-topic** | Does the answer actually address what was asked? | `Noul` (yes/no) |
| **Contradicts source** | Does the answer agree with the context it was supposed to be based on? Graded 0 (consistent) to 1 (flat contradiction), not just yes/no. | `Score` |
| **Right format** | Is the answer in the structure you asked for (e.g. valid JSON)? | `Choice` |

```python
from jev_guard import guard, make_client

client = make_client()
overall, results = guard(
    client,
    answer="Paris is the capital of France.",
    question="What is the capital of France?",
    context="France's capital city is Paris.",
)
print(overall)  # "pass" | "flag" | "block"
```

Each check returns `pass`, `flag` (worth a second look), or `block`. The
overall verdict is the worst of whichever checks you ran.

**If a check's API call fails** (timeout, rate limit, auth error), it
doesn't crash `guard()` — a guardrail that takes down your app on its own
infrastructure hiccup is worse than one that degrades gracefully. It
defaults to flagging that check for human review (`on_error="flag"`);
pass `on_error="block"` for a stricter fail-closed policy if that's the
right call for your use case.

## Does it actually work? (measured, not claimed)

Built a test set of 100 made-up examples across the three checks and ran
every one through both Jev-Guard and a normal "ask an LLM to grade it"
baseline (`gpt-4o-mini` via OpenRouter), scored against the exact same
pass/flag/block thresholds for both, so it's a fair comparison of the
*judge*, not the policy.

![Latency and catch-rate comparison](assets/comparison.png)

| Check | Jev catch rate | Baseline catch rate | Jev latency (median) | Baseline latency (median) |
|---|---|---|---|---|
| On-topic | 100% | 100% | 210ms | 1,027ms |
| Contradicts source | 100% | 100% | 217ms | 614ms |
| Right format | 80% | 80% | 192ms | 748ms |

False-alarm rate was 0% for both judges on every check — neither one
wrongly flagged a genuinely good answer.

**This time the test set includes a genuinely hard tier, on purpose.** An
earlier version of this test set was flagged (correctly) as too easy —
wildly unrelated answers and 10x-wrong numbers are simple for any
reasonable judge to catch, so a tie there doesn't prove much. 20 of the
100 cases now are deliberately subtle near-misses instead: a
partially-relevant answer that never actually answers the question, a
transposed digit, a date that's off by a year, a price that's close but
wrong. Broken out separately:

| Check | Difficulty | n | Jev catch rate | Baseline catch rate |
|---|---|---|---|---|
| On-topic | easy | 15 | 100% | 100% |
| On-topic | **hard** | 10 | **100%** | **100%** |
| Contradicts source | easy | 15 | 100% | 100% |
| Contradicts source | **hard** | 10 | **100%** | **100%** |

Both judges held up even on the hard tier. That's a real result, not a
guaranteed one: it was entirely possible Jev caught the easy cases but
missed the subtle ones, and it didn't.

**Is the tie actually meaningful, or just noise?** Ran a bootstrap
confidence interval on the catch-rate gap for each check (5,000
resamples). On-topic and contradiction: observed gap 0%, 95% CI [0%, 0%]
— genuinely identical, not just close. Format: observed gap 0%, 95% CI
[-30%, +30%] — a real tie, but the CI is wide because there are only 10
bad format cases, so don't read too much precision into that one number.
Full numbers from `python -m jev_guard.report`.

Even the misses on the format check are an honest, interesting result:
Jev and the baseline missed *different* tricky near-valid-JSON cases (Jev
missed unquoted keys, the baseline missed a trailing comma; both missed
single-quoted JSON) — not identical blind spots, and not a cherry-picked
result. Spot-checking the live demo afterwards turned up more
format misses (a missing closing brace, a missing comma, and this time
a trailing comma too, all passed as valid JSON), so treat the format
check as a soft signal and use a real parser when you need strict JSON.

**Same accuracy on this test set, including the hard cases, ~3x faster,
every time.**

**One honest caveat:** Jev used *more* input tokens per call than the
baseline (~300 vs. ~65). Jev isn't listed in OpenRouter's public pricing
catalog, so there's no way to independently confirm a $ cost for it —
"faster" is a hard, measured number here; "cheaper" isn't claimed, on
purpose, because it isn't verified.

Raw results from the run: `results/report.json` (gitignored, regenerate
it yourself). Re-run everything, including the chart above, with
`python -m jev_guard.report`.

## Install

```bash
pip install git+https://github.com/omkarchougule19/Jev_validation_agent
```

That installs just the library (its only dependency is `typesafe-sdk`).
Set `OPENROUTER_API_KEY` in your environment and you're ready to call
`guard()`. Both Jev and the baseline judge are reached through
[OpenRouter](https://openrouter.ai), so one API key covers both, with no
TypeSafe-specific account needed.

Optional extras: `[report]` for re-running the benchmark and chart,
`[demo]` for the live demo page, `[dev]` for the tests.

### Working on the repo itself

```bash
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt  # editable install with every extra
cp .env.example .env  # fill in OPENROUTER_API_KEY
python -m pytest
```

## Live demo

A single page where you paste a question, an answer, and optional source
context, and watch Jev-Guard verdict it in real time, with the benchmark
numbers alongside.

```bash
pip install "jev-guard[demo] @ git+https://github.com/omkarchougule19/Jev_validation_agent"
python -m jev_guard.demo  # then open http://localhost:8000
```

To host it, use the included `Dockerfile` (it listens on `$PORT`, 7860 by
default, which suits Hugging Face Spaces or Render) and set
`OPENROUTER_API_KEY` as a secret on the host. A hosted copy spends your
OpenRouter credits, so inputs are capped at 4,000 characters and each IP
gets 10 checks a minute.

## Project layout

```
src/jev_guard/
├── client.py    # thin Jev wrapper (Noul / Choice / Score), via OpenRouter
├── checks.py    # the 3 checks + their pass/flag/block thresholds
├── guard.py     # guard() — runs the checks you ask for, rolls up a verdict
├── baseline.py  # the "ask a full LLM to grade it" comparison judge
├── testset.py   # the 100 made-up test examples (easy + hard tiers)
├── report.py    # runs the test set through both, scores it, charts it
└── demo/        # FastAPI app + single-page UI for the live demo
tests/           # unit tests for the decision logic (no API calls needed)
assets/          # the comparison chart shown above
pyproject.toml   # packaging: pip-installable, with optional extras
Dockerfile       # container for hosting the demo
.github/workflows/tests.yml  # CI: runs the test suite on every push
```

## Why it's built this way

This is deliberately small on purpose: a made-up test set instead of a
real dataset, three checks instead of a plugin framework, one provider
(OpenRouter) instead of several. See `plan.md` for the reasoning behind
the scope.
