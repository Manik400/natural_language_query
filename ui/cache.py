"""Streamlit-cached accessors shared by both pages."""

from __future__ import annotations

import json

import pandas as pd
import streamlit as st

import config
from demo.data_store import flatten_event, load_events


@st.cache_data(ttl=900, show_spinner=False)
def cached_events() -> list[dict]:
    return load_events()


@st.cache_data(show_spinner=False)
def camera_names() -> list[str]:
    """Every camera in artifacts/video_resources.json, sorted."""
    return sorted(c["name"] for c in json.loads(config.VIDEO_JSON_PATH.read_text(encoding="utf-8")))


def events_frame(events: list[dict]) -> pd.DataFrame:
    return pd.DataFrame([flatten_event(e) for e in events])
