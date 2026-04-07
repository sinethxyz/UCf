"""Spec planning endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db_session
from foundry.contracts.task_types import PlanArtifact

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
    db: AsyncSession = Depends(get_db_session),
) -> PlanArtifact:
    """Convert a feature spec into a structured implementation plan.

    Runs the planner subagent to produce a PlanArtifact with ordered
    implementation steps, risks, and open questions.
    """
    raise HTTPException(status_code=501, detail="Not implemented")
