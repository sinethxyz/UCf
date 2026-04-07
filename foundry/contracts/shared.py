"""Common enums and base models used across all Foundry contracts."""

from enum import Enum

from pydantic import BaseModel


class TaskType(str, Enum):
    """All supported Foundry task types."""

    ENDPOINT_BUILD = "endpoint_build"
    FEATURE_SLICE = "feature_slice"
    BUG_FIX = "bug_fix"
    REFACTOR = "refactor"
    MIGRATION_PLAN = "migration_plan"
    ARCHITECTURE_REVIEW = "architecture_review"
    REVIEW_DIFF = "review_diff"
    EXTRACTION_BATCH = "extraction_batch"
    EVIDENCE_CLASSIFICATION = "evidence_classification"
    EVAL_RUN = "eval_run"
    CANON_UPDATE = "canon_update"


class RunState(str, Enum):
    """Run lifecycle states."""

    QUEUED = "queued"
    CREATING_WORKTREE = "creating_worktree"
    PLANNING = "planning"
    IMPLEMENTING = "implementing"
    VERIFYING = "verifying"
    VERIFICATION_PASSED = "verification_passed"
    REVIEWING = "reviewing"
    PR_OPENED = "pr_opened"
    COMPLETED = "completed"
    PLAN_FAILED = "plan_failed"
    VERIFICATION_FAILED = "verification_failed"
    REVIEW_FAILED = "review_failed"
    CANCELLED = "cancelled"
    ERRORED = "errored"


class MCPProfile(str, Enum):
    """MCP server profiles controlling tool access per run."""

    NONE = "none"
    GITHUB_ONLY = "github_only"
    GITHUB_POSTGRES_READONLY = "github_postgres_readonly"
    RESEARCH_FULL = "research_full"
    APP_BUILD_MINIMAL = "app_build_minimal"


class Complexity(str, Enum):
    """Plan complexity levels."""

    TRIVIAL = "trivial"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    CRITICAL = "critical"


class ReviewSeverity(str, Enum):
    """Review issue severity levels."""

    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"
    NIT = "nit"


class ReviewVerdictType(str, Enum):
    """Review verdict outcomes."""

    APPROVE = "approve"
    REQUEST_CHANGES = "request_changes"
    REJECT = "reject"


class EvidenceStrength(str, Enum):
    """Evidence strength levels for extraction."""

    DIRECT = "direct"
    STRONG_INFERENCE = "strong_inference"
    WEAK_INFERENCE = "weak_inference"
    CONTEXTUAL = "contextual"


class FoundryBaseModel(BaseModel):
    """Base model with shared configuration for all Foundry models."""

    model_config = {"from_attributes": True}
