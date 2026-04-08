"""Pydantic models for code review verdicts and issues."""

from pydantic import Field

from foundry.contracts.shared import (
    FoundryBaseModel,
    ReviewSeverity,
    ReviewVerdictType,
)


class ReviewIssue(FoundryBaseModel):
    """A single issue found during code review."""

    severity: ReviewSeverity
    file_path: str
    line_range: str | None = None
    description: str
    suggestion: str | None = None


class ReviewVerdict(FoundryBaseModel):
    """The complete review verdict for a diff."""

    verdict: ReviewVerdictType
    issues: list[ReviewIssue]
    summary: str
    confidence: float = Field(ge=0.0, le=1.0)
