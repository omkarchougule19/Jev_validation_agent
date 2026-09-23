"""Runs the made-up test set through both Jev-Guard and the baseline LLM
judge, and prints a comparison: catch rate (overall and by difficulty),
false-alarm rate, latency, cost (where pricing is actually confirmed), and
a bootstrap confidence interval on whether the catch-rate gap is real or
just noise at this sample size.

Both judges are scored against the exact same pure verdict thresholds from
checks.py, so this is a fair "same decision policy, different judge"
comparison, not a comparison of different thresholds.

Pricing note: gpt-4o-mini's price is public on OpenRouter's own /models
listing ($0.15/M input, $0.60/M output — checked live, not assumed).
Jev isn't listed there at all, so its $ cost below is left unverified
rather than guessed — only token counts are reported for it.
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from dotenv import load_dotenv

from jev_guard.baseline import baseline_contradiction, baseline_format, baseline_on_topic, make_baseline_client
from jev_guard.checks import check_contradiction, check_format, check_on_topic, contradiction_verdict, format_verdict, on_topic_verdict
from jev_guard.client import make_client
from jev_guard.testset import build_testset

BASELINE_PRICE_PER_TOKEN = {"input": 0.00000015, "output": 0.0000006}  # gpt-4o-mini, confirmed live on OpenRouter
OUT_PATH = Path("results/report.json")
CHART_PATH = Path("assets/comparison.png")


def _run_case(jev_client, baseline_client, case: dict) -> dict:
    check = case["check"]
    if check == "on_topic":
        jev = check_on_topic(jev_client, case["question"], case["answer"])
        b = baseline_on_topic(baseline_client, case["question"], case["answer"])
        b_verdict = on_topic_verdict(b.value)
    elif check == "contradiction":
        jev = check_contradiction(jev_client, case["context"], case["answer"])
        b = baseline_contradiction(baseline_client, case["context"], case["answer"])
        b_verdict = contradiction_verdict(b.value)
    else:  # format
        jev = check_format(jev_client, case["answer"], case["expected_format"])
        b = baseline_format(baseline_client, case["answer"], case["expected_format"])
        b_verdict = format_verdict(*b.value)

    b_cost = b.input_tokens * BASELINE_PRICE_PER_TOKEN["input"] + b.output_tokens * BASELINE_PRICE_PER_TOKEN["output"]

    return {
        "check": check,
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
        "baseline_cost_usd": b_cost,
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
    ax1.bar(x + width / 2, base_latency, width, label="Baseline (gpt-4o-mini)", color="#C44E52")
    ax1.set_ylabel("Median latency (ms)")
    ax1.set_title("Latency by check")
    ax1.set_xticks(x)
    ax1.set_xticklabels(labels)
    ax1.legend()

    ax2.bar(x - width / 2, jev_catch, width, label="Jev-Guard", color="#4C72B0")
    ax2.bar(x + width / 2, base_catch, width, label="Baseline (gpt-4o-mini)", color="#C44E52")
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

    print(f"Running {len(testset)} test cases through Jev-Guard and the baseline judge...")
    rows = []
    try:
        for i, case in enumerate(testset, 1):
            rows.append(_run_case(jev_client, baseline_client, case))
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
        base_cost = statistics.mean(r["baseline_cost_usd"] for r in check_rows)

        print(f"\n{check}:")
        print(f"  Jev-Guard : catch={jev_scores['catch_rate']:.0%}  false-alarm={jev_scores['false_alarm_rate']:.0%}  median latency={jev_latency:.0f}ms")
        print(f"  Baseline  : catch={base_scores['catch_rate']:.0%}  false-alarm={base_scores['false_alarm_rate']:.0%}  median latency={base_latency:.0f}ms  avg cost=${base_cost:.6f}/check")

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
