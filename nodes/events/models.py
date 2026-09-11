from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class MatchedEvent(BaseModel):
    event_name: str = Field(..., description="Name of the matched event")
    query_part: str = Field(
        ..., description="Exact raw query span that triggered this event"
    )


class MatchedEvents(BaseModel):
    matched_events: List[MatchedEvent] = Field(
        default_factory=list,
        description="List of matched events with their triggering query spans",
    )
