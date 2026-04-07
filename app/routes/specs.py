"""Spec planning endpoints."""

from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from foundry.contracts.shared import MCPProfile, TaskType
from foundry.contracts.task_types import PlanArtifact, TaskRequest
from foundry.orchestration.agent_runner import AgentRunner

router = APIRouter()


class SpecPlanRequest(BaseModel):
    """Request body for spec-to-plan conversion."""

    spec_text: str
    repo: str = "unicorn-app"
    base_branch: str = "main"
    metadata: dict = {}


@router.post("/specs/plan", response_model=PlanArtifact)
async def create_plan(
    request: SpecPlanRequest,
) -> PlanArtifact:
    """Convert a feature spec into a structured implementation plan.

    Runs the planner subagent to produce a PlanArtifact with ordered
    implementation steps, risks, and open questions.

    This is a debug/convenience endpoint — no run lifecycle, no artifacts stored.
    """
    # Build a synthetic TaskRequest for the planner
    task_request = TaskRequest(
        task_type=TaskType.BUG_FIX,
        repo=request.repo,
        base_branch=request.base_branch,
        title="Spec plan request",
        prompt=request.spec_text,
        target_paths=[],
        mcp_profile=MCPProfile.NONE,
        metadata=request.metadata,
    )

    runner = AgentRunner()
    try:
        plan = await runner.run_planner(task_request, worktree_path=".")
        return plan
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Planning failed: {e}")
