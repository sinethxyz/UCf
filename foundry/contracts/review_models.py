"""Pydantic models for code review verdicts and issues."""

from pydantic import Field

from foundry.contracts.shared import (
    FoundryBaseModel,
    ReviewVerdictType,
    Severity,
)


class ReviewIssue(FoundryBaseModel):
    """A single issue found during code review.

    The reviewer subagent produces these for each problem it identifies
    in a diff. Issues are classified by severity and optionally include
    a suggested fix.
    """

    severity: Severity = Field(description="How important this issue is.")
    file_path: str = Field(description="Path to the file containing the issue.")
    line_range: str | None = Field(
        default=None,
        description="Line range affected, e.g. '15-20' or '42'.",
    )
    description: str = Field(description="What the issue is and why it matters.")
    suggestion: str | None = Field(
        default=None,
        description="Suggested fix or improvement, if applicable.",
    )


class ReviewVerdict(FoundryBaseModel):
    """The complete review verdict for a diff.

    Produced by the reviewer subagent after independently evaluating
    a diff. The verdict is advisory — a human must confirm before merge.
    """

    verdict: ReviewVerdictType = Field(
        description="Overall review outcome: approve, request_changes, or reject."
    )
    issues: list[ReviewIssue] = Field(
        default_factory=list,
        description="All issues found during review.",
    )
    summary: str = Field(
        description="High-level summary of the review findings."
    )
