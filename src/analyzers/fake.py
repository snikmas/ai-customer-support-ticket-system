import os
import time
from collections.abc import Callable

from .base import (
    AnalysisInputSnapshot,
    AnalysisOutput,
    PermanentAnalysisError,
    RetryableAnalysisError,
)


MAX_FAKE_DELAY_SECONDS = 10.0
SUPPORTED_FAKE_FAILURE_MODES = {"none", "retryable", "permanent"}


def _normalize_whitespace(value: str) -> str:
    return " ".join(value.split())


def _truncate_at_word_boundary(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value

    prefix = value[: max_length - 3].rstrip()
    if value[max_length - 3] != " " and " " in prefix:
        prefix = prefix.rsplit(" ", 1)[0]
    return f"{prefix.rstrip(' .')}..."


class DeterministicFakeAnalyzer:
    def __init__(
        self,
        *,
        delay_seconds: float = 0,
        failure_mode: str = "none",
        sleeper: Callable[[float], None] = time.sleep,
    ):
        if not 0 <= delay_seconds <= MAX_FAKE_DELAY_SECONDS:
            raise ValueError(
                f"delay_seconds must be between 0 and {MAX_FAKE_DELAY_SECONDS:g}"
            )
        if failure_mode not in SUPPORTED_FAKE_FAILURE_MODES:
            raise ValueError("unsupported fake analyzer failure mode")

        self._delay_seconds = delay_seconds
        self._failure_mode = failure_mode
        self._sleeper = sleeper

    def analyze(self, snapshot: AnalysisInputSnapshot) -> AnalysisOutput:
        if self._delay_seconds:
            self._sleeper(self._delay_seconds)

        if self._failure_mode == "retryable":
            raise RetryableAnalysisError("controlled retryable analyzer failure")
        if self._failure_mode == "permanent":
            raise PermanentAnalysisError("controlled permanent analyzer failure")

        title = _normalize_whitespace(snapshot.title)
        description = _normalize_whitespace(snapshot.description)
        combined = f"{title}: {description}"
        return AnalysisOutput(summary=_truncate_at_word_boundary(combined, 300))


def build_fake_analyzer() -> DeterministicFakeAnalyzer:
    """Build the local analyzer with optional bounded smoke-test controls."""
    raw_delay = os.getenv("FAKE_ANALYZER_DELAY_SECONDS", "0")
    failure_mode = os.getenv("FAKE_ANALYZER_FAILURE_MODE", "none").strip().lower()

    try:
        delay_seconds = float(raw_delay)
    except ValueError as exc:
        raise RuntimeError("FAKE_ANALYZER_DELAY_SECONDS must be numeric") from exc

    try:
        return DeterministicFakeAnalyzer(
            delay_seconds=delay_seconds,
            failure_mode=failure_mode,
        )
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc
