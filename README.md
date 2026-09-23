# Jev-Guard

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
from jev_guard.client import make_client
from jev_guard.guard import guard

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

Built a small test set of 80 made-up examples — some answers deliberately
good, some deliberately bad — and ran every one through both Jev-Guard and
a normal "ask an LLM to grade it" baseline (`gpt-4o-mini` via OpenRouter),
scored against the exact same pass/flag/block thresholds for both, so it's
a fair comparison of the *judge*, not the policy.

| Check | Jev catch rate | Baseline catch rate | Jev latency (median) | Baseline latency (median) |
|---|---|---|---|---|
| On-topic | 100% | 100% | 237ms | 698ms |
| Contradicts source | 100% | 100% | 253ms | 912ms |
| Right format | 80% | 80% | 260ms | 783ms |

False-alarm rate was 0% for both judges on every check — neither one
wrongly flagged a genuinely good answer.

**Read the accuracy numbers with this in mind:** the on-topic and
contradiction test cases are deliberately obvious — wildly unrelated
answers, 10x-wrong numbers, wrong cities — not subtle near-misses (a
partially-relevant answer, a detail that's *slightly* off). A 100%/100%
tie on cases this clear-cut mostly shows both judges can catch the easy
stuff; it doesn't prove Jev holds up on harder, more ambiguous calls.
The **format check is the more informative one** here, since JSON syntax
errors range from obvious to genuinely tricky, and it's also the one
check where the two judges' catch rate actually matched *and* their
individual misses differed — a more honest signal than a clean sweep.

**Same accuracy on this test set, ~3x faster, every time.** Even the misses on the format
check are an honest, interesting result: Jev and the baseline missed
*different* tricky near-valid-JSON cases (Jev missed unquoted keys, the
baseline missed a trailing comma; both missed single-quoted JSON) — not
identical blind spots, and not a cherry-picked result.

**One honest caveat:** Jev used *more* input tokens per call than the
baseline (~300 vs. ~65). Jev isn't listed in OpenRouter's public pricing
catalog, so there's no way to independently confirm a $ cost for it —
"faster" is a hard, measured number here; "cheaper" isn't claimed, on
purpose, because it isn't verified.

Raw results from the run: `results/report.json`. Re-run it yourself with
`python -m jev_guard.report`.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env  # fill in OPENROUTER_API_KEY
```

Both Jev and the baseline judge are reached through
[OpenRouter](https://openrouter.ai) — one API key covers both, no
TypeSafe-specific account needed.

## Project layout

```
src/jev_guard/
├── client.py    # thin Jev wrapper (Noul / Choice / Score), via OpenRouter
├── checks.py    # the 3 checks + their pass/flag/block thresholds
├── guard.py     # guard() — runs the checks you ask for, rolls up a verdict
├── baseline.py  # the "ask a full LLM to grade it" comparison judge
├── testset.py   # the 80 made-up test examples
└── report.py    # runs the test set through both, prints the comparison
tests/           # unit tests for the decision logic (no API calls needed)
```

## Why it's built this way

`plan.md`, `decisions.md`, and `logs.md` in this repo track the actual
build process — what was decided, why, and what happened along the way
(including an earlier, more ambitious project that got scrapped over API
rate-limit issues, which is part of why this one is deliberately small:
a made-up test set instead of a real dataset, three checks instead of a
plugin framework, one provider (OpenRouter) instead of several).
