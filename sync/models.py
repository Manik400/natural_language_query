from enum import IntEnum
from typing import List

from pydantic import BaseModel, field_serializer

# ─────────────────────────────────────────────
# RuleType Enum
# ─────────────────────────────────────────────


class RuleType(IntEnum):
    number = 0
    string = 1
    float = 2
    boolean = 3
    ipAddress = 4
    dateTime = 5
    image = 6
    date = 7
    timeOfDay = 8
    dayOfWeek = 9
    imagePath = 10
    unixDateTime = 11
    filePath = 12
    array = 13
    custom = 14
    vector = 18
    guid = 19
    ArrayOfObject = 21
    Double = 23
    dateRange = 24


# ─────────────────────────────────────────────
# RuleType → JSON Schema type mapping
# ─────────────────────────────────────────────

RULETYPE_TO_JSON: dict[int, tuple[str, str | None]] = {
    RuleType.number: ("number", None),
    RuleType.string: ("string", None),
    RuleType.float: ("number", None),
    RuleType.boolean: ("boolean", None),
    RuleType.ipAddress: ("string", "ipv4"),
    RuleType.dateTime: ("string", "date-time"),
    RuleType.image: ("string", "uri"),
    RuleType.date: ("string", "date"),
    RuleType.timeOfDay: ("string", "time"),
    RuleType.dayOfWeek: ("string", None),
    RuleType.imagePath: ("string", "uri-reference"),
    RuleType.unixDateTime: ("integer", None),
    RuleType.filePath: ("string", "uri-reference"),
    RuleType.array: ("array", None),
    RuleType.custom: ("object", None),
    RuleType.vector: ("array", None),
    RuleType.guid: ("string", "uuid"),
    RuleType.ArrayOfObject: ("array", None),
    RuleType.Double: ("number", None),
    RuleType.dateRange: ("object", None),
}

# ─────────────────────────────────────────────
# Request / Response Models
# ─────────────────────────────────────────────


class VideoResource(BaseModel):
    id: str
    name: str
    ip: str
    type: str


class EventProperty(BaseModel):
    name: str
    type: RuleType


class EventSchema(BaseModel):
    name: str
    properties: List[EventProperty]


class AttributeValueType(IntEnum):
    string = 0
    number = 1
    boolean = 2


class Attribute(BaseModel):
    key: str
    valueType: AttributeValueType

    @field_serializer("valueType")
    def serialize_value_type(self, value: AttributeValueType) -> str:
        return value.name
