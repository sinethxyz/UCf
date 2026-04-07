"""Spec planning endpoints — debug/convenience only."""

import shutil
import tempfile

from fastapi import APIRouter, HTTPException

from foundry.contracts.task_types import PlanArtifact, TaskRequest
from foundry.orchestration.agent_runner import AgentRunner

router = APIRouter()


@router.post("/specs/plan", response_model=PlanArtifact)
async def create_plan(
    request: TaskRequest,
) -> PlanArtifact:
    """Convert a task request into a structured implementation plan.

    Runs the planner subagent to produce a PlanArtifact with ordered
    implementation steps, risks, and open questions.

    This is a debug/convenience endpoint — no run lifecycle, no artifacts
    stored. Useful for testing planning prompts in isolation.
    """
    runner = AgentRunner()
    tmpdir = tempfile.mkdtemp(prefix="foundry-spec-")
    try:
        plan = await runner.run_planner(request, worktree_path=tmpdir)
        return plan
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Planning failed: {e}")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
