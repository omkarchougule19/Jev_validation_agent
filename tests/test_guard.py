import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jev_guard.client import Measurement
from jev_guard.guard import guard

_M = lambda value: Measurement(value, latency_ms=1.0, input_tokens=1, output_tokens=1)


def test_guard_all_pass():
    with patch("jev_guard.checks.ask_noul", return_value=_M(0.95)), \
         patch("jev_guard.checks.ask_score", return_value=_M(0.0)):
        overall, results = guard(None, "answer", question="q", context="c")
    assert overall == "pass"
    assert len(results) == 2


def test_guard_worst_verdict_wins():
    with patch("jev_guard.checks.ask_noul", return_value=_M(0.95)), \
         patch("jev_guard.checks.ask_score", return_value=_M(1.0)):  # contradiction -> block
        overall, results = guard(None, "answer", question="q", context="c")
    assert overall == "block"


def test_guard_only_runs_requested_checks():
    with patch("jev_guard.checks.ask_noul", return_value=_M(0.95)):
        overall, results = guard(None, "answer", question="q")
    assert len(results) == 1
    assert results[0].name == "on_topic"


def test_guard_does_not_crash_on_api_error():
    with patch("jev_guard.checks.ask_noul", side_effect=TimeoutError("boom")):
        overall, results = guard(None, "answer", question="q")
    assert overall == "flag"  # default on_error policy
    assert "boom" in results[0].detail


def test_guard_on_error_can_be_set_to_block():
    with patch("jev_guard.checks.ask_noul", side_effect=TimeoutError("boom")):
        overall, results = guard(None, "answer", question="q", on_error="block")
    assert overall == "block"


def test_guard_one_failing_check_does_not_stop_others():
    with patch("jev_guard.checks.ask_noul", side_effect=TimeoutError("boom")), \
         patch("jev_guard.checks.ask_score", return_value=_M(0.0)):
        overall, results = guard(None, "answer", question="q", context="c")
    assert len(results) == 2
    names = {r.name for r in results}
    assert names == {"on_topic", "contradiction"}
