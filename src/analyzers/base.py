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


class AnalysisOutput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    summary: str = Field(min_length=1, max_length=300)


class RetryableAnalysisError(Exception):
    """Temporary technical failure that may succeed on another attempt."""


class PermanentAnalysisError(Exception):
    """Domain or input failure that retrying cannot repair."""


class Analyzer(Protocol):
    def analyze(self, snapshot: AnalysisInputSnapshot) -> AnalysisOutput:
        """Return validated analysis without database or Redis access."""
