"""Loads the dummy event dataset used by the demo UI."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import config

_SHIFTED_PROPERTY_KEYS = ("entryTimeStamp", "exitTimeStamp")


def event_label(event_type: str) -> str:
    """'ANPR Properties' → 'ANPR'."""
    return event_type.removesuffix(" Properties")


def load_events(
    path: Path = config.DUMMY_EVENTS_PATH,
    now: datetime | None = None,
) -> list[dict]:
    """Return all events, newest first, with timestamps moved forward by whole
    days so the newest day in the file lands on today. Events that would fall
    later than *now* are dropped. Each event gains a parsed ``ts`` datetime."""
    now = now or datetime.now()
    with open(path, encoding="utf-8") as fh:
        raw = [json.loads(line) for line in fh if line.strip()]

    newest = max(datetime.fromisoformat(e["timestamp"]) for e in raw)
    shift = timedelta(days=(now.date() - newest.date()).days)

    events = []
    for event in raw:
        ts = datetime.fromisoformat(event["timestamp"]) + shift
        if ts > now:
            continue
        props = dict(event["properties"])
        for key in _SHIFTED_PROPERTY_KEYS:
            if key in props:
                shifted = datetime.fromisoformat(props[key]) + shift
                props[key] = shifted.isoformat(timespec="seconds")
        events.append(
            {**event, "ts": ts, "timestamp": ts.isoformat(timespec="seconds"),
             "properties": props}
        )

    events.sort(key=lambda e: e["ts"], reverse=True)
    return events


def summarize_properties(props: dict, max_items: int = 7) -> str:
    """Compact one-line summary: true flags by name, skips false flags and zero counts."""
    parts = []
    for key, value in props.items():
        if value is False or value == 0 or value in ("", None):
            continue
        parts.append(key if value is True else f"{key}: {value}")
    extra = len(parts) - max_items
    text = " · ".join(parts[:max_items])
    return f"{text} · +{extra} more" if extra > 0 else text


def event_details(event: dict) -> str:
    props = event["properties"]
    if event["event_type"] == "Safety Gear Violation Properties":
        missing = [k for k, v in props.items() if v is False]
        return "missing: " + ", ".join(missing)
    return summarize_properties(props)


def flatten_event(event: dict) -> dict:
    """Table row for one event."""
    return {
        "Time": event["ts"],
        "Event ID": event["event_id"],
        "Event": event_label(event["event_type"]),
        "Camera": event["camera_name"],
        "IP": event["camera_ip"],
        "Details": event_details(event),
        "Address": event.get("attributes", {}).get("address", ""),
    }
