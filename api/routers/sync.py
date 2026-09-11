import json
from typing import List

from fastapi import APIRouter, HTTPException

import config
from sync.models import Attribute, EventSchema, VideoResource
from sync.schema_sync import sync_event_schemas

router = APIRouter(prefix="/sync", tags=["Sync"])


@router.post("/attributes")
def sync_attributes(request: List[Attribute]):
    try:
        with open(config.ATTRIBUTES_JSON_PATH, "w") as f:
            json.dump([item.dict() for item in request], f, indent=2)

        return {"status": "success", "attributes_synced": len(request)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/video_resources")
def sync_video_resources(request: List[VideoResource]):
    try:
        config.VIDEO_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)

        transformed = []
        for v in request:
            resource = v.dict()
            # Transform type: videoSource -> camera
            if resource.get("type") == "videoSource":
                resource["type"] = "camera"
            transformed.append(resource)

        with open(config.VIDEO_JSON_PATH, "w") as f:
            json.dump(transformed, f, indent=2)

        return {"status": "success", "videos_synced": len(transformed)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/events_schema")
def sync_events_schema(request: List[EventSchema]):
    try:
        result = sync_event_schemas(request)
        return {"status": "success", **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
