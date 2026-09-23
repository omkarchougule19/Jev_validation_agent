"""The main entry point: guard() runs whichever checks apply and rolls
them up into one overall verdict. Plain function, no async, no decorator —
call it directly around any LLM answer.
"""

from __future__ import annotations

from jev_guard.checks import CheckResult, check_contradiction, check_format, check_on_topic

_SEVERITY = {"pass": 0, "flag": 1, "block": 2}
_CHECK_FNS = {
    "on_topic": lambda client, answer, question, context, expected_format: check_on_topic(client, question, answer),
    "contradiction": lambda client, answer, question, context, expected_format: check_contradiction(client, context, answer),
    "format": lambda client, answer, question, context, expected_format: check_format(client, answer, expected_format),
}


def _error_result(name: str, exc: Exception) -> CheckResult:
    return CheckResult(name, "flag", float("nan"), f"check failed, flagged for review: {type(exc).__name__}: {exc}", 0.0, 0, 0)


def guard(
    client,
    answer: str,
    question: str | None = None,
    context: str | None = None,
    expected_format: str | None = None,
    on_error: str = "flag",
) -> tuple[str, list[CheckResult]]:
    """Runs a check for each optional input that's provided:
    - question  -> on-topic check
    - context   -> contradiction check
    - expected_format -> format check
    Returns (overall_verdict, individual_results). Overall verdict is the
    worst of the individual ones (block > flag > pass).

    Failure policy: if a check's API call raises (timeout, auth error, rate
    limit, etc.), it does NOT propagate and take down the whole guard() call
    — a guardrail that crashes on its own infrastructure hiccup is worse
    than one that degrades gracefully. Default is `on_error="flag"` (the
    failed check doesn't silently pass, but doesn't hard-block either — it
    surfaces for a human to look at). Pass `on_error="block"` for a
    stricter, fail-closed policy if that's the right call for your use case."""
    results: list[CheckResult] = []
    requested = [
        ("on_topic", question is not None),
        ("contradiction", context is not None),
        ("format", expected_format is not None),
    ]

    for name, wanted in requested:
        if not wanted:
            continue
        try:
            results.append(_CHECK_FNS[name](client, answer, question, context, expected_format))
        except Exception as exc:
            result = _error_result(name, exc)
            result.verdict = on_error if on_error in _SEVERITY else "flag"
            results.append(result)

    overall = max((r.verdict for r in results), key=lambda v: _SEVERITY[v], default="pass")
    return overall, results
