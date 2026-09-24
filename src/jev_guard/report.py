"""Runs the made-up test set through both Jev-Guard and the baseline LLM
judge, and prints a comparison: catch rate (overall and by difficulty),
false-alarm rate, latency, cost (where pricing is actually confirmed), and
a bootstrap confidence interval on whether the catch-rate gap is real or
just noise at this sample size.

Both judges are scored against the exact same pure verdict thresholds from
checks.py, so this is a fair "same decision policy, different judge"
comparison, not a comparison of different thresholds.

The baseline runs on Groq's free tier (see baseline.py), so its $ cost is
zero; the run is paced to stay under Groq's 30 requests / 8,000 tokens per
minute, and waits out any rate-limit response instead of failing. A run
takes a few minutes. Jev's measured cost is about $0.0000124 per check.
"""

from __future__ import annotations

import json
import statistics
import time
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from dotenv import load_dotenv

from jev_guard.baseline import BASELINE_MODEL, BaselineRateLimited, make_baseline_client, run_baseline_case
from jev_guard.checks import run_jev_case
from jev_guard.client import make_client
from jev_guard.testset import build_testset

OUT_PATH = Path("results/report.json")
CHART_PATH = Path("assets/comparison.png")
MIN_SECONDS_PER_BASELINE_CALL = 2.5  # 24/min keeps under Groq's 30 req and 8K tokens per minute


def _baseline_with_wait(client, case: dict):
    while True:
        try:
            return run_baseline_case(client, case)
        except BaselineRateLimited as exc:
            wait = exc.retry_after or 20
            print(f"    Groq rate limit hit, waiting {wait:.0f}s...")
            time.sleep(wait)


def _run_case(jev_client, baseline_client, case: dict) -> dict:
    jev = run_jev_case(jev_client, case)
    b_verdict, b = _baseline_with_wait(baseline_client, case)
    return {
        "check": case["check"],
        "difficulty": case.get("difficulty", "easy"),
        "expected": case["expected"],
        "jev_verdict": jev.verdict,
        "jev_latency_ms": jev.latency_ms,
        "jev_input_tokens": jev.input_tokens,
        "jev_output_tokens": jev.output_tokens,
        "baseline_verdict": b_verdict,
        "baseline_latency_ms": b.latency_ms,
        "baseline_input_tokens": b.input_tokens,
        "baseline_output_tokens": b.output_tokens,
        "baseline_cost_usd": 0.0,  # Groq free tier
        "baseline_model": BASELINE_MODEL,
        "run_date": date.today().isoformat(),
    }


def _score(rows: list[dict], verdict_key: str) -> dict:
    """catch rate = fraction of "block"-expected rows NOT called "pass" (flag counts as caught).
    false-alarm rate = fraction of "pass"-expected rows wrongly called anything but "pass"."""
    bad = [r for r in rows if r["expected"] == "block"]
    good = [r for r in rows if r["expected"] == "pass"]
    catch_rate = sum(1 for r in bad if r[verdict_key] != "pass") / len(bad) if bad else float("nan")
    false_alarm_rate = sum(1 for r in good if r[verdict_key] != "pass") / len(good) if good else float("nan")
    return {"catch_rate": catch_rate, "false_alarm_rate": false_alarm_rate, "n_bad": len(bad), "n_good": len(good)}


def bootstrap_catch_rate_gap_ci(rows: list[dict], n_resamples: int = 5000, ci: float = 0.95, seed: int = 42) -> dict:
    """Paired bootstrap over the "block"-expected rows: is Jev's catch rate
    minus the baseline's catch rate distinguishable from zero, or is a tie
    (or a gap) just noise at this sample size?"""
    bad = [r for r in rows if r["expected"] == "block"]
    jev_caught = np.array([r["jev_verdict"] != "pass" for r in bad], dtype=float)
    base_caught = np.array([r["baseline_verdict"] != "pass" for r in bad], dtype=float)
    n = len(bad)
    if n == 0:
        return {"observed_gap": float("nan"), "ci_low": float("nan"), "ci_high": float("nan"), "significant": False, "n": 0}

    rng = np.random.default_rng(seed)
    gaps = np.empty(n_resamples)
    for i in range(n_resamples):
        idx = rng.integers(0, n, n)
        gaps[i] = jev_caught[idx].mean() - base_caught[idx].mean()

    lo_q, hi_q = (1 - ci) / 2, 1 - (1 - ci) / 2
    lo, hi = np.quantile(gaps, [lo_q, hi_q])
    observed = jev_caught.mean() - base_caught.mean()
    return {"observed_gap": float(observed), "ci_low": float(lo), "ci_high": float(hi), "significant": bool(lo > 0 or hi < 0), "n": n}


