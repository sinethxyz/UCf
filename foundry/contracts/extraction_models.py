"""Pydantic models for signal extraction: events, evidence, and results."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from foundry.contracts.shared import (
    EvidenceStrength,
    EventType,
    FoundryBaseModel,
)


class Evidence(FoundryBaseModel):
    """An evidence object attached to an extracted event.

    Each piece of evidence links a claim back to the source material
    with a confidence score and strength classification.
    """

    type: EvidenceStrength = Field(
        description="How directly this evidence supports the event."
    )
    quote: str = Field(
        max_length=100,
        description="Verbatim quote from the source, max 100 characters.",
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score between 0.0 and 1.0.",
    )
    source_location: str = Field(
        description="Where in the source document this evidence was found.",
    )


class ExtractionEvent(FoundryBaseModel):
    """A single event extracted from a source document.

    Represents a discrete startup signal (funding, hire, launch, etc.)
    with structured data and supporting evidence.
    """

    event_type: EventType = Field(description="The category of startup event.")
    company_name: str = Field(description="Name of the company this event relates to.")
    date: str = Field(description="Date of the event in ISO 8601 format.")
    date_precision: Literal["day", "month", "year", "unknown"] = Field(
        description="How precise the extracted date is."
    )
    summary: str = Field(description="Brief human-readable summary of the event.")
    evidence: list[Evidence] = Field(
        description="Evidence supporting this event extraction."
    )
    structured_data: dict = Field(
        default_factory=dict,
        description="Event-type-specific structured fields (e.g. amount, role, product name).",
    )


class ExtractionResult(FoundryBaseModel):
    """Complete extraction result for a single source document.

    Contains all events extracted from one source, along with metadata
    about the extraction process.
    """

    source_id: UUID = Field(description="Identifier of the source document.")
    source_type: str = Field(
        description="Type of source (e.g. 'news_article', 'press_release', 'sec_filing')."
    )
    extraction_timestamp: datetime = Field(
        description="When the extraction was performed."
    )
    events: list[ExtractionEvent] = Field(
        description="All events extracted from this source."
    )


class ExtractionClassification(FoundryBaseModel):
    """Pre-extraction classification of a source document.

    Used by the classification step to triage sources before full
    extraction, estimating complexity and relevance.
    """

    source_type: str = Field(
        description="Classified type of the source document."
    )
    complexity: Literal["simple", "complex"] = Field(
        description="Whether the source requires simple or complex extraction."
    )
    estimated_event_count: int = Field(
        ge=0,
        description="Estimated number of events in the source.",
    )
    language: str = Field(
        description="Detected language of the source document (ISO 639-1 code)."
    )
    is_relevant: bool = Field(
        description="Whether the source contains relevant startup signals."
    )
