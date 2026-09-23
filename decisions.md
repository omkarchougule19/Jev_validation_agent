# Decisions Log

One entry per decision: what was decided, why, and what it replaced. This
file gets reorganized as decisions get superseded — unlike `logs.md`, which
is append-only. See `plan.md` for the current plan these decisions feed
into.

---

## Picked the guardrail idea over the LLM router

**Decided:** build "Jev-Guard" (a fast/cheap LLM-output checker) instead of
a smart model router, after getting an independent critique on both.

**Why:** the router's hard part — proving it *routes well* — needs the same
kind of rigorous, ground-truth benchmarking that made the last project
(Jev vs. an LLM judge on BANKING77) drag on and eventually get scrapped.
The guardrail lets us make up our own ground truth cheaply (write some
known-good and known-bad answers on purpose) instead of needing a real
labeled dataset. It's also a better fit for Jev's actual primitives —
yes/no and small-category checks are exactly what Jev's Choice/Noul were
built for, while "how complex is this prompt" (what a router needs) is a
fuzzier judgment call.

## Three checks, not fewer

**Decided:** keep all three checks (on-topic, contradicts-source, right
format) rather than trimming to two for a leaner v1.

**Why:** the user's call — even though format-checking is the least
"interesting" of the three (it doesn't strictly need an LLM-style judge),
having all three makes the finished tool feel more complete and gives the
comparison table more to show.

## Test set: ~50-100 made-up examples, not a real dataset

**Decided:** build the proof-of-concept test set out of hand/templated
examples (deliberately good and deliberately bad answers), not a scraped
or borrowed labeled dataset.

**Why:** this is the direct fix for what went wrong last time. A real
dataset would mean real API-call volume and possibly rate-limit pain
again. Made-up examples mean the ground truth already exists by
construction — no labeling, no big API bill, no waiting on anyone else's
data.

## No Groq this time — everything through OpenRouter

**Decided:** both Jev and the baseline "ask a full LLM to grade it" judge
go through OpenRouter, not a separate provider.

**Why:** Groq's account-level rate limits (8,000 tokens/minute, ~200
calls/day on the free tier) were the entire reason the last project
turned into a multi-day scheduling problem. OpenRouter access for Jev was
already tested and worked reliably and fast. Using it for the baseline
judge too keeps the whole project on one provider, with one known-working
integration pattern.

## Code stays minimal — no async, no decorator, no plugin framework

**Decided:** `guard()` is a plain synchronous function, checks are plain
Python objects/functions, no `@guarded` decorator, no config-driven "check
builder" framework for v1.

**Why:** user asked explicitly to keep the code to a minimum. Those extra
layers (mentioned as "make it unique" ideas earlier) are real, but they're
v2 material — they'd add real complexity for a first working version that
doesn't need it yet.
