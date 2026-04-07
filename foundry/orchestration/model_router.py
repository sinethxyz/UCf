"""Model routing: maps task types and agent roles to Claude models.

Routing principle: Opus for judgment-heavy work (review, architecture,
red-teaming). Sonnet for implementation and structured extraction.
Haiku for classification, tagging, and reconnaissance.
"""

from foundry.contracts.shared import TaskType

# ---------------------------------------------------------------------------
# Routing table: task_type (str) -> agent_role -> model identifier
#
# - claude-opus-4-6:   architecture, critical planning, review, migration guard
# - claude-sonnet-4-6: implementation, extraction, evals, medium-complexity
# - claude-haiku-4-5:  classification, tagging, reconnaissance
# ---------------------------------------------------------------------------

MODEL_ROUTING: dict[str, dict[str, str]] = {
    TaskType.ENDPOINT_BUILD.value: {
        "planner": "claude-sonnet-4-6",
        "implementer": "claude-sonnet-4-6",
        "reviewer": "claude-opus-4-6",
    },
    TaskType.FEATURE_SLICE.value: {
        "planner": "claude-sonnet-4-6",
        "implementer": "claude-sonnet-4-6",
        "reviewer": "claude-opus-4-6",
    },
    TaskType.BUG_FIX.value: {
        "planner": "claude-sonnet-4-6",
        "implementer": "claude-sonnet-4-6",
        "reviewer": "claude-opus-4-6",
    },
    TaskType.REFACTOR.value: {
        "planner": "claude-sonnet-4-6",
        "implementer": "claude-sonnet-4-6",
        "reviewer": "claude-opus-4-6",
    },
    TaskType.MIGRATION_PLAN.value: {
        "planner": "claude-opus-4-6",
        "reviewer": "claude-opus-4-6",
        "migration_guard": "claude-opus-4-6",
    },
    TaskType.ARCHITECTURE_REVIEW.value: {
        "planner": "claude-opus-4-6",
        "reviewer": "claude-opus-4-6",
    },
    TaskType.REVIEW_DIFF.value: {
        "reviewer": "claude-opus-4-6",
    },
    TaskType.EXTRACTION_BATCH.value: {
        "extractor": "claude-sonnet-4-6",
        "classifier": "claude-haiku-4-5",
    },
    TaskType.EVIDENCE_CLASSIFICATION.value: {
        "classifier": "claude-haiku-4-5",
    },
    TaskType.EVAL_RUN.value: {
        "evaluator": "claude-sonnet-4-6",
    },
    TaskType.CANON_UPDATE.value: {
        "planner": "claude-opus-4-6",
        "implementer": "claude-sonnet-4-6",
        "reviewer": "claude-opus-4-6",
    },
    "_default": {
        "planner": "claude-sonnet-4-6",
        "implementer": "claude-sonnet-4-6",
        "reviewer": "claude-opus-4-6",
        "explorer": "claude-haiku-4-5",
    },
}


def resolve_model(
    task_type: TaskType | str,
    agent_role: str,
    override: str | None = None,
) -> str:
    """Resolve the model to use for a given task type and agent role.

    Lookup order:
    1. Explicit override (from task request's model_override field).
    2. Task-specific routing entry.
    3. _default routing entry.
    4. Fallback to claude-sonnet-4-6.

    Args:
        task_type: The task type (enum or string value).
        agent_role: The subagent role (planner, implementer, reviewer, etc.).
        override: Optional model override from the task request.

    Returns:
        Model identifier string (e.g. "claude-opus-4-6").
    """
    if override:
        return override

    task_key = task_type.value if isinstance(task_type, TaskType) else task_type
    routing = MODEL_ROUTING.get(task_key, MODEL_ROUTING["_default"])
    return routing.get(
        agent_role,
        MODEL_ROUTING["_default"].get(agent_role, "claude-sonnet-4-6"),
    )
