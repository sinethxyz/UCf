"""Model routing: maps task types and agent roles to Claude models.

Routing principle: Opus for judgment-heavy work (review, architecture,
red-teaming). Sonnet for implementation and structured extraction.
Haiku for classification, tagging, and reconnaissance.
"""

MODEL_ROUTING: dict[str, dict[str, str]] = {
    "endpoint_build": {
        "planner": "claude-sonnet-4-6",
        "implementer": "claude-sonnet-4-6",
        "reviewer": "claude-opus-4-6",
    },
    "feature_slice": {
        "planner": "claude-sonnet-4-6",
        "implementer": "claude-sonnet-4-6",
        "reviewer": "claude-opus-4-6",
    },
    "bug_fix": {
        "planner": "claude-sonnet-4-6",
        "implementer": "claude-sonnet-4-6",
        "reviewer": "claude-opus-4-6",
    },
    "refactor": {
        "planner": "claude-sonnet-4-6",
        "implementer": "claude-sonnet-4-6",
        "reviewer": "claude-opus-4-6",
    },
    "migration_plan": {
        "planner": "claude-opus-4-6",
        "reviewer": "claude-opus-4-6",
        "migration_guard": "claude-opus-4-6",
    },
    "architecture_review": {
        "planner": "claude-opus-4-6",
        "reviewer": "claude-opus-4-6",
    },
    "review_diff": {
        "reviewer": "claude-opus-4-6",
    },
    "extraction_batch": {
        "extractor": "claude-sonnet-4-6",
        "classifier": "claude-haiku-4-5",
    },
    "evidence_classification": {
        "classifier": "claude-haiku-4-5",
    },
    "eval_run": {
        "evaluator": "claude-sonnet-4-6",
    },
    "canon_update": {
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


def resolve_model(task_type: str, agent_role: str, override: str | None = None) -> str:
    """Resolve the model to use for a given task type and agent role.

    Args:
        task_type: The task type enum value.
        agent_role: The subagent role (planner, implementer, reviewer, etc.).
        override: Optional model override from the task request.

    Returns:
        Model identifier string.
    """
    if override:
        return override

    routing = MODEL_ROUTING.get(task_type, MODEL_ROUTING["_default"])
    return routing.get(agent_role, MODEL_ROUTING["_default"].get(agent_role, "claude-sonnet-4-6"))
