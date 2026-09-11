"""
resolvers.py — One resolver per timeIntentSubClass.
All calendar logic lives here; no date computation in the LLM.
"""

from __future__ import annotations

import calendar
import datetime as dt

from .constants import MONTH_NAME_TO_NUM, QUARTER_BOUNDS, WEEKDAY_ORDER
from .models import Anchors, ParsedIntent, ResolvedDateTime

# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------

_START_TIME = "00:00:00"
_END_OF_DAY = "23:59:59"


# ---------------------------------------------------------------------------
# UTILITIES
# ---------------------------------------------------------------------------


def _fmt(d: int, m: int, y: int) -> str:
    return f"{d:02d}-{m:02d}-{y:04d}"


def _month_last_day(m: int, y: int) -> int:
    return calendar.monthrange(y, m)[1]


def _add_days(d: int, m: int, y: int, n: int) -> tuple[int, int, int]:
    date = dt.date(y, m, d) + dt.timedelta(days=n)
    return date.day, date.month, date.year


def _add_months(d: int, m: int, y: int, n: int) -> tuple[int, int, int]:
    total = m - 1 + n
    ny = y + total // 12
    nm = total % 12 + 1
    nd = min(d, _month_last_day(nm, ny))
    return nd, nm, ny


def _apply_unit(d: int, m: int, y: int, n: int, unit: str) -> tuple[int, int, int]:
    u = unit.lower().rstrip("s")
    if u == "day":
        return _add_days(d, m, y, n)
    if u == "week":
        return _add_days(d, m, y, n * 7)
    if u == "month":
        return _add_months(d, m, y, n)
    if u == "quarter":
        return _add_months(d, m, y, n * 3)
    if u == "year":
        return _add_months(d, m, y, n * 12)
    return d, m, y


def _parse_hhmmss(raw: str | None) -> str | None:
    """HHMMSS → HH:MM:SS, or None."""
    if not raw or len(raw) != 6 or not raw.isdigit():
        return None
    return f"{raw[:2]}:{raw[2:4]}:{raw[4:]}"


def _time_range(p: ParsedIntent) -> tuple[str | None, str | None]:
    return (
        _parse_hhmmss(p.p().get("raw_time_start")),
        _parse_hhmmss(p.p().get("raw_time_end")),
    )


def _is_current_date(date_str: str, anchors: Anchors) -> bool:
    """True when the resolved date is today."""
    return date_str == anchors.current_date


def _end_time(date_str: str, anchors: Anchors) -> str:
    """
    Determine end time based on whether the date is today or in the past.
      today → anchors.current_time  (open-ended, up to now)
      past  → 23:59:59              (full closed day)
    """
    return anchors.current_time if _is_current_date(date_str, anchors) else _END_OF_DAY


def _make(
    p: ParsedIntent,
    start_date: str | None,
    start_time: str | None,
    end_date: str | None,
    end_time: str | None,
) -> ResolvedDateTime:
    return ResolvedDateTime(
        raw=p.raw_time_query,
        timeIntent=p.timeIntent,
        timeIntentSubClass=p.timeIntentSubClass,
        start={"date": start_date, "time": start_time},
        end={"date": end_date, "time": end_time},
    )


def _yesterday(anchors: Anchors) -> str:
    yd, ym, yy = _add_days(anchors.day(), anchors.month(), anchors.year(), -1)
    return _fmt(yd, ym, yy)


# ---------------------------------------------------------------------------
# NONE / INVALID
# ---------------------------------------------------------------------------


def resolve_null(p: ParsedIntent, anchors: Anchors) -> ResolvedDateTime:
    d, m, y = anchors.day(), anchors.month(), anchors.year()
    return _make(p, _fmt(d, m, y), _START_TIME, _fmt(d, m, y), anchors.current_time)


# ---------------------------------------------------------------------------
# RELATIVE
# ---------------------------------------------------------------------------


