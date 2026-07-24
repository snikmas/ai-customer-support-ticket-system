from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from src.constants import Category, Priority, Status, Tag


class AnalysisInputSnapshot(BaseModel):
    """Immutable request-time input shared by fake and future LLM analyzers."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=32000)
    category: Category
    tags: tuple[Tag, ...] = Field(default_factory=tuple, max_length=10)
    priority: Priority
    status: Status
    public_comments: tuple[str, ...] = Field(default_factory=tuple, max_length=10)


class AnalysisOutput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    summary: str = Field(min_length=1, max_length=300)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)


class RetryableAnalysisError(Exception):
    """Temporary technical failure that may succeed on another attempt."""

    def __init__(
        self,
        message: str = "Analysis provider temporarily unavailable",
        *,
        code: str = "provider_unavailable",
        safe_message: str | None = None,
    ):
        self.code = code
        self.safe_message = safe_message or "Analysis provider temporarily unavailable"
        super().__init__(message)


class PermanentAnalysisError(Exception):
    """Domain or input failure that retrying cannot repair."""

    def __init__(
        self,
        message: str = "Analysis provider rejected the request",
        *,
        code: str = "provider_bad_request",
        safe_message: str | None = None,
    ):
        self.code = code
        self.safe_message = safe_message or "Analysis provider rejected the request"
        super().__init__(message)


class Analyzer(Protocol):
    def analyze(self, snapshot: AnalysisInputSnapshot) -> AnalysisOutput:
        """Return validated analysis without database or Redis access."""
