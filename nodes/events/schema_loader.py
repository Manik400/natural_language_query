from __future__ import annotations

import asyncio
import json
import os

import aiofiles


async def load_event_schemas(schema_dir: str) -> list[dict]:
    """
    Load all JSON schema files from the given directory.
    Returns a list of dicts with title, description, and fields.
    """
    if not os.path.exists(schema_dir):
        raise FileNotFoundError(f"Schema directory not found: {schema_dir}")

    schemas = []

    async def _load_file(filename: str) -> dict | None:
        filepath = os.path.join(schema_dir, filename)
        try:
            async with aiofiles.open(filepath, "r") as f:
                content = await f.read()
            raw = json.loads(content)

            title = raw.get("title", "").strip()
            if not title:
                print(f"[WARNING] Skipping {filename}: missing title")
                return None

            description = raw.get("description", "").strip()
            fields = list(raw.get("properties", {}).keys())

            print(f"[INFO] Loaded schema: {title}")
            return {
                "title": title,
                "description": description,
                "fields": fields,
            }

        except json.JSONDecodeError as e:
            print(f"[ERROR] Failed to parse {filename}: {e}")
            return None
        except Exception as e:
            print(f"[ERROR] Unexpected error reading {filename}: {e}")
            return None

    filenames = sorted(f for f in os.listdir(schema_dir) if f.endswith(".json"))

    results = await asyncio.gather(*[_load_file(f) for f in filenames])

    schemas = [r for r in results if r is not None]

    if not schemas:
        raise ValueError(f"No valid schema files found in: {schema_dir}")

    return schemas
