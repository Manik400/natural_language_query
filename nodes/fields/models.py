from typing import Any

from pydantic import BaseModel


class MatchedEvent(BaseModel):
    event_name: str
    query_part: str


class MatchedEventsResponse(BaseModel):
    status: str
    matched_events: list[MatchedEvent]


class RelevantField(BaseModel):
    field: str
    operator: str | None
    value: Any
    query_snippet: str | None
    valid: bool | None = None
    error: str | None = None


class EventFieldResult(BaseModel):
    event_name: str
    query_part: str
    relevant_fields: list[RelevantField]
