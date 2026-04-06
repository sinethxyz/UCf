"""Pydantic models for evaluation definitions and results."""

from datetime import datetime

from pydantic import Field

from foundry.contracts.shared import FoundryBaseModel


class EvalDefinition(FoundryBaseModel):
    """Definition of an eval run to execute."""

    dataset: str
    scorer: str
    model: str
    metadata: dict = Field(default_factory=dict)


class EvalItemResult(FoundryBaseModel):
    """Score for a single eval item."""

    item_index: int
    expected: dict
    actual: dict
    score: float = Field(ge=0.0, le=1.0)
    notes: str | None = None


class EvalResult(FoundryBaseModel):
    """Aggregate results of an eval run."""

    dataset: str
    scorer: str
    model: str
    total_items: int
    precision: float | None = None
    recall: float | None = None
    f1: float | None = None
    accuracy: float | None = None
    per_item: list[EvalItemResult] = Field(default_factory=list)
    started_at: datetime
    completed_at: datetime | None = None
