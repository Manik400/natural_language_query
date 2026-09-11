from __future__ import annotations

from typing import Any

from pydantic import BaseModel, field_serializer

from .constants import AttributeValueType, ConditionType, Operators


class Attribute(BaseModel):
    key: str
    valueType: AttributeValueType

    @field_serializer("valueType")
    def serialize_value_type(self, value: AttributeValueType) -> str:
        return value.name


class AttributeExtractionResult(BaseModel):
    key: str
    valueType: AttributeValueType
    operator: Operators
    value: Any
    raw_slice: str

    @field_serializer("operator")
    def serialize_operator(self, value: Operators) -> str:
        return value.name

    @field_serializer("valueType")
    def serialize_value_type(self, value: AttributeValueType) -> str:
        return value.name


class ExtractionResult(BaseModel):
    conditionType: ConditionType | None = None
    conditions: list[AttributeExtractionResult] = []  # ← was `Condition`, undefined

    @field_serializer("conditionType")
    def serialize_condition_type(self, value: ConditionType | None) -> str | None:
        return value.name if value is not None else None  # ← guard for None
