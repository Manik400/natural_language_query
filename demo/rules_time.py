"""
Rule-based stand-in for the time LLM classifier (offline mode).

It emits the same JSON the LLM classifier returns
({raw_time_query, timeIntent, timeIntentSubClass, params}) and then reuses the
project's own validator (nodes/time/validate.py) and calendar resolvers
(nodes/time/resolver.py) for the actual date arithmetic.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import re

from nodes.time.dispatcher import dispatch
from nodes.time.run import TimeExtractionFallbackHandler
from nodes.time.utility import build_anchors
from nodes.time.validate import validate_llm_response

_MONTHS = ["january", "february", "march", "april", "may", "june", "july",
           "august", "september", "october", "november", "december"]
_MONTH_BY_ABBR = {m[:3]: m for m in _MONTHS}
_MONTH_NC = (r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|"
             r"aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)")
_MONTH = f"({_MONTH_NC})"
_WEEKDAY = r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
_NUM_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
              "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
              "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30, "sixty": 60,
              "ninety": 90}
_NUM = r"(\d+|" + "|".join(_NUM_WORDS) + r")"
_UNIT = r"(hours?|days?|weeks?|months?|quarters?|years?)"

_DATE_ANY = (r"(?:\d{1,2}[-/.]\d{1,2}[-/.]\d{4}|\d{4}-\d{1,2}-\d{1,2}|"
             rf"\d{{1,2}}(?:st|nd|rd|th)?\s+(?:of\s+)?{_MONTH_NC}\.?,?\s+\d{{4}}|"
             rf"{_MONTH_NC}\.?\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{4}})")
_DATE_PARSERS = [
    (re.compile(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})"), ("d", "m", "y")),
    (re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})"), ("y", "m", "d")),
    (re.compile(rf"(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?{_MONTH}\.?,?\s+(\d{{4}})", re.I), ("d", "M", "y")),
    (re.compile(rf"{_MONTH}\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})", re.I), ("M", "d", "y")),
]

_T = r"(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?"
_TIME_RANGE = re.compile(rf"(?:from|between)?\s*{_T}\s*(?:to|till|until|and|-|–)\s*{_T}", re.I)
_PARTS_OF_DAY = {"morning": ("060000", "115959"), "afternoon": ("120000", "165959"),
                 "evening": ("170000", "205959"), "night": ("210000", "235959"),
                 "tonight": ("210000", "235959")}


class _Invalid(Exception):
    """Raised when a date-looking span is not a real calendar date."""


def _num(token: str) -> int:
    token = token.lower()
    return int(token) if token.isdigit() else _NUM_WORDS[token]


def _unit(token: str) -> str:
    return token.lower().rstrip("s")


def _month(token: str) -> str:
    return _MONTH_BY_ABBR[token.lower()[:3]]


def _parse_date(text: str) -> str:
    """Any supported date spelling → 'DD-MM-YYYY'. Raises _Invalid for impossible dates."""
    for pattern, order in _DATE_PARSERS:
        m = pattern.fullmatch(text.strip())
        if not m:
            continue
        parts = dict(zip(order, m.groups()))
        month = MONTH_NUM[_month(parts["M"])] if "M" in parts else int(parts["m"])
        try:
            date = dt.date(int(parts["y"]), month, int(parts["d"]))
        except ValueError as e:
            raise _Invalid(text) from e
        return date.strftime("%d-%m-%Y")
    raise _Invalid(text)


MONTH_NUM = {m: i for i, m in enumerate(_MONTHS, 1)}


def _to_hhmmss(hour: str, minute: str | None, ampm: str | None) -> str:
    h, m = int(hour), int(minute or 0)
    ap = (ampm or "").replace(".", "").lower()
    if ap == "pm" and h < 12:
        h += 12
    elif ap == "am" and h == 12:
        h = 0
    return f"{h:02d}{m:02d}00"


def _time_window(q: str) -> tuple[dict, str | None]:
    """Find a time-of-day window like '9am to 5pm' or 'evening'."""
    for m in _TIME_RANGE.finditer(q):
        h1, m1, ap1, h2, m2, ap2 = m.groups()
        if not (ap1 or ap2 or m1 or m2):
            continue  # "2 to 3" without am/pm or minutes is not a time
        if ap2 and not ap1 and int(h1) <= int(h2):
            ap1 = ap2
        start, end = _to_hhmmss(h1, m1, ap1), _to_hhmmss(h2, m2, ap2)
        if int(start[:2]) > 23 or int(end[:2]) > 23:
            continue
        return {"raw_time_start": start, "raw_time_end": end}, m.group(0).strip()
    for word, (start, end) in _PARTS_OF_DAY.items():
        if re.search(rf"\b{word}\b", q, re.I):
            return {"raw_time_start": start, "raw_time_end": end}, word
    return {}, None


def _intent(raw, intent, subclass, params=None) -> dict:
    return {"raw_time_query": raw, "timeIntent": intent,
            "timeIntentSubClass": subclass, "params": params}


def classify(query: str, today: dt.date | None = None) -> dict:
    """Return the LLM-classifier-shaped dict for *query*."""
    today = today or dt.date.today()
    q = query
    window, window_raw = _time_window(q)

    def with_window(raw, intent, subclass, params):
        if window:
            params = {**params, **window}
            raw = f"{raw} {window_raw}"
        return _intent(raw, intent, subclass, params)

    try:
        # ── Absolute: explicit ranges and "since" ────────────────────────────
        m = re.search(rf"(?:from|between)?\s*({_DATE_ANY})\s*(?:to|till|until|through|and|-|–)\s*({_DATE_ANY})", q, re.I)
        if m:
            return with_window(m.group(0).strip(), "absolute", "explicit_date_range",
                               {"abs_start_date": _parse_date(m.group(1)),
                                "abs_end_date": _parse_date(m.group(2))})
        m = re.search(rf"(?:since|from)\s+({_DATE_ANY})(?:\s+(?:to|till|until)\s+(?:now|today))?", q, re.I)
        if m:
            return _intent(m.group(0).strip(), "absolute", "date_to_now_range",
                           {"abs_start_date": _parse_date(m.group(1))})

        # ── Offset from an anchor date ───────────────────────────────────────
        m = re.search(rf"\b{_NUM}\s+{_UNIT}\s+(before|after)\s+({_DATE_ANY})", q, re.I)
        if m and _unit(m.group(2)) in ("day", "week", "month", "year"):
            return _intent(m.group(0), "relative", "offset_from_anchor_date",
                           {"n_units": str(_num(m.group(1))), "unit": _unit(m.group(2)),
                            "direction": m.group(3).lower(), "anchor_date": _parse_date(m.group(4))})

        # ── Single explicit date ─────────────────────────────────────────────
        m = re.search(rf"\b({_DATE_ANY})", q, re.I)
        if m:
            return with_window(m.group(0), "instant", "specific_date",
                               {"instant_date": _parse_date(m.group(1))})
    except _Invalid:
        return _intent(query, "invalid", "malformed_date")

    # ── Month to month ───────────────────────────────────────────────────────
    m = re.search(rf"\b{_MONTH}(?:\s+(\d{{4}}))?\s+(?:to|till|until|through|-|–)\s+{_MONTH}\s+(\d{{4}})\b", q, re.I)
    if m:
        return _intent(m.group(0), "duration", "month_to_month_range",
                       {"d_month": _month(m.group(1)), "d_year": m.group(2) or m.group(4),
                        "d_month_end": _month(m.group(3)), "d_year2": m.group(4)})

    # ── Today / yesterday / weekday ──────────────────────────────────────────
    m = re.search(r"\b(today|yesterday|tonight|this (?:morning|afternoon|evening))\b", q, re.I)
    if m:
        is_today = "yesterday" not in m.group(1).lower()
        return with_window(m.group(0), "instant", "today_or_yesterday",
                           {"instant_is_today": "true" if is_today else "false"})
    m = re.search(rf"\b(?:(last|previous|next|this|coming|on)\s+)?{_WEEKDAY}s?\b", q, re.I)
    if m:
        modifier = {"previous": "last", "coming": "next", "on": "this", None: "this"}.get(
            (m.group(1) or "").lower() or None, (m.group(1) or "this").lower())
        return with_window(m.group(0), "instant", "weekday_reference",
                           {"weekday_target": m.group(2).lower(), "weekday_modifier": modifier})

    # ── Relative windows ─────────────────────────────────────────────────────
    m = re.search(rf"\b(?:last|past|previous)\s+{_NUM}\s+hours?\b", q, re.I)
    if m:
        days = max(1, math.ceil(_num(m.group(1)) / 24))
        return _intent(m.group(0), "relative", "rolling_window", {"n_units": str(days), "unit": "day"})
    m = re.search(rf"\bpast\s+(?:{_NUM}\s+)?{_UNIT}\b", q, re.I) or re.search(rf"\blast\s+{_NUM}\s+{_UNIT}\b", q, re.I)
    if m and _unit(m.group(2)) != "hour":
        return _intent(m.group(0), "relative", "rolling_window",
                       {"n_units": str(_num(m.group(1) or "1")), "unit": _unit(m.group(2))})
    m = re.search(rf"\bprevious\s+(?:{_NUM}\s+)?{_UNIT}\b", q, re.I)
    if m and _unit(m.group(2)) != "hour":
        return _intent(m.group(0), "relative", "completed_period",
                       {"period": _unit(m.group(2)), "n_units": str(_num(m.group(1) or "1"))})
    m = re.search(rf"\blast\s+{_UNIT}\b", q, re.I)
    if m and _unit(m.group(1)) != "hour":
        return _intent(m.group(0), "relative", "completed_period",
                       {"period": _unit(m.group(1)), "n_units": "1"})
    m = re.search(rf"\b(?:this|current|so\s+far\s+this)\s+{_UNIT}\b", q, re.I)
    if m and _unit(m.group(1)) != "hour":
        return _intent(m.group(0), "relative", "current_period", {"period": _unit(m.group(1))})
    m = re.search(r"\b(week|month|year)[\s-]to[\s-]date\b|\b(wtd|mtd|ytd)\b", q, re.I)
    if m:
        period = (m.group(1) or {"wtd": "week", "mtd": "month", "ytd": "year"}[m.group(2).lower()]).lower()
        return _intent(m.group(0), "relative", "current_period", {"period": period})
    m = re.search(rf"\b(?:next|upcoming|coming)\s+(?:{_NUM}\s+)?{_UNIT}\b", q, re.I)
    if m and _unit(m.group(2)) != "hour":
        return _intent(m.group(0), "relative", "future_window",
                       {"n_units": str(_num(m.group(1) or "1")), "unit": _unit(m.group(2))})

    # ── Named month / year ───────────────────────────────────────────────────
    m = re.search(rf"\b{_MONTH}\s*,?\s*((?:19|20)\d{{2}})\b", q, re.I)
    if m:
        return _intent(m.group(0), "duration", "single_month",
                       {"d_month": _month(m.group(1)), "d_year": m.group(2)})
    m = re.search(rf"\b(?:in|during|for|of|throughout)\s+{_MONTH}\b", q, re.I)
    if m:
        return _intent(m.group(0), "duration", "single_month",
                       {"d_month": _month(m.group(1)), "d_year": str(today.year)})
    m = re.search(r"\b(?:in|during|for|of|year|throughout|all\s+of)\s+((?:19|20)\d{2})\b", q, re.I)
    if m:
        return _intent(m.group(0), "duration", "full_year", {"d_year": m.group(1)})

    return _intent(None, "none", "no_temporal_reference")


def extract_time(query: str, now: dt.datetime | None = None) -> dict:
    """Same result shape as nodes.time.run.time_extraction_with_error_handling()."""
    now = now or dt.datetime.now()
    classified = {"user_query": query, **classify(query, now.date())}
    validation = validate_llm_response(json.dumps(classified))
    fallback = TimeExtractionFallbackHandler().get_default_fallback()
    if not validation.success:
        return {**fallback, "llm_response": classified,
                "validation": {"success": False, "errors": validation.errors}}
    result = dispatch(validation, build_anchors(now))
    resolved = result.get("resolved")
    if not result.get("success") or resolved is None:
        return {**fallback, "llm_response": classified}
    return {
        "llm_response": classified,
        "validation": {"success": True, "errors": []},
        "resolved": {"start": resolved.start, "end": resolved.end},
        "error": None,
    }
