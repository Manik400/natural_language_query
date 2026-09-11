"""
classifier.py — Prompt builder and anchor factory for the DateTime Intent Engine.
"""

from __future__ import annotations

import datetime as dt

from .constants import WEEKDAY_ORDER
from .models import Anchors
from .prompt import CLASSIFIER_PROMPT

_WEEKDAY_NUM_TO_NAME: dict[int, str] = {v: k for k, v in WEEKDAY_ORDER.items()}


def build_anchors(current_datetime: dt.datetime | None = None) -> Anchors:

    if current_datetime is None:
        current_datetime = dt.datetime.now()

    current_date = f"{current_datetime.day:02d} {current_datetime.month:02d} {current_datetime.year:04d}"
    current_time = current_datetime.strftime("%H:%M:%S")
    current_weekday = _WEEKDAY_NUM_TO_NAME[
        current_datetime.isoweekday()
    ]  # isoweekday: mon=1 … sun=7

    return Anchors(
        current_date=current_date,
        current_time=current_time,
        current_weekday=current_weekday,
    )


def build_classifier_prompt(user_query: str) -> str:
    """
    Render the classifier prompt with the user query only.
    Anchors are not injected into the prompt — they are resolved
    server-side at dispatch time, not by the LLM.
    """
    return CLASSIFIER_PROMPT.format(user_query=user_query)