def resolve_current_period(p: ParsedIntent, anchors: Anchors) -> ResolvedDateTime:
    """
    R1 — In-progress calendar period containing today.
    start_time = 00:00:00   end_time = current_time (always ends now)

    period = "day"     → start = today
    period = "week"    → start = monday of this week
    period = "month"   → start = 1st of this month
    period = "quarter" → start = 1st of this quarter
    period = "year"    → start = 1 Jan this year
    """
    d, m, y = anchors.day(), anchors.month(), anchors.year()
    period = p.p().get("period", "")

    if period == "day":
        start_date = anchors.current_date

    elif period == "week":
        sd, sm, sy = _add_days(d, m, y, -(anchors.weekday_num() - 1))
        start_date = _fmt(sd, sm, sy)

    elif period == "month":
        start_date = _fmt(1, m, y)

    elif period == "quarter":
        cq = (m - 1) // 3 + 1
        (sm_, sd_), _ = QUARTER_BOUNDS[cq]
        start_date = _fmt(sd_, sm_, y)

    elif period == "year":
        start_date = _fmt(1, 1, y)

    else:
        start_date = anchors.current_date

    return _make(p, start_date, _START_TIME, anchors.current_date, anchors.current_time)


def resolve_rolling_window(p: ParsedIntent, anchors: Anchors) -> ResolvedDateTime:
    """
    R2 — Sliding N-unit window ending now.
    start_time = 00:00:00   end_time = current_time
    """
    d, m, y = anchors.day(), anchors.month(), anchors.year()
    n = int(p.p().get("n_units"))
    unit = p.p().get("unit")
    sd, sm, sy = _apply_unit(d, m, y, -n, unit)
    return _make(
        p, _fmt(sd, sm, sy), _START_TIME, anchors.current_date, anchors.current_time
    )


def resolve_completed_period(p: ParsedIntent, anchors: Anchors) -> ResolvedDateTime:
    """
    R3 — Most recently finished discrete calendar period.
    start_time = 00:00:00   end_time = 23:59:59 (full closed period)

    period = "day"     → start = yesterday,          end = yesterday
    period = "week"    → start = last Monday,         end = last Sunday
    period = "month"   → start = 1st of prev month,  end = last day of prev month
    period = "quarter" → start = 1st of prev quarter, end = last day of prev quarter
    period = "year"    → start = 1 Jan prev year,     end = 31 Dec prev year
    """
    d, m, y = anchors.day(), anchors.month(), anchors.year()
    period = p.p().get("period", "")

    if period == "day":
        yesterday = _yesterday(anchors)
        start_date = yesterday
        end_date = yesterday

    elif period == "week":
        wn = anchors.weekday_num()
        ed, em, ey = _add_days(d, m, y, -wn)
        sd, sm, sy = _add_days(d, m, y, -(wn + 6))
        start_date = _fmt(sd, sm, sy)
        end_date = _fmt(ed, em, ey)

    elif period == "month":
        pm, py = (12, y - 1) if m == 1 else (m - 1, y)
        start_date = _fmt(1, pm, py)
        end_date = _fmt(_month_last_day(pm, py), pm, py)

    elif period == "year":
        start_date = _fmt(1, 1, y - 1)
        end_date = _fmt(31, 12, y - 1)

    elif period == "quarter":
        cq = (m - 1) // 3 + 1
        pq = cq - 1 if cq > 1 else 4
        qy = y if cq > 1 else y - 1
        (sm_, sd_), (em_, ed_) = QUARTER_BOUNDS[pq]
        start_date = _fmt(sd_, sm_, qy)
        end_date = _fmt(_month_last_day(em_, qy), em_, qy)

    else:
        start_date = end_date = anchors.current_date

    return _make(p, start_date, _START_TIME, end_date, _END_OF_DAY)


