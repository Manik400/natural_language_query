MONTH_NAME_TO_NUM = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

WEEKDAY_ORDER = {
    "monday": 1,
    "tuesday": 2,
    "wednesday": 3,
    "thursday": 4,
    "friday": 5,
    "saturday": 6,
    "sunday": 7,
}

QUARTER_BOUNDS = {
    1: ((1, 1), (3, 31)),
    2: ((4, 1), (6, 30)),
    3: ((7, 1), (9, 30)),
    4: ((10, 1), (12, 31)),
}

INTENT_REGISTRY: dict[str, dict[str, dict[str, set]]] = {
    "none": {
        "no_temporal_reference": {"required": set(), "optional": set()},
    },
    "invalid": {
        "incomplete_expression": {"required": set(), "optional": set()},
        "ambiguous_reference": {"required": set(), "optional": set()},
        "conflicting_information": {"required": set(), "optional": set()},
        "malformed_date": {"required": set(), "optional": set()},
    },
    "relative": {
        "current_period": {"required": {"period"}, "optional": set()},
        "rolling_window": {"required": {"n_units", "unit"}, "optional": set()},
        "completed_period": {
            "required": {"period", "n_units"},
            "optional": set(),
        },  # ← added n_units
        "future_window": {"required": {"n_units", "unit"}, "optional": set()},
        "offset_from_anchor_date": {
            "required": {"n_units", "unit", "direction", "anchor_date"},
            "optional": set(),
        },
    },
    "duration": {
        "full_year": {"required": {"d_year"}, "optional": set()},
        "single_month": {"required": {"d_month", "d_year"}, "optional": set()},
        "month_to_month_range": {
            "required": {"d_month", "d_year", "d_month_end", "d_year2"},
            "optional": set(),
        },
    },
    "instant": {
        "today_or_yesterday": {
            "required": {"instant_is_today"},
            "optional": {"raw_time_start", "raw_time_end"},
        },
        "weekday_reference": {
            "required": {"weekday_target", "weekday_modifier"},
            "optional": {"raw_time_start", "raw_time_end"},
        },
        "specific_date": {
            "required": {"instant_date"},
            "optional": {"raw_time_start", "raw_time_end"},
        },
    },
    "absolute": {
        "explicit_date_range": {
            "required": {"abs_start_date", "abs_end_date"},
            "optional": {"raw_time_start", "raw_time_end"},
        },
        "date_to_now_range": {
            "required": {"abs_start_date"},
            "optional": {"raw_time_start"},
        },
    },
}

ALLOWED_VALUES: dict[str, set[str]] = {
    "period": {"day", "week", "month", "quarter", "year"},
    "unit": {"day", "week", "month", "quarter", "year"},
    "direction": {"before", "after"},
    "instant_is_today": {"true", "false"},
    "weekday_target": set(
        WEEKDAY_ORDER.keys()
    ),  # ← wrapped in set() for type consistency
    "d_month": set(MONTH_NAME_TO_NUM.keys()),  # ← wrapped in set() for type consistency
    "d_month_end": set(
        MONTH_NAME_TO_NUM.keys()
    ),  # ← wrapped in set() for type consistency
    "weekday_modifier": {"last", "next", "this"},
}
