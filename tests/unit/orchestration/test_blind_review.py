"""Tests for blind diff review.

Verifies:
1. The plan is NEVER included in the reviewer's context.
2. ReviewVerdict structured output is parsed and validated correctly.
3. Issues are classified by severity.
4. Changed files are forwarded to the reviewer.
5. Model routing resolves to Opus for review tasks.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from foundry.contracts.review_models import ReviewIssue, ReviewVerdict
from foundry.contracts.shared import (
    MCPProfile,
    ReviewSeverity,
    ReviewVerdictType,
    TaskType,
)
from foundry.contracts.task_types import TaskRequest
from foundry.orchestration.agent_runner import AgentRunner, REVIEWER_TOOLS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


SAMPLE_DIFF = """\
diff --git a/services/api/search/handler.go b/services/api/search/handler.go
index abc1234..def5678 100644
--- a/services/api/search/handler.go
+++ b/services/api/search/handler.go
@@ -42,7 +42,7 @@ func (h *SearchHandler) Search(w http.ResponseWriter, r *http.Request) {
-    offset := (page - 1) * pageSize
+    offset := page * pageSize
     results, err := h.store.Search(ctx, query, offset, pageSize)
"""

SAMPLE_DIFF_MULTI = """\
diff --git a/services/api/search/handler.go b/services/api/search/handler.go
index abc1234..def5678 100644
--- a/services/api/search/handler.go
+++ b/services/api/search/handler.go
@@ -42,7 +42,7 @@
-    offset := (page - 1) * pageSize
+    offset := page * pageSize
diff --git a/services/api/search/handler_test.go b/services/api/search/handler_test.go
index 1111111..2222222 100644
--- a/services/api/search/handler_test.go
+++ b/services/api/search/handler_test.go
@@ -10,6 +10,15 @@
+func TestSearch_Pagination(t *testing.T) {
+    // regression test
+}
"""


@pytest.fixture
def sample_verdict() -> ReviewVerdict:
    return ReviewVerdict(
        verdict=ReviewVerdictType.REQUEST_CHANGES,
        issues=[
            ReviewIssue(
                severity=ReviewSeverity.CRITICAL,
                file_path="services/api/search/handler.go",
                line_range="42-42",
                description="Off-by-one: offset calculation skips first page of results",
                suggestion="Use (page - 1) * pageSize instead of page * pageSize",
            ),
            ReviewIssue(
                severity=ReviewSeverity.MAJOR,
                file_path="services/api/search/handler.go",
                line_range="45-50",
                description="Missing bounds check on page parameter",
                suggestion="Validate page >= 1 before computing offset",
            ),
            ReviewIssue(
                severity=ReviewSeverity.MINOR,
                file_path="services/api/search/handler_test.go",
                line_range="10-12",
                description="Test body is empty",
            ),
            ReviewIssue(
                severity=ReviewSeverity.NIT,
                file_path="services/api/search/handler.go",
                line_range=None,
                description="Consider adding a constant for default page size",
            ),
        ],
        summary="The pagination offset calculation is incorrect and will skip the first page.",
        confidence=0.95,
    )


@pytest.fixture
def approve_verdict() -> ReviewVerdict:
    return ReviewVerdict(
        verdict=ReviewVerdictType.APPROVE,
        issues=[],
        summary="Clean change, no issues found.",
        confidence=0.9,
    )


@pytest.fixture
def runner() -> AgentRunner:
    return AgentRunner(api_key="test-key")


# ---------------------------------------------------------------------------
# Plan exclusion tests — the reviewer must NEVER see the plan
# ---------------------------------------------------------------------------


class TestPlanExclusion:
    """Verify the plan is never passed to the reviewer subagent."""

    async def test_reviewer_context_does_not_contain_plan(
        self, runner: AgentRunner, sample_verdict: ReviewVerdict
    ):
        """The user message sent to the reviewer must not contain plan data."""
        runner.provider = MagicMock()
        runner.provider.run_with_structured_output = AsyncMock(return_value={
            "response": sample_verdict,
            "model": "claude-opus-4-6",
            "tokens_in": 500,
            "tokens_out": 200,
            "duration_ms": 3000,
        })

        await runner.run_reviewer(
            diff=SAMPLE_DIFF,
            pr_title="Fix pagination",
            pr_description="Fix off-by-one in search pagination",
        )

        call_kwargs = runner.provider.run_with_structured_output.call_args.kwargs
        user_msg = call_kwargs["user_message"]
        system_prompt = call_kwargs["system_prompt"]

        # Plan-related terms must not appear in reviewer context
        for forbidden in ["PlanArtifact", "plan_json", "steps", "rationale", "dependencies"]:
            assert forbidden not in user_msg, (
                f"Reviewer user message must not contain plan term '{forbidden}'"
            )

        # System prompt must mention independent review
        assert "without access to the original plan" in system_prompt.lower() or \
               "WITHOUT access to the original plan" in system_prompt

    async def test_reviewer_system_prompt_enforces_independence(
        self, runner: AgentRunner, sample_verdict: ReviewVerdict
    ):
        """The reviewer system prompt must state it reviews without the plan."""
        runner.provider = MagicMock()
        runner.provider.run_with_structured_output = AsyncMock(return_value={
            "response": sample_verdict,
            "model": "claude-opus-4-6",
            "tokens_in": 100,
            "tokens_out": 50,
            "duration_ms": 1000,
        })

        await runner.run_reviewer(
            diff=SAMPLE_DIFF,
            pr_title="Fix pagination",
            pr_description="Fix off-by-one",
        )

        call_kwargs = runner.provider.run_with_structured_output.call_args.kwargs
        system_prompt = call_kwargs["system_prompt"]
        assert "WITHOUT access to the original plan" in system_prompt

    async def test_reviewer_receives_no_tools(
        self, runner: AgentRunner, sample_verdict: ReviewVerdict
    ):
        """The reviewer must have no tools — it judges the diff only."""
        runner.provider = MagicMock()
        runner.provider.run_with_structured_output = AsyncMock(return_value={
            "response": sample_verdict,
            "model": "claude-opus-4-6",
            "tokens_in": 100,
            "tokens_out": 50,
            "duration_ms": 1000,
        })

        await runner.run_reviewer(
            diff=SAMPLE_DIFF,
            pr_title="Fix pagination",
            pr_description="Fix off-by-one",
        )

        call_kwargs = runner.provider.run_with_structured_output.call_args.kwargs
        # REVIEWER_TOOLS is [], passed as None to provider
        assert call_kwargs["tools"] is None

    async def test_reviewer_only_sees_diff_title_description(
        self, runner: AgentRunner, sample_verdict: ReviewVerdict
    ):
        """The reviewer user message must contain only diff, title, and description."""
        runner.provider = MagicMock()
        runner.provider.run_with_structured_output = AsyncMock(return_value={
            "response": sample_verdict,
            "model": "claude-opus-4-6",
            "tokens_in": 100,
            "tokens_out": 50,
            "duration_ms": 1000,
        })

        title = "Fix pagination bug"
        description = "Fix the off-by-one error in search"

        await runner.run_reviewer(
            diff=SAMPLE_DIFF,
            pr_title=title,
            pr_description=description,
        )

        call_kwargs = runner.provider.run_with_structured_output.call_args.kwargs
        user_msg = call_kwargs["user_message"]

        assert title in user_msg
        assert description in user_msg
        assert "offset := page * pageSize" in user_msg  # from the diff


# ---------------------------------------------------------------------------
# Structured verdict parsing tests
# ---------------------------------------------------------------------------


class TestVerdictParsing:
    """Verify ReviewVerdict parsing and validation."""

    async def test_returns_review_verdict_instance(
        self, runner: AgentRunner, sample_verdict: ReviewVerdict
    ):
        """run_reviewer returns a ReviewVerdict Pydantic model."""
        runner.provider = MagicMock()
        runner.provider.run_with_structured_output = AsyncMock(return_value={
            "response": sample_verdict,
            "model": "claude-opus-4-6",
            "tokens_in": 100,
            "tokens_out": 50,
            "duration_ms": 1000,
        })

        result = await runner.run_reviewer(
            diff=SAMPLE_DIFF,
            pr_title="Fix pagination",
            pr_description="Fix off-by-one",
        )

        assert isinstance(result, ReviewVerdict)
        assert result.verdict == ReviewVerdictType.REQUEST_CHANGES
        assert result.confidence == 0.95

    async def test_validates_dict_response_into_verdict(
        self, runner: AgentRunner, sample_verdict: ReviewVerdict
    ):
        """run_reviewer validates a dict response into a ReviewVerdict."""
        runner.provider = MagicMock()
        runner.provider.run_with_structured_output = AsyncMock(return_value={
            "response": sample_verdict.model_dump(),
            "model": "claude-opus-4-6",
            "tokens_in": 100,
            "tokens_out": 50,
            "duration_ms": 1000,
        })

        result = await runner.run_reviewer(
            diff=SAMPLE_DIFF,
            pr_title="Fix pagination",
            pr_description="Fix off-by-one",
        )

        assert isinstance(result, ReviewVerdict)
        assert result.verdict == ReviewVerdictType.REQUEST_CHANGES
        assert len(result.issues) == 4

    async def test_approve_verdict_has_empty_issues(
        self, runner: AgentRunner, approve_verdict: ReviewVerdict
    ):
        """An approve verdict can have an empty issues list."""
        runner.provider = MagicMock()
        runner.provider.run_with_structured_output = AsyncMock(return_value={
            "response": approve_verdict,
            "model": "claude-opus-4-6",
            "tokens_in": 100,
            "tokens_out": 50,
            "duration_ms": 1000,
        })

        result = await runner.run_reviewer(
            diff=SAMPLE_DIFF,
            pr_title="Clean change",
            pr_description="No problems",
        )

        assert result.verdict == ReviewVerdictType.APPROVE
        assert result.issues == []
        assert result.confidence == 0.9

    async def test_verdict_confidence_must_be_between_0_and_1(self):
        """ReviewVerdict confidence field must be between 0.0 and 1.0."""
        # Valid: 0.0
        v = ReviewVerdict(
            verdict=ReviewVerdictType.APPROVE,
            issues=[],
            summary="OK",
            confidence=0.0,
        )
        assert v.confidence == 0.0

        # Valid: 1.0
        v = ReviewVerdict(
            verdict=ReviewVerdictType.APPROVE,
            issues=[],
            summary="OK",
            confidence=1.0,
        )
        assert v.confidence == 1.0

        # Invalid: > 1.0
        with pytest.raises(Exception):
            ReviewVerdict(
                verdict=ReviewVerdictType.APPROVE,
                issues=[],
                summary="OK",
                confidence=1.5,
            )

        # Invalid: < 0.0
        with pytest.raises(Exception):
            ReviewVerdict(
                verdict=ReviewVerdictType.APPROVE,
                issues=[],
                summary="OK",
                confidence=-0.1,
            )

    async def test_uses_structured_output_with_review_verdict_schema(
        self, runner: AgentRunner, sample_verdict: ReviewVerdict
    ):
        """run_reviewer passes ReviewVerdict as the output_schema."""
        runner.provider = MagicMock()
        runner.provider.run_with_structured_output = AsyncMock(return_value={
            "response": sample_verdict,
            "model": "claude-opus-4-6",
            "tokens_in": 100,
            "tokens_out": 50,
            "duration_ms": 1000,
        })

        await runner.run_reviewer(
            diff=SAMPLE_DIFF,
            pr_title="Fix pagination",
            pr_description="Fix off-by-one",
        )

        call_kwargs = runner.provider.run_with_structured_output.call_args.kwargs
        assert call_kwargs["output_schema"] is ReviewVerdict

    async def test_propagates_provider_errors(self, runner: AgentRunner):
        """run_reviewer propagates exceptions from the provider."""
        runner.provider = MagicMock()
        runner.provider.run_with_structured_output = AsyncMock(
            side_effect=ValueError("Model unavailable")
        )

        with pytest.raises(ValueError, match="Model unavailable"):
            await runner.run_reviewer(
                diff=SAMPLE_DIFF,
                pr_title="Fix pagination",
                pr_description="Fix off-by-one",
            )


# ---------------------------------------------------------------------------
# Issue severity classification tests
# ---------------------------------------------------------------------------


class TestIssueSeverityClassification:
    """Verify issues are correctly classified by severity."""

    async def test_issues_have_valid_severity_levels(
        self, runner: AgentRunner, sample_verdict: ReviewVerdict
    ):
        """All issues must have a valid ReviewSeverity value."""
        runner.provider = MagicMock()
        runner.provider.run_with_structured_output = AsyncMock(return_value={
            "response": sample_verdict,
            "model": "claude-opus-4-6",
            "tokens_in": 100,
            "tokens_out": 50,
            "duration_ms": 1000,
        })

        result = await runner.run_reviewer(
            diff=SAMPLE_DIFF,
            pr_title="Fix pagination",
            pr_description="Fix off-by-one",
        )

        valid_severities = {s for s in ReviewSeverity}
        for issue in result.issues:
            assert issue.severity in valid_severities

    async def test_critical_issues_counted(
        self, runner: AgentRunner, sample_verdict: ReviewVerdict
    ):
        """Can filter and count critical issues from the verdict."""
        runner.provider = MagicMock()
        runner.provider.run_with_structured_output = AsyncMock(return_value={
            "response": sample_verdict,
            "model": "claude-opus-4-6",
            "tokens_in": 100,
            "tokens_out": 50,
            "duration_ms": 1000,
        })

        result = await runner.run_reviewer(
            diff=SAMPLE_DIFF,
            pr_title="Fix pagination",
            pr_description="Fix off-by-one",
        )

        critical = [i for i in result.issues if i.severity == ReviewSeverity.CRITICAL]
        major = [i for i in result.issues if i.severity == ReviewSeverity.MAJOR]
        minor = [i for i in result.issues if i.severity == ReviewSeverity.MINOR]
        nit = [i for i in result.issues if i.severity == ReviewSeverity.NIT]

        assert len(critical) == 1
        assert len(major) == 1
        assert len(minor) == 1
        assert len(nit) == 1

    async def test_issues_have_file_path(
        self, runner: AgentRunner, sample_verdict: ReviewVerdict
    ):
        """Every issue must have a file_path."""
        runner.provider = MagicMock()
        runner.provider.run_with_structured_output = AsyncMock(return_value={
            "response": sample_verdict,
            "model": "claude-opus-4-6",
            "tokens_in": 100,
            "tokens_out": 50,
            "duration_ms": 1000,
        })

        result = await runner.run_reviewer(
            diff=SAMPLE_DIFF,
            pr_title="Fix pagination",
            pr_description="Fix off-by-one",
        )

        for issue in result.issues:
            assert issue.file_path, "Every issue must have a file_path"

    async def test_issue_line_range_is_optional(self):
        """line_range is optional — some issues are file-level."""
        issue_with_range = ReviewIssue(
            severity=ReviewSeverity.CRITICAL,
            file_path="handler.go",
            line_range="10-20",
            description="Bug",
        )
        assert issue_with_range.line_range == "10-20"

        issue_without_range = ReviewIssue(
            severity=ReviewSeverity.NIT,
            file_path="handler.go",
            description="Style issue",
        )
        assert issue_without_range.line_range is None

    async def test_issue_suggestion_is_optional(self):
        """suggestion is optional — not all issues have a fix."""
        issue_with = ReviewIssue(
            severity=ReviewSeverity.MAJOR,
            file_path="handler.go",
            description="Missing validation",
            suggestion="Add input validation",
        )
        assert issue_with.suggestion == "Add input validation"

        issue_without = ReviewIssue(
            severity=ReviewSeverity.MINOR,
            file_path="handler.go",
            description="Code smell",
        )
        assert issue_without.suggestion is None


# ---------------------------------------------------------------------------
# Model routing and changed files tests
# ---------------------------------------------------------------------------


class TestModelRoutingAndContext:
    """Verify model routing and changed file context."""

    async def test_reviewer_uses_opus_model(
        self, runner: AgentRunner, sample_verdict: ReviewVerdict
    ):
        """run_reviewer resolves to claude-opus-4-6 for review_diff tasks."""
        runner.provider = MagicMock()
        runner.provider.run_with_structured_output = AsyncMock(return_value={
            "response": sample_verdict,
            "model": "claude-opus-4-6",
            "tokens_in": 100,
            "tokens_out": 50,
            "duration_ms": 1000,
        })

        await runner.run_reviewer(
            diff=SAMPLE_DIFF,
            pr_title="Fix pagination",
            pr_description="Fix off-by-one",
        )

        call_kwargs = runner.provider.run_with_structured_output.call_args.kwargs
        assert call_kwargs["model"] == "claude-opus-4-6"

    async def test_changed_files_appended_to_user_message(
        self, runner: AgentRunner, sample_verdict: ReviewVerdict
    ):
        """When changed_files is provided, they appear in the user message."""
        runner.provider = MagicMock()
        runner.provider.run_with_structured_output = AsyncMock(return_value={
            "response": sample_verdict,
            "model": "claude-opus-4-6",
            "tokens_in": 100,
            "tokens_out": 50,
            "duration_ms": 1000,
        })

        changed = ["services/api/search/handler.go", "services/api/search/handler_test.go"]
        await runner.run_reviewer(
            diff=SAMPLE_DIFF,
            pr_title="Fix pagination",
            pr_description="Fix off-by-one",
            changed_files=changed,
        )

        call_kwargs = runner.provider.run_with_structured_output.call_args.kwargs
        user_msg = call_kwargs["user_message"]
        assert "services/api/search/handler.go" in user_msg
        assert "services/api/search/handler_test.go" in user_msg
        assert "Changed files:" in user_msg

    async def test_no_changed_files_omits_section(
        self, runner: AgentRunner, sample_verdict: ReviewVerdict
    ):
        """When changed_files is None, no 'Changed files:' section appears."""
        runner.provider = MagicMock()
        runner.provider.run_with_structured_output = AsyncMock(return_value={
            "response": sample_verdict,
            "model": "claude-opus-4-6",
            "tokens_in": 100,
            "tokens_out": 50,
            "duration_ms": 1000,
        })

        await runner.run_reviewer(
            diff=SAMPLE_DIFF,
            pr_title="Fix pagination",
            pr_description="Fix off-by-one",
            changed_files=None,
        )

        call_kwargs = runner.provider.run_with_structured_output.call_args.kwargs
        user_msg = call_kwargs["user_message"]
        assert "Changed files:" not in user_msg

    async def test_empty_changed_files_omits_section(
        self, runner: AgentRunner, sample_verdict: ReviewVerdict
    ):
        """When changed_files is an empty list, no 'Changed files:' section appears."""
        runner.provider = MagicMock()
        runner.provider.run_with_structured_output = AsyncMock(return_value={
            "response": sample_verdict,
            "model": "claude-opus-4-6",
            "tokens_in": 100,
            "tokens_out": 50,
            "duration_ms": 1000,
        })

        await runner.run_reviewer(
            diff=SAMPLE_DIFF,
            pr_title="Fix pagination",
            pr_description="Fix off-by-one",
            changed_files=[],
        )

        call_kwargs = runner.provider.run_with_structured_output.call_args.kwargs
        user_msg = call_kwargs["user_message"]
        assert "Changed files:" not in user_msg
