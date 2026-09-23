"""Runs the made-up test set through both Jev-Guard and the baseline LLM
judge, and prints a comparison: catch rate, false-alarm rate, latency, and
cost (where pricing is actually confirmed — see the note below).

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

from dotenv import load_dotenv

from jev_guard.baseline import baseline_contradiction, baseline_format, baseline_on_topic, make_baseline_client
from jev_guard.checks import check_contradiction, check_format, check_on_topic, contradiction_verdict, format_verdict, on_topic_verdict
from jev_guard.client import make_client
from jev_guard.testset import build_testset

BASELINE_PRICE_PER_TOKEN = {"input": 0.00000015, "output": 0.0000006}  # gpt-4o-mini, confirmed live on OpenRouter
OUT_PATH = Path("results/report.json")


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
    return {"catch_rate": catch_rate, "false_alarm_rate": false_alarm_rate}


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
            print(f"  [{i}/{len(testset)}] {case['check']}: jev={rows[-1]['jev_verdict']} baseline={rows[-1]['baseline_verdict']} expected={case['expected']}")
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

    print(f"\nWrote raw results to {OUT_PATH}")


if __name__ == "__main__":
    main()