def resolve_future_window(p: ParsedIntent, anchors: Anchors) -> ResolvedDateTime:
    """
    R4 — Forward-looking N-unit window starting from today.
    start_time = current_time   end_time = 23:59:59
    """
    d, m, y = anchors.day(), anchors.month(), anchors.year()
    n = int(p.p().get("n_units"))
    unit = p.p().get("unit")
    ed, em, ey = _apply_unit(d, m, y, n, unit)
    return _make(
        p, anchors.current_date, anchors.current_time, _fmt(ed, em, ey), _END_OF_DAY
    )


def resolve_offset_from_anchor_date(
    p: ParsedIntent, anchors: Anchors
) -> ResolvedDateTime:
    """
    R5 — N units before/after an explicit anchor date (DD-MM-YYYY).
    start_time = 00:00:00   end_time = 23:59:59
    """
    anchor = p.p().get("anchor_date", anchors.current_date)
    ad, am, ay = int(anchor[:2]), int(anchor[3:5]), int(anchor[6:])
    n = int(p.p().get("n_units", 0))
    unit = p.p().get("unit", "day")
    direction = p.p().get("direction", "before")

    if direction == "before":
        sd, sm, sy = _apply_unit(ad, am, ay, -n, unit)
        return _make(p, _fmt(sd, sm, sy), _START_TIME, _fmt(ad, am, ay), _END_OF_DAY)
    else:
        ed, em, ey = _apply_unit(ad, am, ay, n, unit)
        return _make(p, _fmt(ad, am, ay), _START_TIME, _fmt(ed, em, ey), _END_OF_DAY)


# ---------------------------------------------------------------------------
# DURATION
# ---------------------------------------------------------------------------


def resolve_full_year(p: ParsedIntent, anchors: Anchors) -> ResolvedDateTime:
    """
    D1 — Full calendar year.
    start_time = 00:00:00
    end_time   = current_time  if end == today
               = 23:59:59      if end is a past date
    """
    y = int(p.p().get("d_year", anchors.year()))
    start_date = _fmt(1, 1, y)
    end_date = anchors.current_date if y == anchors.year() else _fmt(31, 12, y)
    return _make(p, start_date, _START_TIME, end_date, _end_time(end_date, anchors))


def resolve_single_month(p: ParsedIntent, anchors: Anchors) -> ResolvedDateTime:
    """
    D2 — Specific month.
    start_time = 00:00:00
    end_time   = current_time  if end == today
               = 23:59:59      if end is a past date
    """
    m = MONTH_NAME_TO_NUM.get(p.p().get("d_month", ""), anchors.month())
    y = int(p.p().get("d_year", anchors.year()))
    start_date = _fmt(1, m, y)
    end_date = (
        anchors.current_date
        if m == anchors.month() and y == anchors.year()
        else _fmt(_month_last_day(m, y), m, y)
    )
    return _make(p, start_date, _START_TIME, end_date, _end_time(end_date, anchors))


def resolve_month_to_month_range(p: ParsedIntent, anchors: Anchors) -> ResolvedDateTime:
    """
    D3 — Month-to-month range.
    start_time = 00:00:00
    end_time   = current_time  if end == today
               = 23:59:59      if end is a past date
    """
    m1 = MONTH_NAME_TO_NUM.get(p.p().get("d_month", ""), anchors.month())
    m2 = MONTH_NAME_TO_NUM.get(p.p().get("d_month_end", ""), m1)
    y1 = int(p.p().get("d_year", anchors.year()))
    y2 = int(p.p().get("d_year2", y1))
    start_date = _fmt(1, m1, y1)
    end_date = (
        anchors.current_date
        if m2 == anchors.month() and y2 == anchors.year()
        else _fmt(_month_last_day(m2, y2), m2, y2)
    )
    return _make(p, start_date, _START_TIME, end_date, _end_time(end_date, anchors))


# ---------------------------------------------------------------------------
# INSTANT
# ---------------------------------------------------------------------------


