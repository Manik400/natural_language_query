"""
validation.py — Registry and logical validation for the DateTime Intent Engine.
"""

from __future__ import annotations

import re

from .constants import ALLOWED_VALUES, INTENT_REGISTRY, MONTH_NAME_TO_NUM
from .models import ParsedIntent, ValidationResult
from .parser import parse_llm_output

_DATE_RE = re.compile(r"^\d{2}-\d{2}-\d{4}$")
_TIME_RE = re.compile(r"^\d{6}$")
_YEAR_RE = re.compile(r"^\d{4}$")
_DIGITS_RE = re.compile(r"^\d+$")

# subclasses where start and end are always the same date
# → time ordering must be enforced
_SAME_DATE_SUBCLASSES = {
    "today_or_yesterday",
    "weekday_reference",
    "specific_date",
}


# ── Registry ──────────────────────────────────────────────────────────────────


def _validate_registry(parsed: ParsedIntent, errors: list[str]) -> None:
    intent = parsed.timeIntent
    subclass = parsed.timeIntentSubClass

    if intent not in INTENT_REGISTRY:
        errors.append(f"Unknown timeIntent: {intent!r}")
        return

    if subclass not in INTENT_REGISTRY[intent]:
        errors.append(f"Unknown timeIntentSubClass {subclass!r} for intent {intent!r}")
        return

    meta = INTENT_REGISTRY[intent][subclass]
    required = meta["required"]
    optional = meta["optional"]

    if intent in ("none", "invalid"):
        if parsed.params is not None:
            errors.append(f"params must be null for intent {intent!r}")
        return

    if not isinstance(parsed.params, dict):
        errors.append(f"params must be an object for intent {intent!r}")
        return

    for param in required:
        val = parsed.params.get(param)
        if val is None:
            errors.append(f"Missing required param: {param!r}")
        elif val == "":
            errors.append(f"Required param {param!r} must not be empty string")

    unexpected = set(parsed.params.keys()) - (required | optional)
    if unexpected:
        errors.append(f"Unexpected params: {sorted(unexpected)}")

    # ── completed_period: n_units must be a positive-integer string ───────────  ◄ NEW
    # rolling_window already had this enforced in _validate_logical via _DIGITS_RE.
    # completed_period now also carries n_units (e.g. "1" for "last week",
    # "3" for "previous 3 months"), so we enforce the same contract here at
    # registry level before _validate_logical runs, giving a clear early error.
    if subclass == "completed_period" and isinstance(parsed.params, dict):  # ◄ NEW
        n = parsed.params.get("n_units")  # ◄ NEW
        if (
            n is not None and n != ""
        ):  # empty / missing already caught above     # ◄ NEW
            if not str(n).isdigit() or int(n) < 1:  # ◄ NEW
                errors.append(  # ◄ NEW
                    f"completed_period: n_units must be a digits-only string "  # ◄ NEW
                    f"> 0, got {n!r}"  # ◄ NEW
                )  # ◄ NEW


# ── Field-level helpers ───────────────────────────────────────────────────────


def _validate_date(val: str, field: str, errors: list[str]) -> None:
    if not _DATE_RE.match(val):
        errors.append(f"{field}: expected DD-MM-YYYY, got {val!r}")
        return
    dd, mm = int(val[:2]), int(val[3:5])
    if not (1 <= mm <= 12):
        errors.append(f"{field}: month {mm} out of range")
    if not (1 <= dd <= 31):
        errors.append(f"{field}: day {dd} out of range")


def _validate_time_field(val: str, field: str, errors: list[str]) -> None:
    if not _TIME_RE.match(val):
        errors.append(f"{field}: expected HHMMSS, got {val!r}")
        return
    hh, mm, ss = int(val[:2]), int(val[2:4]), int(val[4:])
    if not (0 <= hh <= 23):
        errors.append(f"{field}: hour {hh} out of range")
    if not (0 <= mm <= 59):
        errors.append(f"{field}: minute {mm} out of range")
    if not (0 <= ss <= 59):
        errors.append(f"{field}: second {ss} out of range")


def _dates_are_equal(d: dict) -> bool | None:
    """
    For explicit_date_range: check whether abs_start_date == abs_end_date.
    Returns True  → same date, time ordering must hold.
    Returns False → different dates, time ordering is irrelevant.
    Returns None  → cannot determine (dates missing or malformed).
    """
    s = d.get("abs_start_date")
    e = d.get("abs_end_date")
    if not s or not e:
        return None
    if not (_DATE_RE.match(s) and _DATE_RE.match(e)):
        return None
    return s == e


