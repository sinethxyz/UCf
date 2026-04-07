"""Eval run endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db_session
from foundry.contracts.eval_models import EvalDefinition, EvalResult

router = APIRouter()


@router.post("/evals/run", status_code=201, response_model=EvalResult)
async def create_eval(
    definition: EvalDefinition,
    db: AsyncSession = Depends(get_db_session),
) -> EvalResult:
    """Start an eval run.

    Submits an eval definition for asynchronous execution. The eval
    runner scores model outputs against the specified dataset and scorer.
    """
    raise HTTPException(status_code=501, detail="Not implemented")


@router.get("/evals/{eval_id}", response_model=EvalResult)
async def get_eval(
    eval_id: UUID,
    db: AsyncSession = Depends(get_db_session),
) -> EvalResult:
    """Get eval run status and results."""
    raise HTTPException(status_code=501, detail="Not implemented")
