# Build Log

Append-only. Never rewritten — new entries go at the bottom. See `plan.md`
for the build plan and `decisions.md` for the reasoning behind design
choices; this file is just a chronological record of what happened.

---

## 2026-09-22

- Previous project (Jev vs. LLM-judge benchmark on BANKING77) was
  discarded — Groq's daily rate limits turned it into a multi-day
  scheduling problem that wasn't worth it for a portfolio piece. Project
  folder was fully wiped (git history, venv, all files) and started fresh.
- Brainstormed new project ideas using Jev + OpenRouter (no Groq this
  time). Landed on two finalists: a smart LLM router, and an LLM output
  guardrail.
- Spawned an independent critique agent to compare the two. Verdict:
  build the guardrail. Reasoning: the router's hard part (proving it
  routes *correctly*) needs the same kind of ground-truth benchmarking
  that sank the last project; the guardrail lets you manufacture ground
  truth cheaply by injecting known-bad outputs. Also a better fit for
  Jev's actual primitives (yes/no and small-category checks vs. router's
  fuzzier "task complexity" judgment).
- Scoped "Jev-Guard": 3 checks (on-topic via Noul, contradicts-source via
  Score, right-format via Choice), a small guard() function, a baseline
  "ask a full LLM to grade it" comparison judge, and a ~50-100-example
  made-up test set to prove catch rates + show the speed/cost win over the
  baseline.
- User confirmed: keep all 3 checks, ~50-100 test examples, code kept to a
  minimum (no async, no decorator pattern, no plugin framework for v1).
