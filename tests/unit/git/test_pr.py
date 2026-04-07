"""Tests for PRCreator: title/body building, GitHub API calls, and labeling."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from foundry.contracts.review_models import ReviewIssue, ReviewVerdict
from foundry.contracts.shared import (
    Complexity,
    MCPProfile,
    ReviewSeverity,
    ReviewVerdictType,
    TaskType,
)
from foundry.contracts.task_types import PlanArtifact, PlanStep, TaskRequest
from foundry.git.pr import (
    PRCreator,
    _build_pr_body,
    _build_pr_title,
    _repo_slug,
    _task_type_label,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def task_request() -> TaskRequest:
    return TaskRequest(
        task_type=TaskType.BUG_FIX,
        repo="unicorn-app",
        base_branch="main",
        title="Fix pagination bug",
        prompt="Fix the off-by-one error in search pagination",
        target_paths=["services/api/search/handler.go"],
        mcp_profile=MCPProfile.NONE,
    )


@pytest.fixture
def plan_artifact() -> PlanArtifact:
    return PlanArtifact(
        task_id=uuid4(),
        steps=[
            PlanStep(
                file_path="services/api/search/handler.go",
                action="modify",
                rationale="Fix off-by-one in offset calculation",
            ),
            PlanStep(
                file_path="services/api/search/handler_test.go",
                action="modify",
                rationale="Add regression test for pagination edge case",
            ),
        ],
        risks=["Might affect other pagination endpoints"],
        open_questions=[],
        estimated_complexity=Complexity.SMALL,
    )


@pytest.fixture
def review_verdict() -> ReviewVerdict:
    return ReviewVerdict(
        verdict=ReviewVerdictType.APPROVE,
        issues=[
            ReviewIssue(
                severity=ReviewSeverity.NIT,
                file_path="services/api/search/handler.go",
                description="Consider adding a comment explaining the offset logic",
            ),
        ],
        summary="Clean fix for the off-by-one pagination bug.",
    )


SAMPLE_DIFF = """\
diff --git a/services/api/search/handler.go b/services/api/search/handler.go
--- a/services/api/search/handler.go
+++ b/services/api/search/handler.go
@@ -42,7 +42,7 @@
-    offset := (page - 1) * pageSize + 1
+    offset := (page - 1) * pageSize
"""

SAMPLE_VERIFICATION_RESULTS = [
    {"check_type": "go_build", "passed": True, "output": "ok", "duration_ms": 1200},
    {"check_type": "go_vet", "passed": True, "output": "ok", "duration_ms": 800},
    {"check_type": "go_test", "passed": True, "output": "PASS", "duration_ms": 3500},
]


# ---------------------------------------------------------------------------
# _build_pr_title tests
# ---------------------------------------------------------------------------


class TestBuildPrTitle:
    def test_formats_title_with_task_type_and_title(self, task_request: TaskRequest):
        title = _build_pr_title(task_request)
        assert title == "[Foundry] bug_fix: Fix pagination bug"

    def test_endpoint_build_task_type(self):
        req = TaskRequest(
            task_type=TaskType.ENDPOINT_BUILD,
            repo="unicorn-app",
            title="Add company timeline endpoint",
            prompt="Build GET /v1/companies/{id}/timeline",
        )
        assert _build_pr_title(req) == "[Foundry] endpoint_build: Add company timeline endpoint"

    def test_refactor_task_type(self):
        req = TaskRequest(
            task_type=TaskType.REFACTOR,
            repo="unicorn-foundry",
            title="Extract event normalization",
            prompt="Refactor event normalization into shared module",
        )
        assert _build_pr_title(req) == "[Foundry] refactor: Extract event normalization"


# ---------------------------------------------------------------------------
# _build_pr_body tests
# ---------------------------------------------------------------------------


class TestBuildPrBody:
    def test_body_contains_summary_section(
        self, task_request, plan_artifact, review_verdict,
    ):
        body = _build_pr_body(
            task_request, plan_artifact, SAMPLE_DIFF,
            SAMPLE_VERIFICATION_RESULTS, review_verdict, uuid4(),
        )
        assert "## Summary" in body
        assert "off-by-one" in body

    def test_body_contains_plan_section(
        self, task_request, plan_artifact, review_verdict,
    ):
        body = _build_pr_body(
            task_request, plan_artifact, SAMPLE_DIFF,
            SAMPLE_VERIFICATION_RESULTS, review_verdict, uuid4(),
        )
        assert "## Plan" in body
        assert "Complexity: small" in body
        assert "Steps: 2" in body
        assert "Might affect other pagination endpoints" in body

    def test_body_contains_changes_section(
        self, task_request, plan_artifact, review_verdict,
    ):
        body = _build_pr_body(
            task_request, plan_artifact, SAMPLE_DIFF,
            SAMPLE_VERIFICATION_RESULTS, review_verdict, uuid4(),
        )
        assert "## Changes" in body
        assert "`services/api/search/handler.go`" in body
        assert "modify" in body
        assert "Fix off-by-one" in body

    def test_body_contains_verification_results(
        self, task_request, plan_artifact, review_verdict,
    ):
        body = _build_pr_body(
            task_request, plan_artifact, SAMPLE_DIFF,
            SAMPLE_VERIFICATION_RESULTS, review_verdict, uuid4(),
        )
        assert "## Verification" in body
        assert "[x] go_build" in body
        assert "[x] go_vet" in body
        assert "[x] go_test" in body

    def test_body_shows_failed_verification_checks(
        self, task_request, plan_artifact, review_verdict,
    ):
        failed_results = [
            {"check_type": "go_build", "passed": True},
            {"check_type": "go_test", "passed": False},
        ]
        body = _build_pr_body(
            task_request, plan_artifact, SAMPLE_DIFF,
            failed_results, review_verdict, uuid4(),
        )
        assert "[x] go_build" in body
        assert "[ ] go_test" in body

    def test_body_default_verification_when_empty(
        self, task_request, plan_artifact, review_verdict,
    ):
        body = _build_pr_body(
            task_request, plan_artifact, SAMPLE_DIFF,
            [], review_verdict, uuid4(),
        )
        assert "[x] Verification completed" in body

    def test_body_contains_review_verdict(
        self, task_request, plan_artifact, review_verdict,
    ):
        body = _build_pr_body(
            task_request, plan_artifact, SAMPLE_DIFF,
            SAMPLE_VERIFICATION_RESULTS, review_verdict, uuid4(),
        )
        assert "## Review" in body
        assert "Verdict: approve" in body
        assert "Clean fix" in body
        assert "Issues: 1" in body

    def test_body_contains_artifacts_section(
        self, task_request, plan_artifact, review_verdict,
    ):
        run_id = uuid4()
        body = _build_pr_body(
            task_request, plan_artifact, SAMPLE_DIFF,
            SAMPLE_VERIFICATION_RESULTS, review_verdict, run_id,
        )
        assert "## Artifacts" in body
        assert f"runs/{run_id}/plan.json" in body
        assert f"runs/{run_id}/diff.patch" in body
        assert f"runs/{run_id}/verification.json" in body
        assert f"runs/{run_id}/review.json" in body

    def test_body_contains_run_metadata(
        self, task_request, plan_artifact, review_verdict,
    ):
        run_id = uuid4()
        body = _build_pr_body(
            task_request, plan_artifact, SAMPLE_DIFF,
            SAMPLE_VERIFICATION_RESULTS, review_verdict, run_id,
        )
        assert "## Run Metadata" in body
        assert f"Run ID: {run_id}" in body
        assert "Task Type: bug_fix" in body

    def test_body_truncates_long_summary(
        self, plan_artifact, review_verdict,
    ):
        req = TaskRequest(
            task_type=TaskType.BUG_FIX,
            repo="unicorn-app",
            title="Fix bug",
            prompt="x" * 1000,
        )
        body = _build_pr_body(
            req, plan_artifact, SAMPLE_DIFF,
            [], review_verdict, uuid4(),
        )
        # Summary section should have at most 500 chars of the prompt
        summary_start = body.index("## Summary")
        plan_start = body.index("## Plan")
        summary_section = body[summary_start:plan_start]
        # The 'x' count should be 500
        assert summary_section.count("x") == 500

    def test_body_plan_no_risks(
        self, task_request, review_verdict,
    ):
        plan = PlanArtifact(
            task_id=uuid4(),
            steps=[PlanStep(file_path="a.go", action="modify", rationale="change")],
            risks=[],
            open_questions=[],
            estimated_complexity=Complexity.TRIVIAL,
        )
        body = _build_pr_body(
            task_request, plan, SAMPLE_DIFF,
            [], review_verdict, uuid4(),
        )
        assert "Risks: None identified" in body


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_task_type_label_bug_fix(self):
        req = TaskRequest(
            task_type=TaskType.BUG_FIX, repo="unicorn-app",
            title="t", prompt="p",
        )
        assert _task_type_label(req) == "bug-fix"

    def test_task_type_label_endpoint_build(self):
        req = TaskRequest(
            task_type=TaskType.ENDPOINT_BUILD, repo="unicorn-app",
            title="t", prompt="p",
        )
        assert _task_type_label(req) == "endpoint-build"

    def test_task_type_label_extraction_batch(self):
        req = TaskRequest(
            task_type=TaskType.EXTRACTION_BATCH, repo="unicorn-app",
            title="t", prompt="p",
        )
        assert _task_type_label(req) == "extraction-batch"

    def test_repo_slug_unicorn_app(self):
        req = TaskRequest(
            task_type=TaskType.BUG_FIX, repo="unicorn-app",
            title="t", prompt="p",
        )
        assert _repo_slug(req) == "sinethxyz/unicorn-app"

    def test_repo_slug_unicorn_foundry(self):
        req = TaskRequest(
            task_type=TaskType.BUG_FIX, repo="unicorn-foundry",
            title="t", prompt="p",
        )
        assert _repo_slug(req) == "sinethxyz/ucf"


# ---------------------------------------------------------------------------
# PRCreator.create_pr tests
# ---------------------------------------------------------------------------


class TestPRCreatorCreatePr:
    @pytest.fixture
    def pr_creator(self) -> PRCreator:
        creator = PRCreator(token="test-token")
        creator.client = MagicMock()
        creator.client.create_pull_request = AsyncMock(return_value={
            "url": "https://github.com/sinethxyz/unicorn-app/pull/42",
            "number": 42,
            "html_url": "https://github.com/sinethxyz/unicorn-app/pull/42",
        })
        creator.client.add_pr_labels = AsyncMock()
        return creator

    async def test_create_pr_calls_github_api(
        self, pr_creator, task_request, plan_artifact, review_verdict,
    ):
        run_id = uuid4()
        result = await pr_creator.create_pr(
            task_request=task_request,
            plan=plan_artifact,
            diff=SAMPLE_DIFF,
            verification_results=SAMPLE_VERIFICATION_RESULTS,
            review_verdict=review_verdict,
            run_id=run_id,
            branch_name="foundry/bug-fix-pagination",
            base_branch="main",
        )

        pr_creator.client.create_pull_request.assert_called_once()
        call_kwargs = pr_creator.client.create_pull_request.call_args.kwargs
        assert call_kwargs["repo"] == "sinethxyz/unicorn-app"
        assert call_kwargs["head"] == "foundry/bug-fix-pagination"
        assert call_kwargs["base"] == "main"
        assert "[Foundry] bug_fix: Fix pagination bug" in call_kwargs["title"]

    async def test_create_pr_returns_url_and_number(
        self, pr_creator, task_request, plan_artifact, review_verdict,
    ):
        result = await pr_creator.create_pr(
            task_request=task_request,
            plan=plan_artifact,
            diff=SAMPLE_DIFF,
            verification_results=SAMPLE_VERIFICATION_RESULTS,
            review_verdict=review_verdict,
            run_id=uuid4(),
            branch_name="foundry/bug-fix-pagination",
            base_branch="main",
        )

        assert result["url"] == "https://github.com/sinethxyz/unicorn-app/pull/42"
        assert result["number"] == 42

    async def test_create_pr_applies_standard_labels(
        self, pr_creator, task_request, plan_artifact, review_verdict,
    ):
        await pr_creator.create_pr(
            task_request=task_request,
            plan=plan_artifact,
            diff=SAMPLE_DIFF,
            verification_results=SAMPLE_VERIFICATION_RESULTS,
            review_verdict=review_verdict,
            run_id=uuid4(),
            branch_name="foundry/bug-fix-pagination",
            base_branch="main",
        )

        pr_creator.client.add_pr_labels.assert_called_once()
        call_args = pr_creator.client.add_pr_labels.call_args
        labels = call_args[0][2]  # positional: repo, pr_number, labels
        assert "foundry" in labels
        assert "needs-human-review" in labels
        assert "bug-fix" in labels

    async def test_create_pr_body_includes_all_sections(
        self, pr_creator, task_request, plan_artifact, review_verdict,
    ):
        await pr_creator.create_pr(
            task_request=task_request,
            plan=plan_artifact,
            diff=SAMPLE_DIFF,
            verification_results=SAMPLE_VERIFICATION_RESULTS,
            review_verdict=review_verdict,
            run_id=uuid4(),
            branch_name="foundry/bug-fix-pagination",
            base_branch="main",
        )

        body = pr_creator.client.create_pull_request.call_args.kwargs["body"]
        assert "## Summary" in body
        assert "## Plan" in body
        assert "## Changes" in body
        assert "## Verification" in body
        assert "## Review" in body
        assert "## Artifacts" in body
        assert "## Run Metadata" in body

    async def test_create_pr_label_failure_does_not_raise(
        self, pr_creator, task_request, plan_artifact, review_verdict,
    ):
        pr_creator.client.add_pr_labels = AsyncMock(
            side_effect=RuntimeError("Label API error"),
        )

        # Should not raise
        result = await pr_creator.create_pr(
            task_request=task_request,
            plan=plan_artifact,
            diff=SAMPLE_DIFF,
            verification_results=SAMPLE_VERIFICATION_RESULTS,
            review_verdict=review_verdict,
            run_id=uuid4(),
            branch_name="foundry/bug-fix-pagination",
            base_branch="main",
        )

        assert result["url"] == "https://github.com/sinethxyz/unicorn-app/pull/42"

    async def test_create_pr_uses_foundry_repo_for_foundry_tasks(
        self, pr_creator, plan_artifact, review_verdict,
    ):
        req = TaskRequest(
            task_type=TaskType.REFACTOR,
            repo="unicorn-foundry",
            title="Refactor thing",
            prompt="Refactor the thing",
        )
        await pr_creator.create_pr(
            task_request=req,
            plan=plan_artifact,
            diff=SAMPLE_DIFF,
            verification_results=[],
            review_verdict=review_verdict,
            run_id=uuid4(),
            branch_name="foundry/refactor-thing",
            base_branch="main",
        )

        call_kwargs = pr_creator.client.create_pull_request.call_args.kwargs
        assert call_kwargs["repo"] == "sinethxyz/ucf"

    async def test_create_pr_endpoint_build_label(
        self, pr_creator, plan_artifact, review_verdict,
    ):
        req = TaskRequest(
            task_type=TaskType.ENDPOINT_BUILD,
            repo="unicorn-app",
            title="Add timeline endpoint",
            prompt="Build the timeline",
        )
        await pr_creator.create_pr(
            task_request=req,
            plan=plan_artifact,
            diff=SAMPLE_DIFF,
            verification_results=[],
            review_verdict=review_verdict,
            run_id=uuid4(),
            branch_name="foundry/endpoint-build-timeline",
            base_branch="main",
        )

        labels = pr_creator.client.add_pr_labels.call_args[0][2]
        assert "endpoint-build" in labels


# ---------------------------------------------------------------------------
# PRCreator.add_comment / add_labels tests
# ---------------------------------------------------------------------------


class TestPRCreatorDelegation:
    async def test_add_comment_delegates_to_client(self):
        creator = PRCreator(token="test")
        creator.client = MagicMock()
        creator.client.add_pr_comment = AsyncMock()

        await creator.add_comment("sinethxyz/unicorn-app", 42, "LGTM")

        creator.client.add_pr_comment.assert_called_once_with(
            "sinethxyz/unicorn-app", 42, "LGTM",
        )

    async def test_add_labels_delegates_to_client(self):
        creator = PRCreator(token="test")
        creator.client = MagicMock()
        creator.client.add_pr_labels = AsyncMock()

        await creator.add_labels("sinethxyz/unicorn-app", 42, ["urgent"])

        creator.client.add_pr_labels.assert_called_once_with(
            "sinethxyz/unicorn-app", 42, ["urgent"],
        )
