"""The main entry point: guard() runs whichever checks apply and rolls
them up into one overall verdict. Plain function, no async, no decorator —
call it directly around any LLM answer.
"""

from __future__ import annotations

from jev_guard.checks import CheckResult, check_contradiction, check_format, check_on_topic

_SEVERITY = {"pass": 0, "flag": 1, "block": 2}


def guard(
    client,
    answer: str,
    question: str | None = None,
    context: str | None = None,
    expected_format: str | None = None,
) -> tuple[str, list[CheckResult]]:
    """Runs a check for each optional input that's provided:
    - question  -> on-topic check
    - context   -> contradiction check
    - expected_format -> format check
    Returns (overall_verdict, individual_results). Overall verdict is the
    worst of the individual ones (block > flag > pass)."""
    results: list[CheckResult] = []

    if question is not None:
        results.append(check_on_topic(client, question, answer))
    if context is not None:
        results.append(check_contradiction(client, context, answer))
    if expected_format is not None:
        results.append(check_format(client, answer, expected_format))

    overall = max((r.verdict for r in results), key=lambda v: _SEVERITY[v], default="pass")
    return overall, results
