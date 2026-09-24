import json

import pytest

pytest.importorskip("fastapi")

from jev_guard.baseline import BaselineRateLimited
from jev_guard.demo import race

CASES = [{"check": "on_topic", "difficulty": "easy", "expected": exp, "question": "q", "answer": "a"}
         for exp in ("pass", "block", "pass")]


@pytest.fixture(autouse=True)
def _fresh_state(monkeypatch):
    monkeypatch.setattr(race, "_state", {"busy": False, "next_allowed": 0.0, "day": None, "count": 0})


def _events(jev, groq, cases=CASES, all_cases=None):
    return [json.loads(s.removeprefix("data: ")) for s in race.race_events(jev, groq, cases=cases, all_cases=all_cases)]


def test_race_streams_both_lanes_to_the_end():
    events = _events(lambda c: ("pass", 5.0, 0.00001), lambda c: ("block", 9.0, 0.00001))
    assert events[0]["type"] == "start" and len(events[0]["cases"]) == 3
    assert events[-1]["type"] == "end"
    jev = [e for e in events if e.get("lane") == "jev" and e["type"] == "result"]
    groq = [e for e in events if e.get("lane") == "baseline" and e["type"] == "result"]
    assert [e["correct"] for e in jev] == [True, False, True]
    assert [e["correct"] for e in groq] == [False, True, False]
    assert sum(e["type"] == "lane_done" for e in events) == 2
    assert all(e["cost"] == 0.00001 for e in jev + groq)
    assert events[0]["prices"]["baseline"] == {"input": 0.15, "output": 0.6}


def test_rate_limit_stops_only_the_groq_lane():
    def groq(case):
        raise BaselineRateLimited(30, "429")
    events = _events(lambda c: ("pass", 5.0, 0.00001), groq)
    assert {"type": "limit", "lane": "baseline", "retry_after": 30} in events
    assert any(e["type"] == "lane_done" and e["lane"] == "jev" for e in events)
    assert events[-1]["type"] == "end"


def test_provider_error_is_reported_not_raised():
    def jev(case):
        raise RuntimeError("402")
    events = _events(jev, lambda c: ("pass", 5.0, 0.00001))
    assert any(e["type"] == "error" and e["lane"] == "jev" for e in events)


def test_second_race_within_a_minute_is_blocked():
    _events(lambda c: ("pass", 1.0, 0.00001), lambda c: ("pass", 1.0, 0.00001))
    events = _events(lambda c: ("pass", 1.0, 0.00001), lambda c: ("pass", 1.0, 0.00001))
    assert events == [{"type": "blocked", "reason": "busy", "retry_in": events[0]["retry_in"]}]


def test_daily_cap_blocks_with_limit_reason(monkeypatch):
    monkeypatch.setattr(race, "DAILY_CAP", 0)
    assert _events(lambda c: ("pass", 1.0, 0.00001), lambda c: ("pass", 1.0, 0.00001)) == [{"type": "blocked", "reason": "limit"}]


def test_random_race_picks_race_size_cases():
    pool = CASES * 20
    events = _events(lambda c: ("pass", 1.0, 0.00001), lambda c: ("pass", 1.0, 0.00001), cases=None) if False else \
        [json.loads(s.removeprefix("data: ")) for s in race.race_events(lambda c: ("pass", 1.0, 0.00001), lambda c: ("pass", 1.0, 0.00001), all_cases=pool)]
    assert len(events[0]["cases"]) == race.RACE_SIZE
