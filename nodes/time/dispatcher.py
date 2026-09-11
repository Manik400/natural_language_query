from __future__ import annotations

from typing import Callable

from .models import Anchors, ParsedIntent, ResolvedDateTime, ValidationResult
from .resolver import (
    resolve_completed_period,
    resolve_current_period,
    resolve_date_to_now_range,
    resolve_explicit_date_range,
    resolve_full_year,
    resolve_future_window,
    resolve_month_to_month_range,
    resolve_null,
    resolve_offset_from_anchor_date,
    resolve_rolling_window,
    resolve_single_month,
    resolve_specific_date,
    resolve_today_or_yesterday,
    resolve_weekday_reference,
)

ResolverFn = Callable[[ParsedIntent, Anchors], ResolvedDateTime]

DISPATCHER: dict[str, dict[str, ResolverFn]] = {
    "none": {
        "no_temporal_reference": resolve_null,
    },
    "invalid": {
        "incomplete_expression": resolve_null,
        "ambiguous_reference": resolve_null,
        "conflicting_information": resolve_null,
        "malformed_date": resolve_null,
    },
    "relative": {
        "current_period": resolve_current_period,
        "rolling_window": resolve_rolling_window,
        "completed_period": resolve_completed_period,
        "future_window": resolve_future_window,
        "offset_from_anchor_date": resolve_offset_from_anchor_date,
    },
    "duration": {
        "full_year": resolve_full_year,
        "single_month": resolve_single_month,
        "month_to_month_range": resolve_month_to_month_range,
    },
    "instant": {
        "today_or_yesterday": resolve_today_or_yesterday,
        "weekday_reference": resolve_weekday_reference,
        "specific_date": resolve_specific_date,
    },
    "absolute": {
        "explicit_date_range": resolve_explicit_date_range,
        "date_to_now_range": resolve_date_to_now_range,
    },
}


def dispatch(result: ValidationResult, anchors: Anchors) -> dict:
    if not result.success:
        return {"success": False, "errors": result.errors, "resolved": None}

    intent = result.parsed.timeIntent
    subclass = result.parsed.timeIntentSubClass
    resolver = DISPATCHER.get(intent, {}).get(subclass)

    if resolver is None:
        return {
            "success": False,
            "errors": [f"No resolver for intent={intent!r} subclass={subclass!r}"],
            "resolved": None,
        }

    return {"success": True, "errors": [], "resolved": resolver(result.parsed, anchors)}
