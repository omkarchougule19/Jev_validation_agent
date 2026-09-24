"""Thin Jev wrapper (Choice / Noul / Score) routed through OpenRouter.

Schema confirmed by reading the installed typesafe-sdk package directly
(typesafe_sdk/_schemas/models.py, _core/question_types.py) rather than
guessing, after getting bitten by wrong assumptions in an earlier project:

  - Noul(instructions=...)               -> response.nouls[key].noul       (float 0-1, P(yes))
  - Choice(instructions=..., criteria={}) -> response.choices[key].choice   (str), .confidence, .probabilities
  - Score(instructions=..., criteria=[])  -> response.scores[key].score    (float, probability-weighted
                                              rubric level — a 2-item criteria list gives a natural 0-1 range)

Every response also carries response.usage.input_tokens/.output_tokens
(confirmed live) — each ask_* function below measures latency and returns
usage alongside the value, since the whole point of this project is
comparing that cost/speed against a normal LLM call (see baseline.py).

Routed through OpenRouter (typesafe/jev-1.13), not TypeSafe's own API
directly — same reason as the discarded prior project: a key from an
unofficial "community" site never authenticated against api.typesafe.ai,
and OpenRouter mirrors the same request/response schema at a different
base_url/model.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Generic, TypeVar

from typesafe_sdk import Choice, Noul, Score, TypeSafeClient

OPENROUTER_BASE_URL = "https://openrouter.ai/api"  # SDK appends /v1/systemone itself
OPENROUTER_MODEL = "typesafe/jev-1.13"
# OpenRouter list price for Jev (checked 2026-09-24): input tokens only, output is free.
PRICE_PER_TOKEN = {"input": 0.042e-6, "output": 0.0}


def cost_usd(input_tokens: int, output_tokens: int) -> float:
    return input_tokens * PRICE_PER_TOKEN["input"] + output_tokens * PRICE_PER_TOKEN["output"]

T = TypeVar("T")


@dataclass
class Measurement(Generic[T]):
    value: T
    latency_ms: float
    input_tokens: int
    output_tokens: int


def make_client() -> TypeSafeClient:
    api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENROUTER_JEV_API_KEY")
    return TypeSafeClient(api_key=api_key, base_url=OPENROUTER_BASE_URL, model=OPENROUTER_MODEL)


def _timed_call(client: TypeSafeClient, state: str, question):
    start = time.perf_counter()
    response = client.system_one(state=state, questions={"q": question})
    latency_ms = (time.perf_counter() - start) * 1000
    return response, latency_ms


def ask_noul(client: TypeSafeClient, state: str, instructions: str) -> Measurement[float]:
    """value = P(yes), 0-1."""
    response, latency_ms = _timed_call(client, state, Noul(instructions=instructions))
    return Measurement(response.nouls["q"].noul, latency_ms, response.usage.input_tokens, response.usage.output_tokens)


def ask_choice(client: TypeSafeClient, state: str, instructions: str, options: dict[str, str | None]) -> Measurement[tuple[str, float]]:
    """value = (chosen_label, confidence)."""
    response, latency_ms = _timed_call(client, state, Choice(instructions=instructions, criteria=options))
    answer = response.choices["q"]
    return Measurement((answer.choice, answer.confidence), latency_ms, response.usage.input_tokens, response.usage.output_tokens)


def ask_score(client: TypeSafeClient, state: str, instructions: str, levels: list[str]) -> Measurement[float]:
    """levels is an ordered rubric, e.g. ["consistent with the source", "contradicts the source"].
    value = the probability-weighted level (0 to len(levels)-1) — a 2-level rubric gives a natural 0-1 range."""
    response, latency_ms = _timed_call(client, state, Score(instructions=instructions, criteria=levels))
    return Measurement(response.scores["q"].score, latency_ms, response.usage.input_tokens, response.usage.output_tokens)
