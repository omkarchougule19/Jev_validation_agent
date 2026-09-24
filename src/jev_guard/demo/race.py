"""The live race: Jev and the Groq-hosted baseline judge each check the same
randomly picked 25 test cases, one call at a time, side by side. Results
stream to the browser as Server-Sent Events as each call finishes.

Why 25: Groq's free tier allows 30 requests per minute, so one race fits
in a single minute's allowance. Races run one at a time, at least a minute
apart, and a small daily cap (RACE_DAILY_CAP) backs up Groq's own daily
limit. When a limit is hit, the page is told so it can say why.
"""

from __future__ import annotations

import json
import os
import queue
import random
import threading
import time
from datetime import date

from jev_guard import baseline, client
from jev_guard.baseline import BASELINE_MODEL, BaselineRateLimited

RACE_SIZE = 25
MIN_GAP_S = 65  # a fresh Groq per-minute window for every race
DAILY_CAP = int(os.environ.get("RACE_DAILY_CAP", 10))

_lock = threading.Lock()
_state = {"busy": False, "next_allowed": 0.0, "day": None, "count": 0}


def jev_prices() -> dict:
    return {k: v * 1e6 for k, v in client.PRICE_PER_TOKEN.items()}  # $ per 1M tokens


def baseline_prices() -> dict:
    return {k: v * 1e6 for k, v in baseline.PRICE_PER_TOKEN.items()}


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


def _reserve_slot() -> dict | None:
    """Claims the single race slot, or returns the event explaining why not."""
    with _lock:
        today = date.today().isoformat()
        if _state["day"] != today:
            _state.update(day=today, count=0)
        if _state["count"] >= DAILY_CAP:
            return {"type": "blocked", "reason": "limit"}
        wait = _state["next_allowed"] - time.monotonic()
        if _state["busy"] or wait > 0:
            return {"type": "blocked", "reason": "busy", "retry_in": max(5, round(wait))}
        _state.update(busy=True, count=_state["count"] + 1)
        return None


def _release_slot(cooldown_s: float = MIN_GAP_S) -> None:
    with _lock:
        _state.update(busy=False, next_allowed=time.monotonic() + cooldown_s)


def _case_summary(case: dict) -> dict:
    given = case.get("question") or case.get("context") or f"Must be valid {case.get('expected_format', '')}"
    return {"check": case["check"], "difficulty": case["difficulty"], "expected": case["expected"],
            "given": given[:160], "answer": case["answer"][:160]}


def _run_lane(name: str, judge, cases: list[dict], out: queue.Queue) -> None:
    start = time.perf_counter()
    for i, case in enumerate(cases):
        try:
            verdict, latency_ms, cost = judge(case)
        except BaselineRateLimited as exc:
            out.put({"type": "limit", "lane": name, "retry_after": exc.retry_after})
            return
        except Exception as exc:  # noqa: BLE001 - any provider failure ends this lane, not the race
            out.put({"type": "error", "lane": name, "message": f"{type(exc).__name__}"})
            return
        out.put({"type": "result", "lane": name, "i": i, "verdict": verdict,
                 "correct": (verdict == "pass") == (case["expected"] == "pass"),
                 "ms": round(latency_ms), "cost": cost, "elapsed_ms": round((time.perf_counter() - start) * 1000)})
    out.put({"type": "lane_done", "lane": name, "elapsed_ms": round((time.perf_counter() - start) * 1000)})


def race_events(jev_judge, groq_judge, cases: list[dict] | None = None, all_cases: list[dict] | None = None):
    """Generator of SSE strings. Judges take a test case and return
    (verdict, latency_ms, cost_usd); they're passed in so tests can use fakes."""
    blocked = _reserve_slot()
    if blocked:
        yield _sse(blocked)
        return

    cooldown = MIN_GAP_S
    try:
        if cases is None:
            cases = random.sample(all_cases, RACE_SIZE)
        yield _sse({"type": "start", "baseline_model": BASELINE_MODEL, "cases": [_case_summary(c) for c in cases],
                    "prices": {"jev": jev_prices(), "baseline": baseline_prices()}})

        out: queue.Queue = queue.Queue()
        for name, judge in (("jev", jev_judge), ("baseline", groq_judge)):
            threading.Thread(target=_run_lane, args=(name, judge, cases, out), daemon=True).start()

        lanes_open = 2
        while lanes_open:
            try:
                event = out.get(timeout=30)
            except queue.Empty:
                yield _sse({"type": "error", "lane": "both", "message": "timed out"})
                break
            if event["type"] == "limit" and event.get("retry_after"):
                cooldown = max(cooldown, event["retry_after"])
            if event["type"] in ("lane_done", "limit", "error"):
                lanes_open -= 1
            yield _sse(event)
        yield _sse({"type": "end"})
    finally:
        _release_slot(cooldown)
