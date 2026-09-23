"""The comparison point: the same three checks, but answered by asking a
normal LLM (via OpenRouter) to judge in a sentence or two instead of using
Jev's decision primitives. This is how most guardrail tools work today —
slower and pricier than Jev because you're paying for a full chat model to
answer what's really just a yes/no or pick-one question.

Returns the same *raw* values as jev_guard.client's ask_noul/ask_score/
ask_choice, so report.py can run both through the exact same verdict
thresholds from checks.py — a fair, apples-to-apples comparison of the
judge, not of different decision policies.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass

from openai import OpenAI

BASELINE_MODEL = "openai/gpt-4o-mini"


@dataclass
class BaselineCall:
    value: float | tuple[str, float]
    latency_ms: float
    input_tokens: int
    output_tokens: int


def make_baseline_client() -> OpenAI:
    api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENROUTER_JEV_API_KEY")
    return OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")


def _ask_json(client: OpenAI, prompt: str) -> tuple[dict, float, int, int]:
    start = time.perf_counter()
    response = client.chat.completions.create(
        model=BASELINE_MODEL,
        messages=[{"role": "user", "content": prompt + "\n\nRespond with ONLY a JSON object, no other text."}],
    )
    latency_ms = (time.perf_counter() - start) * 1000
    text = response.choices[0].message.content.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = {}  # caller applies a safe default
    usage = response.usage
    return parsed, latency_ms, usage.prompt_tokens, usage.completion_tokens


def baseline_on_topic(client: OpenAI, question: str, answer: str) -> BaselineCall:
    prompt = f'Question: {question}\nAnswer: {answer}\n\nHow likely does the answer address the question? Respond as {{"p_relevant": <float 0 to 1>}}.'
    parsed, latency_ms, in_tok, out_tok = _ask_json(client, prompt)
    return BaselineCall(float(parsed.get("p_relevant", 0.5)), latency_ms, in_tok, out_tok)


def baseline_contradiction(client: OpenAI, context: str, answer: str) -> BaselineCall:
    prompt = f'Context: {context}\nAnswer: {answer}\n\nHow much does the answer contradict the context? Respond as {{"severity": <float 0 to 1>}}, where 0 is fully consistent and 1 is a flat contradiction.'
    parsed, latency_ms, in_tok, out_tok = _ask_json(client, prompt)
    return BaselineCall(float(parsed.get("severity", 0.5)), latency_ms, in_tok, out_tok)


def baseline_format(client: OpenAI, answer: str, expected_format: str) -> BaselineCall:
    prompt = f'Text: {answer}\n\nIs this valid {expected_format}? Respond as {{"label": "valid" or "invalid", "confidence": <float 0 to 1>}}.'
    parsed, latency_ms, in_tok, out_tok = _ask_json(client, prompt)
    label = parsed.get("label", "invalid")
    confidence = float(parsed.get("confidence", 0.5))
    return BaselineCall((label, confidence), latency_ms, in_tok, out_tok)
