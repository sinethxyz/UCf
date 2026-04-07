"""Pydantic models for evaluation definitions and results."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from foundry.contracts.shared import FoundryBaseModel


class EvalDefinition(FoundryBaseModel):
    """Definition of an eval run to execute.

    Specifies the dataset, scorer, and model to use for evaluation.
    """

    dataset: str = Field(description="Name or path of the evaluation dataset.")
    scorer: str = Field(description="Name of the scorer to apply.")
    model: str = Field(description="Claude model to evaluate.")
    metadata: dict = Field(
        default_factory=dict,
        description="Additional metadata for the eval run.",
    )


class EventDetectionScores(FoundryBaseModel):
    """Precision/recall/F1 scores for event detection.

    Measures how well the extraction pipeline identifies events
    compared to the ground truth dataset.
    """

    predicted_count: int = Field(
        ge=0, description="Number of events predicted by the model."
    )
    expected_count: int = Field(
        ge=0, description="Number of events in the ground truth."
    )
    true_positives: int = Field(
        ge=0, description="Correctly predicted events."
    )
    false_positives: int = Field(
        ge=0, description="Events predicted but not in ground truth."
    )
    false_negatives: int = Field(
        ge=0, description="Ground truth events not predicted."
    )
    precision: float = Field(
        ge=0.0, le=1.0, description="Precision: TP / (TP + FP)."
    )
    recall: float = Field(
        ge=0.0, le=1.0, description="Recall: TP / (TP + FN)."
    )
    f1: float = Field(
        ge=0.0, le=1.0, description="F1 score: harmonic mean of precision and recall."
    )


class EvalScores(FoundryBaseModel):
    """Aggregate scores across all evaluation dimensions.

    Combines event detection metrics with accuracy scores for
    each extracted field category.
    """

    event_detection: EventDetectionScores = Field(
        description="Precision/recall/F1 for event detection."
    )
    event_type_accuracy: float = Field(
        ge=0.0, le=1.0, description="Accuracy of event type classification."
    )
    date_accuracy: float = Field(
        ge=0.0, le=1.0, description="Accuracy of extracted dates."
    )
    structured_data_accuracy: float = Field(
        ge=0.0, le=1.0, description="Accuracy of structured data fields."
    )
    evidence_type_accuracy: float = Field(
        ge=0.0, le=1.0, description="Accuracy of evidence strength classification."
    )
    confidence_calibration: float = Field(
        ge=0.0, le=1.0, description="How well confidence scores match actual accuracy."
    )


class EvalItemResult(FoundryBaseModel):
    """Score for a single eval item.

    Contains per-item scores and any errors encountered during evaluation.
    """

    item_id: str = Field(description="Identifier of the eval dataset item.")
    scores: EvalScores = Field(description="Scores for this item.")
    errors: list[dict] = Field(
        default_factory=list,
        description="Errors encountered while evaluating this item.",
    )


class EvalResult(FoundryBaseModel):
    """Aggregate results of an eval run.

    Contains the definition, state, per-item results, and aggregate
    metrics for a complete evaluation run.
    """

    eval_id: UUID = Field(description="Unique identifier for this eval run.")
    definition: EvalDefinition = Field(
        description="The eval definition that produced these results."
    )
    state: Literal["running", "completed", "failed"] = Field(
        description="Current state of the eval run."
    )
    aggregate_metrics: EvalScores | None = Field(
        default=None,
        description="Aggregate scores across all items, populated on completion.",
    )
    item_count: int = Field(
        ge=0, description="Total number of items in the eval dataset."
    )
    completed_at: datetime | None = Field(
        default=None,
        description="When the eval run finished, if complete.",
    )
