"""Pydantic models defining all Foundry contracts."""

from foundry.contracts.shared import (
    ArtifactType,
    Complexity,
    EvidenceStrength,
    EventType,
    FoundryBaseModel,
    MCPProfile,
    ReviewVerdictType,
    RunState,
    Severity,
    TaskType,
)
from foundry.contracts.task_types import PlanArtifact, PlanStep, TaskRequest
from foundry.contracts.run_models import RunArtifact, RunEvent, RunResponse
from foundry.contracts.review_models import ReviewIssue, ReviewVerdict
from foundry.contracts.extraction_models import (
    Evidence,
    ExtractionClassification,
    ExtractionEvent,
    ExtractionResult,
)
from foundry.contracts.eval_models import (
    EvalDefinition,
    EvalItemResult,
    EvalResult,
    EvalScores,
    EventDetectionScores,
)

__all__ = [
    # Enums
    "ArtifactType",
    "Complexity",
    "EvidenceStrength",
    "EventType",
    "MCPProfile",
    "ReviewVerdictType",
    "RunState",
    "Severity",
    "TaskType",
    # Base
    "FoundryBaseModel",
    # Task types
    "PlanArtifact",
    "PlanStep",
    "TaskRequest",
    # Run models
    "RunArtifact",
    "RunEvent",
    "RunResponse",
    # Review models
    "ReviewIssue",
    "ReviewVerdict",
    # Extraction models
    "Evidence",
    "ExtractionClassification",
    "ExtractionEvent",
    "ExtractionResult",
    # Eval models
    "EvalDefinition",
    "EvalItemResult",
    "EvalResult",
    "EvalScores",
    "EventDetectionScores",
]
