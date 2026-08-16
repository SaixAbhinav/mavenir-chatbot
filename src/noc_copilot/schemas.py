"""The contract the model must satisfy."""
from __future__ import annotations

from pydantic import BaseModel, Field


class Citation(BaseModel):
    clause_id: str = Field(description="Clause id exactly as given, e.g. 5.3.5.3")
    supporting_quote: str = Field(
        description="A span copied verbatim from that clause's text"
    )


class Answer(BaseModel):
    answer: str
    sufficient: bool = Field(
        description="False if the provided clauses do not contain the answer"
    )
    answerable_from_standards: bool = Field(
        description="False if this asks about a live network rather than the standards"
    )
    citations: list[Citation] = Field(default_factory=list)
