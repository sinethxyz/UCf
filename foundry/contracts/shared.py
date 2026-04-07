"""Common enums and base models used across all Foundry contracts."""

from enum import Enum

from pydantic import BaseModel


class TaskType(str, Enum):
    """All supported Foundry task types.

    Each task type maps to a specific orchestration pipeline and determines
    which subagents are invoked, what verification runs, and which paths
    are authorized for modification.
    """

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
    """Run lifecycle states.

    A run transitions through these states linearly, with terminal states
    being completed, plan_failed, verification_failed, review_failed,
    cancelled, and errored.
    """

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
    """MCP server profiles controlling tool access per run.

    Each profile grants a different set of MCP server connections,
    scoping what external systems a run can interact with.
    """

    NONE = "none"
    GITHUB_ONLY = "github_only"
    GITHUB_POSTGRES_READONLY = "github_postgres_readonly"
    RESEARCH_FULL = "research_full"
    APP_BUILD_MINIMAL = "app_build_minimal"


class ArtifactType(str, Enum):
    """Types of artifacts produced during a run.

    Every meaningful run must store artifacts. This enum classifies
    each artifact for retrieval and auditing.
    """

    PLAN = "plan"
    DIFF = "diff"
    PATCH = "patch"
    VERIFICATION_RESULT = "verification_result"
    REVIEW = "review"
    TOOL_LOG = "tool_log"
    EXTRACTION_RESULT = "extraction_result"
    EVAL_RESULT = "eval_result"
    PR_METADATA = "pr_metadata"
    ERROR_LOG = "error_log"


class EvidenceStrength(str, Enum):
    """Evidence strength levels for extraction.

    Defines how directly a piece of evidence supports an extracted event,
    from direct quotes to contextual inference.
    """

    DIRECT = "direct"
    STRONG_INFERENCE = "strong_inference"
    WEAK_INFERENCE = "weak_inference"
    CONTEXTUAL = "contextual"


class EventType(str, Enum):
    """Startup event types recognized by the extraction pipeline.

    These map to the event taxonomy defined in canon/docs/event_taxonomy.md.
    """

    FUNDING_ROUND = "funding_round"
    PRODUCT_LAUNCH = "product_launch"
    PRODUCT_UPDATE = "product_update"
    HIRE = "hire"
    PARTNERSHIP = "partnership"
    ACQUISITION = "acquisition"
    PIVOT = "pivot"
    LAYOFF = "layoff"
    EXPANSION = "expansion"
    REGULATORY = "regulatory"
    TRACTION_SIGNAL = "traction_signal"
    EXECUTIVE_CHANGE = "executive_change"
    SHUTDOWN = "shutdown"


class Severity(str, Enum):
    """Review issue severity levels.

    Used by the reviewer subagent to classify the importance of each
    issue found during code review.
    """

    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"
    NIT = "nit"


class ReviewVerdictType(str, Enum):
    """Review verdict outcomes.

    The reviewer subagent produces one of these verdicts after
    independently evaluating a diff.
    """

    APPROVE = "approve"
    REQUEST_CHANGES = "request_changes"
    REJECT = "reject"


class Complexity(str, Enum):
    """Plan complexity levels.

    Used by the planner subagent to estimate the scope and risk
    of an implementation plan.
    """

    TRIVIAL = "trivial"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    CRITICAL = "critical"


class FoundryBaseModel(BaseModel):
    """Base model with shared configuration for all Foundry models.

    All Foundry Pydantic models inherit from this base to ensure
    consistent serialization behavior and ORM compatibility.
    """

    model_config = {"from_attributes": True, "strict": True}