def _make_chart(rows: list[dict], out_path: Path) -> None:
    checks = ["on_topic", "contradiction", "format"]
    labels = ["On-topic", "Contradiction", "Format"]
    jev_latency = [statistics.median(r["jev_latency_ms"] for r in rows if r["check"] == c) for c in checks]
    base_latency = [statistics.median(r["baseline_latency_ms"] for r in rows if r["check"] == c) for c in checks]
    jev_catch = [_score([r for r in rows if r["check"] == c], "jev_verdict")["catch_rate"] * 100 for c in checks]
    base_catch = [_score([r for r in rows if r["check"] == c], "baseline_verdict")["catch_rate"] * 100 for c in checks]

    x = np.arange(len(checks))
    width = 0.35

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.5))

    ax1.bar(x - width / 2, jev_latency, width, label="Jev-Guard", color="#4C72B0")
    ax1.bar(x + width / 2, base_latency, width, label=f"Baseline ({BASELINE_MODEL.split('/')[-1]})", color="#C44E52")
    ax1.set_ylabel("Median latency (ms)")
    ax1.set_title("Latency by check")
    ax1.set_xticks(x)
    ax1.set_xticklabels(labels)
    ax1.legend()

    ax2.bar(x - width / 2, jev_catch, width, label="Jev-Guard", color="#4C72B0")
    ax2.bar(x + width / 2, base_catch, width, label=f"Baseline ({BASELINE_MODEL.split('/')[-1]})", color="#C44E52")
    ax2.set_ylabel("Catch rate (%)")
    ax2.set_ylim(0, 105)
    ax2.set_title("Catch rate by check")
    ax2.set_xticks(x)
    ax2.set_xticklabels(labels)
    ax2.legend()

    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def main() -> None:
    load_dotenv()
    testset = build_testset()
    jev_client = make_client()
    baseline_client = make_baseline_client()

    print(f"Running {len(testset)} test cases through Jev-Guard and the baseline judge ({BASELINE_MODEL} on Groq)...")
    rows = []
    try:
        for i, case in enumerate(testset, 1):
            started = time.monotonic()
            rows.append(_run_case(jev_client, baseline_client, case))
            time.sleep(max(0.0, MIN_SECONDS_PER_BASELINE_CALL - (time.monotonic() - started)))
            print(f"  [{i}/{len(testset)}] {case['check']} ({case.get('difficulty', 'easy')}): jev={rows[-1]['jev_verdict']} baseline={rows[-1]['baseline_verdict']} expected={case['expected']}")
    finally:
        jev_client.close()

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2)

    print("\n=== Results by check ===")
    for check in ("on_topic", "contradiction", "format"):
        check_rows = [r for r in rows if r["check"] == check]
        jev_scores = _score(check_rows, "jev_verdict")
        base_scores = _score(check_rows, "baseline_verdict")
        jev_latency = statistics.median(r["jev_latency_ms"] for r in check_rows)
        base_latency = statistics.median(r["baseline_latency_ms"] for r in check_rows)

        print(f"\n{check}:")
        print(f"  Jev-Guard : catch={jev_scores['catch_rate']:.0%}  false-alarm={jev_scores['false_alarm_rate']:.0%}  median latency={jev_latency:.0f}ms")
        print(f"  Baseline  : catch={base_scores['catch_rate']:.0%}  false-alarm={base_scores['false_alarm_rate']:.0%}  median latency={base_latency:.0f}ms")

        for difficulty in ("easy", "hard"):
            diff_rows = [r for r in check_rows if r["difficulty"] == difficulty and r["expected"] == "block"]
            if not diff_rows:
                continue
            jev_d = _score(diff_rows, "jev_verdict")
            base_d = _score(diff_rows, "baseline_verdict")
            print(f"    {difficulty} bad cases (n={jev_d['n_bad']}): Jev catch={jev_d['catch_rate']:.0%}  Baseline catch={base_d['catch_rate']:.0%}")

    print("\n=== Statistical significance (bootstrap, catch rate gap) ===")
    for check in ("on_topic", "contradiction", "format"):
        check_rows = [r for r in rows if r["check"] == check]
        ci = bootstrap_catch_rate_gap_ci(check_rows)
        print(f"  {check}: Jev - Baseline catch rate = {ci['observed_gap']:+.0%}  (95% CI [{ci['ci_low']:+.0%}, {ci['ci_high']:+.0%}])  significant={ci['significant']}")

    _make_chart(rows, CHART_PATH)
    print(f"\nWrote raw results to {OUT_PATH}")
    print(f"Wrote comparison chart to {CHART_PATH}")


if __name__ == "__main__":
    main()
