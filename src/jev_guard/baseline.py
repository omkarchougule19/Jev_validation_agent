"""The comparison point: the same three checks, but answered by asking a
normal LLM to judge instead of using Jev's decision primitives. This is how
most guardrail tools work today.

The judge is OpenAI's open-weight gpt-oss-120b, served by Groq on its free
tier (earlier runs used gpt-4o-mini via OpenRouter). Reasoning is set to
"low", the minimum gpt-oss allows, since these are simple decisions.

Returns the same *raw* values as jev_guard.client's ask_noul/ask_score/
ask_choice, so both judges go through the exact same verdict thresholds
from checks.py: a fair comparison of the judge, not of different policies.

Groq's free tier allows 30 requests and 8,000 tokens per minute. A 429 (or
a 413 "tokens per minute" rejection) is raised as BaselineRateLimited
instead of retried, so callers decide whether to wait or give up.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass

from openai import APIStatusError, OpenAI

from jev_guard.checks import contradiction_verdict, format_verdict, on_topic_verdict

BASELINE_MODEL = os.environ.get("BASELINE_MODEL", "openai/gpt-oss-120b")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
MAX_COMPLETION_TOKENS = 150  # Groq reserves prompt + this against the per-minute token limit


class BaselineRateLimited(Exception):
    def __init__(self, retry_after: float | None, message: str):
        super().__init__(message)
        self.retry_after = retry_after


@dataclass
class BaselineCall:
    value: float | tuple[str, float]
    latency_ms: float
    input_tokens: int
    output_tokens: int


def make_baseline_client() -> OpenAI:
    return OpenAI(api_key=os.environ.get("GROQ_API_KEY"), base_url=GROQ_BASE_URL, max_retries=0, timeout=15)


def _ask_json(client: OpenAI, prompt: str) -> tuple[dict, float, int, int]:
    start = time.perf_counter()
    try:
        response = client.chat.completions.create(
            model=BASELINE_MODEL,
            messages=[{"role": "user", "content": prompt + "\n\nRespond with ONLY a JSON object, no other text."}],
            response_format={"type": "json_object"},
            temperature=0,
            max_completion_tokens=MAX_COMPLETION_TOKENS,
            reasoning_effort="low",
            extra_body={"include_reasoning": False},
        )
    except APIStatusError as exc:
        if exc.status_code in (413, 429):
            retry_after = exc.response.headers.get("retry-after")
            raise BaselineRateLimited(float(retry_after) if retry_after else None, str(exc)) from exc
        raise
    latency_ms = (time.perf_counter() - start) * 1000
    text = (response.choices[0].message.content or "").strip().removeprefix("```json").removeprefix("```").removesuffix("```")
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


def run_baseline_case(client: OpenAI, case: dict) -> tuple[str, BaselineCall]:
    """One test-set case through the baseline judge -> (verdict, call)."""
    if case["check"] == "on_topic":
        b = baseline_on_topic(client, case["question"], case["answer"])
        return on_topic_verdict(b.value), b
    if case["check"] == "contradiction":
        b = baseline_contradiction(client, case["context"], case["answer"])
        return contradiction_verdict(b.value), b
    b = baseline_format(client, case["answer"], case["expected_format"])
    return format_verdict(*b.value), b
