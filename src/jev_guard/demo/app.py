"""Live demo: a single page where you paste a question / answer / context
and watch guard() verdict it. One POST endpoint, no database.

Run locally:  python -m jev_guard.demo   (then open http://localhost:8000)

Since a hosted copy spends the host's OpenRouter credits, inputs are
length-capped and each IP gets a small per-minute request budget.
"""

from __future__ import annotations

import math
import time
from collections import defaultdict, deque
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from jev_guard.baseline import make_baseline_client, run_baseline_case
from jev_guard.checks import run_jev_case
from jev_guard.client import make_client
from jev_guard.demo.race import race_events
from jev_guard.guard import guard
from jev_guard.testset import build_testset

MAX_CHARS = 4000
RATE_LIMIT = 10  # requests per IP per minute

load_dotenv()
app = FastAPI(title="Jev-Guard demo")
_client = None
_hits: dict[str, deque] = defaultdict(deque)
_STATIC = Path(__file__).parent / "static"


class GuardRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=MAX_CHARS)
    question: str | None = Field(default=None, max_length=MAX_CHARS)
    context: str | None = Field(default=None, max_length=MAX_CHARS)
    expected_format: str | None = Field(default=None, max_length=100)


def _rate_limited(ip: str) -> bool:
    now = time.monotonic()
    hits = _hits[ip]
    while hits and now - hits[0] > 60:
        hits.popleft()
    if len(hits) >= RATE_LIMIT:
        return True
    hits.append(now)
    return False


def _get_client():
    global _client
    if _client is None:
        _client = make_client()
    return _client


@app.get("/")
def index():
    return FileResponse(_STATIC / "index.html")


@app.get("/race")
def race_page():
    return FileResponse(_STATIC / "race.html")


@app.get("/api/race")
def race():
    """Streams one live race (see race.py). Each lane gets its own client,
    since the race runs both lanes on separate threads."""
    jev_client, groq_client = make_client(), make_baseline_client()

    def jev_judge(case):
        result = run_jev_case(jev_client, case)
        return result.verdict, result.latency_ms

    def groq_judge(case):
        verdict, call = run_baseline_case(groq_client, case)
        return verdict, call.latency_ms

    def stream():
        try:
            yield from race_events(jev_judge, groq_judge, all_cases=build_testset())
        finally:
            jev_client.close()

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/guard")
def run_guard(req: GuardRequest, request: Request):
    if _rate_limited(request.client.host if request.client else "unknown"):
        raise HTTPException(429, f"Rate limit: {RATE_LIMIT} checks per minute. Try again shortly.")

    # Blank optional fields mean "skip that check", same as passing None.
    optional = {k: (v.strip() or None) if v else None for k, v in
                {"question": req.question, "context": req.context, "expected_format": req.expected_format}.items()}
    if not any(optional.values()):
        raise HTTPException(422, "Fill in at least one of question, context, or expected format.")

    start = time.perf_counter()
    overall, results = guard(_get_client(), req.answer, **optional)
    return {
        "overall": overall,
        "total_ms": round((time.perf_counter() - start) * 1000),
        "results": [
            {
                "name": r.name,
                "verdict": r.verdict,
                "raw": None if math.isnan(r.raw) else round(r.raw, 3),
                "detail": r.detail,
                "latency_ms": round(r.latency_ms),
            }
            for r in results
        ],
    }
