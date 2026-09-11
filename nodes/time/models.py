from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from .constants import WEEKDAY_ORDER


@dataclass
class Anchors:
    """Runtime canonical anchors injected by the caller."""

    current_date: str  # "dd mm yyyy"  (normalised to DD-MM-YYYY on init)
    current_time: str  # "HH:MM:SS"
    current_weekday: str  # "monday" … "sunday"

    def __post_init__(self):
        # Normalise "dd mm yyyy" → "DD-MM-YYYY" so it's safe to pass into _make directly
        parts = self.current_date.strip().split()
        if len(parts) == 3:
            self.current_date = f"{parts[0].zfill(2)}-{parts[1].zfill(2)}-{parts[2]}"

    def day(self) -> int:
        return int(self.current_date.split("-")[0])

    def month(self) -> int:
        return int(self.current_date.split("-")[1])

    def year(self) -> int:
        return int(self.current_date.split("-")[2])

    def weekday_num(self) -> int:
        return WEEKDAY_ORDER[self.current_weekday.lower()]


class ParsedIntent(BaseModel):
    """
    Structured representation of the LLM classifier output.
    Used directly as the PydanticOutputParser target.

    All four fields must be present in the JSON:
      - raw_time_query     : required key, value can be null
      - timeIntent         : required key, value must be non-null string
      - timeIntentSubClass : required key, value must be non-null string
      - params             : required key, value can be null
    """

    raw_time_query: Optional[str] = Field(
        ..., description="Verbatim temporal substring or null if no temporal reference"
    )
    timeIntent: str = Field(..., description="Top-level intent category")
    timeIntentSubClass: str = Field(
        ..., description="Specific subclass within the intent"
    )
    params: Optional[Dict[str, Any]] = Field(
        ..., description="Subclass-specific parameters or null for none/invalid intents"
    )

    def p(self) -> Dict[str, Any]:
        """Safe accessor — returns empty dict when params is null."""
        return self.params or {}


@dataclass
class ValidationResult:
    """Output of the validation pipeline."""

    success: bool
    parsed: Optional[ParsedIntent]
    errors: list[str]


@dataclass
class TimeRange:
    start_time: Optional[str] = None
    end_time: Optional[str] = None


@dataclass
class ResolvedDateTime:
    """Final resolved date/time range returned by a resolver."""

    raw: str
    timeIntent: str
    timeIntentSubClass: str
    start: Dict[str, Optional[str]] = field(
        default_factory=lambda: {"date": None, "time": None}
    )
    end: Dict[str, Optional[str]] = field(
        default_factory=lambda: {"date": None, "time": None}
    )
    reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        out = {
            "raw": self.raw,
            "timeIntent": self.timeIntent,
            "timeIntentSubClass": self.timeIntentSubClass,
            "start": self.start,
            "end": self.end,
        }

        return out