# ── Logical ───────────────────────────────────────────────────────────────────


def _validate_logical(parsed: ParsedIntent, errors: list[str]) -> None:
    if not isinstance(parsed.params, dict):
        return

    d = parsed.params
    subclass = parsed.timeIntentSubClass

    # Per-field checks
    for fname, val in d.items():
        if val is None:
            continue
        if fname in ALLOWED_VALUES and val not in ALLOWED_VALUES[fname]:
            errors.append(f"{fname}: {val!r} not in {sorted(ALLOWED_VALUES[fname])}")
        if fname in ("d_year", "d_year2") and not _YEAR_RE.match(str(val)):
            errors.append(f"{fname}: expected 4-digit year, got {val!r}")
        if fname == "n_units":
            if not _DIGITS_RE.match(str(val)):
                errors.append(f"n_units: expected digits only, got {val!r}")
            elif int(val) <= 0:
                errors.append(f"n_units: must be > 0, got {val!r}")
        if fname in ("anchor_date", "instant_date", "abs_start_date", "abs_end_date"):
            _validate_date(str(val), fname, errors)
        if fname in ("raw_time_start", "raw_time_end"):
            _validate_time_field(str(val), fname, errors)

    # ── Cross-field: time ordering ────────────────────────────────────────────
    ts = d.get("raw_time_start")
    te = d.get("raw_time_end")

    if ts and te and _TIME_RE.match(ts) and _TIME_RE.match(te):

        if subclass in _SAME_DATE_SUBCLASSES:
            # start and end are always the same date → time order must hold
            if te <= ts:
                errors.append(
                    f"raw_time_end {te!r} must be after raw_time_start {ts!r}"
                )

        elif subclass == "explicit_date_range":
            # time order only matters when start date == end date
            same = _dates_are_equal(d)
            if same is True and te <= ts:
                errors.append(
                    f"raw_time_end {te!r} must be after raw_time_start {ts!r} "
                    f"when abs_start_date == abs_end_date"
                )
            # same is False → different dates, any time combination is valid
            # same is None  → dates missing/malformed, already caught above

        elif subclass == "date_to_now_range":
            # only raw_time_start exists for this subclass, no end time to compare
            pass

    # ── Cross-field: explicit_date_range date ordering ────────────────────────
    if subclass == "explicit_date_range":
        s, e = d.get("abs_start_date"), d.get("abs_end_date")
        if s and e and _DATE_RE.match(s) and _DATE_RE.match(e):
            if (s[6:] + s[3:5] + s[:2]) > (e[6:] + e[3:5] + e[:2]):
                errors.append(f"abs_end_date {e!r} is before abs_start_date {s!r}")

    # ── Cross-field: month_to_month_range ordering ────────────────────────────
    if subclass == "month_to_month_range":
        ms, ys = d.get("d_month"), d.get("d_year")
        me, ye = d.get("d_month_end"), d.get("d_year2")
        if all([ms, ys, me, ye]):
            s_ord = int(ys) * 12 + MONTH_NAME_TO_NUM.get(ms, 0)
            e_ord = int(ye) * 12 + MONTH_NAME_TO_NUM.get(me, 0)
            if e_ord < s_ord:
                errors.append(
                    f"month_to_month_range: end ({me} {ye}) is before start ({ms} {ys})"
                )


# ── Public entry point ────────────────────────────────────────────────────────


def validate_llm_response(raw_output: str) -> ValidationResult:
    """
    Full validation pipeline:
      parse + envelope (PydanticOutputParser) → registry → logical
    """
    errors: list[str] = []

    # Step 1: parse + envelope via PydanticOutputParser
    parsed, parse_error = parse_llm_output(raw_output)
    if parse_error:
        return ValidationResult(success=False, parsed=None, errors=[parse_error])

    # Step 2: registry check
    _validate_registry(parsed, errors)
    if errors:
        return ValidationResult(success=False, parsed=parsed, errors=errors)

    # Step 3: logical check
    _validate_logical(parsed, errors)

    return ValidationResult(success=len(errors) == 0, parsed=parsed, errors=errors)
