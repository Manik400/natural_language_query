import json

from fastapi import APIRouter, HTTPException

import config
from sync.models import AttributeValueType

router = APIRouter(prefix="/artifacts", tags=["Artifacts"])


@router.get("/attributes")
def get_attributes():
    try:
        with open(config.ATTRIBUTES_JSON_PATH, "r") as f:
            data = json.load(f)
        return [
            {"key": item["key"], "valueType": AttributeValueType[item["valueType"]]}
            for item in data
        ]
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Attributes data not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/video_resouces")
def video_resouces_raw():
    try:
        with open(config.VIDEO_JSON_PATH, "r") as f:
            data = json.load(f)

        return [
            {
                "name": item["name"],
                "ip": item["ip"],
                "type": "videoSource",
                "id": item["id"],
            }
            for item in data
        ]
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Video Resource data not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/events")
def events_schema():
    try:
        events = []
        for file in config.SCHEMA_DIR.glob("*.json"):
            with open(file) as f:
                schema = json.load(f)

            event_name = schema["title"].replace(" Properties", "")
            properties = [
                {
                    "name": prop_name,
                    "ruleType": prop_def.get("ruleType"),
                }
                for prop_name, prop_def in schema.get("properties", {}).items()
            ]
            events.append({"name": event_name, "properties": properties})

        return events
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Schema directory not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
