"""Pydantic models for signal extraction: events, evidence, and results."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from foundry.contracts.shared import EvidenceStrength, FoundryBaseModel


class Evidence(FoundryBaseModel):
    """An evidence object attached to an extracted event."""

    type: EvidenceStrength
    quote: str
    confidence: float = Field(ge=0.0, le=1.0)
    source_location: str | None = None


class ExtractionEvent(FoundryBaseModel):
    """A single event extracted from a source document."""

    event_type: str
    company_name: str
    date: str | None = None
    date_precision: Literal["day", "month", "quarter", "year"] | None = None
    summary: str
    evidence: list[Evidence]
    structured_data: dict = Field(default_factory=dict)


class ExtractionResult(FoundryBaseModel):
    """Complete extraction result for a single source document."""

    source_id: UUID
    source_type: str
    extraction_timestamp: datetime
    events: list[ExtractionEvent]
    meta: dict = Field(default_factory=dict)
