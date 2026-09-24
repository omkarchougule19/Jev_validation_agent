from unittest.mock import patch

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from jev_guard.checks import CheckResult
from jev_guard.demo import app as demo

client = TestClient(demo.app)


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    demo._hits.clear()


def _fake_guard(results):
    return patch.object(demo, "guard", return_value=("flag", results)), patch.object(demo, "_get_client")


def test_index_serves_page():
    res = client.get("/")
    assert res.status_code == 200
    assert "Jev-Guard" in res.text


def test_guard_endpoint_returns_verdicts():
    results = [CheckResult("on_topic", "flag", 0.5, "P(on-topic)=0.50", 12.3, 1, 1)]
    g, c = _fake_guard(results)
    with g as mock_guard, c:
        res = client.post("/api/guard", json={"answer": "a", "question": "q", "context": "  "})
    assert res.status_code == 200
    assert res.json()["overall"] == "flag"
    assert res.json()["results"][0]["raw"] == 0.5
    # blank context is treated as "skip that check"
    assert mock_guard.call_args.kwargs["context"] is None


def test_failed_check_nan_serializes_as_null():
    results = [CheckResult("on_topic", "flag", float("nan"), "check failed", 0.0, 0, 0)]
    g, c = _fake_guard(results)
    with g, c:
        res = client.post("/api/guard", json={"answer": "a", "question": "q"})
    assert res.status_code == 200
    assert res.json()["results"][0]["raw"] is None


def test_requires_at_least_one_check_input():
    res = client.post("/api/guard", json={"answer": "a", "question": ""})
    assert res.status_code == 422


def test_rejects_oversized_input():
    res = client.post("/api/guard", json={"answer": "x" * (demo.MAX_CHARS + 1), "question": "q"})
    assert res.status_code == 422


def test_rate_limit():
    g, c = _fake_guard([])
    with g, c:
        codes = [client.post("/api/guard", json={"answer": "a", "question": "q"}).status_code
                 for _ in range(demo.RATE_LIMIT + 1)]
    assert codes[-1] == 429
    assert all(code == 200 for code in codes[:-1])
