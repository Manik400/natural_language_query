import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import config

from .models import RULETYPE_TO_JSON, EventSchema
from .schema_docs import generate_event_and_property_docs

MAX_WORKERS = 6


# ─────────────────────────────────────────────
# Hash
# ─────────────────────────────────────────────


def compute_schema_hash(event_name: str, properties: list[str]) -> str:
    payload = {"event": event_name, "properties": sorted(properties)}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


# ─────────────────────────────────────────────
# Schema Builders
# ─────────────────────────────────────────────


def build_property_schema(rule_type: int, description: str) -> dict:
    json_type, fmt = RULETYPE_TO_JSON.get(rule_type, ("string", None))
    prop = {"type": json_type, "description": description, "ruleType": rule_type}
    if fmt:
        prop["format"] = fmt
    return prop


def build_schema(event_name: str, description: str, properties: dict) -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://example.com/schemas/{event_name.lower()}.json",
        "title": f"{event_name} Properties",
        "description": description,
        "type": "object",
        "properties": properties,
        "minProperties": 1,
        "unevaluatedProperties": False,
    }


# ─────────────────────────────────────────────
# Load / Persist
# ─────────────────────────────────────────────


def load_existing_schemas(schema_dir: Path) -> dict:
    schemas = {}
    for file in schema_dir.glob("*.json"):
        with open(file) as f:
            schema = json.load(f)
        event_name = schema["title"].replace(" Properties", "")
        schemas[event_name] = schema
    return schemas


def save_schema(schema: dict, event_name: str, schema_dir: Path) -> None:
    file_path = schema_dir / f"{'_'.join(event_name.lower().split())}.json"
    with open(file_path, "w") as f:
        json.dump(schema, f, indent=2)


# ─────────────────────────────────────────────
# Change Detection
# ─────────────────────────────────────────────


def detect_schema_changes(
    events: list[EventSchema],
    existing_schemas: dict,
) -> list[tuple[EventSchema, str]]:
    changed = []
    for event in events:
        prop_names = [p.name for p in event.properties]
        new_hash = compute_schema_hash(event.name, prop_names)
        if event.name not in existing_schemas:
            changed.append((event, new_hash))
            continue
        if existing_schemas[event.name].get("schemaHash") != new_hash:
            changed.append((event, new_hash))
    return changed


# ─────────────────────────────────────────────
# Per-Event Processing
# ─────────────────────────────────────────────


def process_event(
    event: EventSchema,
    new_hash: str,
    existing_schemas: dict,
    schema_dir: Path,
) -> None:
    event_name = event.name
    incoming = {p.name: p.type for p in event.properties}

    if event_name not in existing_schemas:
        # Brand-new event — generate docs for all properties
        docs = generate_event_and_property_docs(event_name, list(incoming.keys()))

        properties = {
            name: build_property_schema(
                rtype, docs["property_descriptions"].get(name, "")
            )
            for name, rtype in incoming.items()
        }

        schema = build_schema(event_name, docs["event_description"], properties)

    else:
        # Existing event — diff and patch
        schema = existing_schemas[event_name]
        props = schema["properties"]

        existing_names = set(props.keys())
        incoming_names = set(incoming.keys())

        # Remove deleted properties
        for p in existing_names - incoming_names:
            props.pop(p)

        # Generate docs only for genuinely new properties
        new_props = incoming_names - existing_names
        if new_props:
            docs = generate_event_and_property_docs(event_name, list(new_props))
            for p in new_props:
                props[p] = build_property_schema(
                    incoming[p],
                    docs["property_descriptions"].get(p, ""),
                )

    schema["schemaHash"] = new_hash
    save_schema(schema, event_name, schema_dir)


# ─────────────────────────────────────────────
# Public Sync Entry Point
# ─────────────────────────────────────────────


def sync_event_schemas(events: list[EventSchema]) -> dict:
    config.SCHEMA_DIR.mkdir(parents=True, exist_ok=True)

    existing_schemas = load_existing_schemas(config.SCHEMA_DIR)
    changed_events = detect_schema_changes(events, existing_schemas)

    if not changed_events:
        return {"updated": 0, "skipped": len(events)}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [
            executor.submit(
                process_event, event, new_hash, existing_schemas, config.SCHEMA_DIR
            )
            for event, new_hash in changed_events
        ]
        for f in futures:
            f.result()

    return {
        "updated": len(changed_events),
        "skipped": len(events) - len(changed_events),
    }
