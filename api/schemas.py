# api/schemas.py
from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    query: str = Field(..., description="Natural language query string.")
    transform: bool = Field(
        default=False,
        description=(
            "If true, returns an API-ready payload (startTime, endTime, "
            "propertyFilters, AttributeFilters, etc.). "
            "If false (default), returns the raw NLP pipeline output."
        ),
    )