- Wrote `plan.md` (humanized, simple language per user's request) and this
  file's companion `decisions.md`.
- Created scaffold (`src/jev_guard/`, `tests/`, `.gitignore`,
  `.env.example`, `requirements.txt`). Cleaned up `.env`: renamed the
  typo'd `OPENROITER_JEV_API_KEY` to `OPENROUTER_API_KEY` (this project
  uses one OpenRouter key for both Jev and the baseline judge model, so a
  Jev-specific name didn't fit), dropped the unused `GROQ_API_KEY`/
  `HF_TOKEN` from the old project.
- Before writing `client.py`, read the installed `typesafe-sdk` package
  directly (`_schemas/models.py`, `_core/question_types.py`) to confirm
  the `Score` primitive's exact interface rather than guessing — lesson
  from the last project's OpenRouter debugging. Confirmed: `Score(criteria=
  [...])` takes an ordered rubric list, and the response's `.score` is a
  probability-weighted rubric level (not a plain 0-1 value) — a 2-item
  rubric gives a natural 0-1 range, which is what the contradiction check
  needs.
- Wrote `client.py` (thin wrapper for Noul/Choice/Score, via OpenRouter —
  same routing fix as the prior project). Live-tested all three primitives
  immediately: noul=0.99 for an obviously-relevant answer, choice correctly
  picked `valid_json` for actual valid JSON, score=1.0 for a flatly
  contradictory answer. All three working correctly on the first real call.
- Wrote `checks.py` (3 checks + pure verdict-threshold functions),
  `guard.py` (rolls checks up into one overall verdict), `baseline.py` (same
  checks, but judged by a normal LLM via OpenRouter instead of Jev — same
  pure verdict functions applied to both, so it's a fair same-policy,
  different-judge comparison). Live-tested the baseline against
  `openai/gpt-4o-mini` on OpenRouter — works, correct JSON parsing, usage
  tracked (61-71 input tokens, 8-10 output tokens per check).
- Checked OpenRouter's live `/api/v1/models` pricing before writing any
  cost math: `gpt-4o-mini` pricing is public and confirmed ($0.15/M input,
  $0.60/M output). Jev isn't listed there at all — no public per-token
  price to check. Decided to report real measured token counts for both,
  but only compute a $ cost for the baseline where pricing is actually
  confirmed, rather than guess a number for Jev.
- Refactored `client.py`'s `ask_*` functions to return a small `Measurement`
  (value + latency_ms + input_tokens + output_tokens) instead of a bare
  value, once it became clear the report needs latency/cost data alongside
  the check functions already use — confirmed `response.usage.
  input_tokens/output_tokens` exists on live Jev calls before relying on it.
- Wrote `testset.py` (80 made-up examples: 30 on-topic, 30 contradiction,
  20 format, each built to be obviously good or obviously bad on purpose)
  and `report.py` (runs the set through both judges, scores catch-rate /
  false-alarm-rate per check, prints + saves the comparison).
- Wrote `tests/test_checks.py` (10 tests, pure verdict-threshold logic) and
  `tests/test_guard.py` (3 tests, guard()'s worst-verdict-wins aggregation,
  using a mocked client — no API calls needed). All 13 pass.
- Smoke-tested `report.py`'s full pipeline on 6 real cases before running
  the whole set: 6/6 correct on both Jev and the baseline, Jev consistently
  2-4x faster (220-450ms vs. baseline's 560-1370ms).
- Ran the full 80-case report for real. Results: on-topic and contradiction
  both 100% catch / 0% false-alarm for BOTH judges; format check 80% catch
  for both (identical rate, but different misses — Jev missed unquoted
  JSON keys, baseline missed a trailing comma, both missed single-quoted
  JSON). Jev was consistently ~3x faster across all three checks (237-260ms
  vs. baseline's 698-912ms median). Noted honestly: Jev used more input
  tokens per call than the baseline (~300 vs ~65) — since Jev isn't in
  OpenRouter's public pricing list, "faster" is hard-confirmed but
  "cheaper" isn't, and the report doesn't claim it. Raw results saved to
  `results/report.json`.
- Wrote `README.md` with the real pitch, the actual measured comparison
  table, the honest cost caveat, setup instructions, and a pointer back to
  plan/decisions/logs for anyone curious about the build process.
- `git init` + initial commit (root commit `9634dd2`) — clean stage, `.env`
  and `results/` correctly excluded via `.gitignore`. All 13 tests re-run
  and passing right before the commit.
- Sent the finished code to the same critique agent from the idea-selection
  stage (resumed via SendMessage, told explicitly to re-read the actual
  files fresh rather than rely on memory). Findings:
  - Code matches what plan.md/decisions.md/logs.md claim — no discrepancies.
  - **Required fix:** the README's results section didn't carry the
    test-set-difficulty caveat that already existed in `testset.py`'s
    docstring and `decisions.md` — "same accuracy" read as a stronger claim
    than the underlying (deliberately easy) test cases actually support.
  - **Recommended fix:** zero error handling around any API call — a
    timeout/rate-limit/auth blip would crash `guard()` uncaught, a real gap
    for something pitched as a guardrail.
  - Minor: `make_baseline_client()` only checked `OPENROUTER_API_KEY`, not
    the same tolerant fallback `make_client()` uses.
  - Confirmed clean: baseline comparison isn't strawmanned (same
    thresholds, live-checked pricing, honest cost disclosure), scoring math
    in `report.py` is sound.
- Applied all three fixes: added the caveat paragraph to README (pointing
  to the format check as the more informative result, since both judges
  tied there but missed different individual cases); added try/except
  handling in `guard.py` with a documented `on_error="flag"` (default) /
  `"block"` policy — a failed check no longer crashes the whole call or
  stops other checks from running; aligned `make_baseline_client()`'s key
  lookup with `client.py`'s. Added 3 new tests for the error-handling path.
  All 16 tests passing.
- Pushed to GitHub: github.com/omkarchougule19/Jev_validation_agent (branch
  `main`). `gh` CLI wasn't installed locally, so the user created the empty
  repo directly and gave the URL rather than having it created
  automatically.
- User asked to remove Claude as a contributor from commit messages.
  Rewrote all 3 existing commits (git filter-branch, stripped the
  Co-Authored-By trailer) and force-pushed to main — the user confirmed
  this was fine despite already being on GitHub, since they're the only
  one who'd touched the repo. Commit hashes changed (9634dd2/765da26/
  93c9571 -> b8bbe10/7c0b37a/0882dc3). No attribution trailer on commits
  going forward either.