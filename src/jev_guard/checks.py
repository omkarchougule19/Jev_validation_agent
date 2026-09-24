"""The three checks. Each is: one Jev call + a simple threshold turning the
raw number into pass / flag / block. The threshold logic is split into its
own small pure functions so it can be tested without any API calls.
"""

from __future__ import annotations

from dataclasses import dataclass

from jev_guard.client import Measurement, ask_choice, ask_noul, ask_score


@dataclass
class CheckResult:
    name: str
    verdict: str  # "pass" | "flag" | "block"
    raw: float
    detail: str
    latency_ms: float
    input_tokens: int
    output_tokens: int


# --- pure verdict logic (no API calls, easy to unit test) -----------------

def on_topic_verdict(p_relevant: float) -> str:
    if p_relevant >= 0.7:
        return "pass"
    if p_relevant >= 0.4:
        return "flag"
    return "block"


def contradiction_verdict(severity: float) -> str:
    if severity <= 0.3:
        return "pass"
    if severity <= 0.7:
        return "flag"
    return "block"


def format_verdict(label: str, confidence: float) -> str:
    if label != "valid":
        return "block"
    if confidence < 0.6:
        return "flag"
    return "pass"


def _result(name: str, verdict: str, raw: float, detail: str, m: Measurement) -> CheckResult:
    return CheckResult(name, verdict, raw, detail, m.latency_ms, m.input_tokens, m.output_tokens)


# --- checks (one Jev call each) --------------------------------------------

def check_on_topic(client, question: str, answer: str) -> CheckResult:
    state = f"Question: {question}\nAnswer: {answer}"
    m = ask_noul(client, state, "Does the answer actually address the question?")
    return _result("on_topic", on_topic_verdict(m.value), m.value, f"P(on-topic)={m.value:.2f}", m)


def check_contradiction(client, context: str, answer: str) -> CheckResult:
    state = f"Context: {context}\nAnswer: {answer}"
    m = ask_score(
        client, state, "How much does the answer contradict the context?",
        ["fully consistent with the context", "contradicts the context"],
    )
    return _result("contradiction", contradiction_verdict(m.value), m.value, f"contradiction={m.value:.2f}", m)


def run_jev_case(client, case: dict) -> CheckResult:
    """One test-set case (see testset.py) through the matching Jev check."""
    if case["check"] == "on_topic":
        return check_on_topic(client, case["question"], case["answer"])
    if case["check"] == "contradiction":
        return check_contradiction(client, case["context"], case["answer"])
    return check_format(client, case["answer"], case["expected_format"])


def check_format(client, answer: str, expected_format: str) -> CheckResult:
    m = ask_choice(
        client, answer, f"Is this valid {expected_format}?",
        {"valid": f"well-formed {expected_format}", "invalid": f"not valid {expected_format}"},
    )
    label, confidence = m.value
    return _result("format", format_verdict(label, confidence), confidence, f"{label} (confidence={confidence:.2f})", m)