def _instant_times(
    date_str: str,
    ts: str | None,
    te: str | None,
    anchors: Anchors,
) -> tuple[str, str]:
    """
    Resolve start/end times for single-day instants.

    If the user provided explicit times → use them as-is.
    If no times provided:
      date == today  → start = 00:00:00, end = current_time
      date != today  → start = 00:00:00, end = 23:59:59
    """
    resolved_start = ts if ts is not None else _START_TIME
    resolved_end = te if te is not None else _end_time(date_str, anchors)
    return resolved_start, resolved_end


def resolve_today_or_yesterday(p: ParsedIntent, anchors: Anchors) -> ResolvedDateTime:
    """
    I1 — Today or yesterday, optionally with a time window.
    No times provided:
      today     → start = 00:00:00, end = current_time
      yesterday → start = 00:00:00, end = 23:59:59
    Times provided → use as-is.
    """
    is_today = p.p().get("instant_is_today", "true") == "true"
    date_str = anchors.current_date if is_today else _yesterday(anchors)
    ts, te = _time_range(p)
    rs, re = _instant_times(date_str, ts, te, anchors)
    return _make(p, date_str, rs, date_str, re)


def resolve_weekday_reference(p: ParsedIntent, anchors: Anchors) -> ResolvedDateTime:
    """
    I2 — Last / next / this <weekday>, optionally with a time window.
    No times provided:
      resolved date == today → start = 00:00:00, end = current_time
      resolved date != today → start = 00:00:00, end = 23:59:59
    Times provided → use as-is.
    """
    target = p.p().get("weekday_target", "monday")
    modifier = p.p().get("weekday_modifier", "this")
    tn = WEEKDAY_ORDER.get(target)
    cn = anchors.weekday_num()
    d, m, y = anchors.day(), anchors.month(), anchors.year()

    if modifier == "this":
        offset = tn - cn
    elif modifier == "last":
        diff = cn - tn
        offset = -(diff if diff > 0 else diff + 7)
    else:  # next
        diff = tn - cn
        offset = diff if diff > 0 else diff + 7

    rd, rm, ry = _add_days(d, m, y, offset)
    date_str = _fmt(rd, rm, ry)
    ts, te = _time_range(p)
    rs, re = _instant_times(date_str, ts, te, anchors)
    return _make(p, date_str, rs, date_str, re)


def resolve_specific_date(p: ParsedIntent, anchors: Anchors) -> ResolvedDateTime:
    """
    I3 — Explicit single date, optionally with a time window.
    No times provided:
      date == today → start = 00:00:00, end = current_time
      date != today → start = 00:00:00, end = 23:59:59
    Times provided → use as-is.
    """
    date_str = p.p().get("instant_date", anchors.current_date)
    ts, te = _time_range(p)
    rs, re = _instant_times(date_str, ts, te, anchors)
    return _make(p, date_str, rs, date_str, re)


# ---------------------------------------------------------------------------
# ABSOLUTE
# ---------------------------------------------------------------------------


def resolve_explicit_date_range(p: ParsedIntent, anchors: Anchors) -> ResolvedDateTime:
    """
    A1 — Explicit start and end date, optionally with a time window.
    No times provided:
      end == today → start = 00:00:00, end = current_time
      end != today → start = 00:00:00, end = 23:59:59
    Times provided → use as-is.
    """
    start_date = p.p().get("abs_start_date", anchors.current_date)
    end_date = p.p().get("abs_end_date", anchors.current_date)
    ts, te = _time_range(p)
    rs, re = _instant_times(end_date, ts, te, anchors)
    return _make(p, start_date, rs, end_date, re)


def resolve_date_to_now_range(p: ParsedIntent, anchors: Anchors) -> ResolvedDateTime:
    """
    A2 — Since <date> to now.
    start_time = provided raw_time_start, or 00:00:00
    end_time   = current_time (always, end is implicitly now)
    """
    start_date = p.p().get("abs_start_date", anchors.current_date)
    ts = _parse_hhmmss(p.p().get("raw_time_start")) or _START_TIME
    return _make(p, start_date, ts, anchors.current_date, anchors.current_time)
