"""Jev-Guard: fast, cheap LLM output validation using Jev instead of an LLM judge."""

from jev_guard.checks import CheckResult
from jev_guard.client import make_client
from jev_guard.guard import guard

__all__ = ["CheckResult", "guard", "make_client"]
__version__ = "0.1.0"
