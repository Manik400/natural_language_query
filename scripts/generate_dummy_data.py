"""
Generate deterministic dummy surveillance events for the demo UI.

Usage:
    python scripts/generate_dummy_data.py [--count 2000] [--days 60] [--seed 42]

Writes data/dummy_events.jsonl (one event per line). Every event's properties
validate against its JSON Schema in artifacts/events_schema/, and cameras come
from artifacts/video_resources.json.

Timestamps are local (IST) wall-clock ISO strings ending at ANCHOR. The app
shifts them forward by whole days at load time (demo/data_store.py), so the
data always covers "the last N days" whenever the demo is opened.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config  # noqa: E402

ANCHOR = datetime(2026, 9, 12, 23, 59, 0)

EVENT_WEIGHTS = {
    "ANPR Properties": 22,
    "Face Recognition Properties": 18,
    "Objects Entered Properties": 10,
    "Highway ATCC Properties": 8,
    "Safety Gear Violation Properties": 8,
    "Perimeter Violation Properties": 5,
    "Crowd Detected Properties": 5,
    "Vehicle Stopped Properties": 4,
    "Lane Changed Properties": 4,
    "Illegal Vehicle Properties": 3,
    "Reverse Traffic Properties": 3,
    "Vehicle Accelerated Properties": 3,
    "Human Crossing Road Properties": 3,
    "Collison Detected Properties": 2,
    "Motion Analysis Properties": 2,
}

# Camera-name fragments each family of events prefers (falls back to all cameras).
TRAFFIC_CAMS = ("GATE", "ENTRY", "BOOM", "WB", "DUMP", "RAIL", "SURF", "OB_", "BAY",
                "240T", "1222", "AMG", "GAY", "BALRAM", "SARANGI", "MAIN", "HASDEO", "DISP")
PEOPLE_CAMS = ("GATE", "ENTRY", "LOBBY", "ADMIN", "FLOOR", "CONF", "BOARD", "SEC_",
               "OFFICE", "HOSP", "WARD", "ICU", "COLONY", "MAIN", "FACE")
SITE_CAMS = ("PIT", "PLANT", "WASH", "CPP", "SILO", "SHAFT", "UG_", "MINE", "PERIM",
             "NORTH", "TOWER", "HIK", "CTRL", "INNER", "LAB", "WS_", "PLATFORM", "LOAD")

CAMERA_FAMILY = {
    "Face Recognition Properties": PEOPLE_CAMS,
    "Objects Entered Properties": PEOPLE_CAMS,
    "Crowd Detected Properties": PEOPLE_CAMS,
    "Safety Gear Violation Properties": SITE_CAMS,
    "Perimeter Violation Properties": SITE_CAMS,
    "Motion Analysis Properties": SITE_CAMS,
}  # everything else → TRAFFIC_CAMS

NAMES = ["Karan Desai", "Priya Sharma", "Rahul Verma", "Anita Singh", "Vikram Rao",
         "Sneha Patel", "Arjun Mehta", "Pooja Nair", "Rohit Gupta", "Neha Joshi",
         "Amit Kumar", "Kavita Reddy", "Suresh Yadav", "Meera Iyer", "Imran Khan",
         "Deepak Mishra", "Ritu Agarwal", "Sanjay Chauhan", "Farah Ali", "Manoj Tiwari"]
IDENTITIES = {"Employee": 40, "Visitor": 25, "Contractor": 15, "VIP": 5,
              "Watchlist": 6, "Wanted": 3, "Unknown": 6}
ADDRESSES = ["MG Road, Gurugram", "Sector 29, Gurugram", "Connaught Place, New Delhi",
             "Koramangala, Bengaluru", "Bandra West, Mumbai", "Salt Lake, Kolkata",
             "Kusmunda, Korba", "Transport Nagar, Korba", "Link Road, Bilaspur",
             "Hitech City, Hyderabad", "Civil Lines, Raipur", "Aundh, Pune"]
STATES = ["HR", "DL", "UP", "CG", "MP", "MH", "RJ", "PB", "KA", "GJ"]
VEHICLES = ["car", "truck", "bus", "motorbike", "auto_rickshaw", "tractor", "dumper"]
VIEWS = ["front", "rear", "side"]
ZONES = [f"Z{i}" for i in range(1, 9)]
HOUR_WEIGHTS = [1, 1, 1, 1, 1, 2, 4, 6, 8, 9, 9, 8, 8, 8, 9, 9, 9, 8, 7, 6, 4, 3, 2, 1]


def pick(rng: random.Random, weights: dict):
    return rng.choices(list(weights), weights=list(weights.values()))[0]


def plate(rng: random.Random) -> str:
    letters = "".join(rng.choice("ABCDEFGHJKLMNPRSTUVWXYZ") for _ in range(2))
    return f"{rng.choice(STATES)}{rng.randint(1, 99):02d}{letters}{rng.randint(1000, 9999)}"


# ── Per-event property generators ────────────────────────────────────────────


def gen_anpr(rng):
    speed = round(rng.uniform(15, 125), 1)
    riders = rng.choices([1, 2, 3, 4], weights=[60, 28, 9, 3])[0]
    return {
        "plateNumber": plate(rng),
        "speed": speed,
        "VehicleColor": rng.choice(["Red", "Green", "Blue", "Yellow", "Orange"]),
        "Category": pick(rng, {"Authorized": 50, "Unauthorized": 14, "Suspecious": 9,
                               "Lost": 9, "Stolen": 9, "Wanted": 9}),
        "numberOfRiders": riders,
        "redLightViolated": rng.random() < 0.12,
        "speedViolated": speed > 80,
        "trippleRiding": riders >= 3,
        "noHelmet": rng.random() < 0.2,
    }


def gen_face(rng):
    return {
        "age": rng.randint(18, 75),
        "glasses": rng.random() < 0.25,
        "mask": rng.random() < 0.15,
        "gender": rng.choice(["male", "female"]),
        "emotion": pick(rng, {"neutral": 40, "happy": 20, "sad": 10, "angry": 10,
                              "surprised": 8, "scared": 5, "disgusted": 3, "unknown": 4}),
        "personName": rng.choice(NAMES),
        "identity": pick(rng, IDENTITIES),
        "detConf": round(rng.uniform(0.55, 0.99), 2),
    }


def gen_crowd(rng):
    threshold = rng.choice([20, 30, 50, 100])
    return {
        "type": rng.choice(["Gathering", "Queue", "Protest", "Rally"]),
        "threshold": threshold,
        "count": threshold + rng.randint(0, threshold),
        "speed": rng.choice(["slow", "normal", "fast"]),
        "zoneId": rng.choice(ZONES),
    }


def gen_atcc(rng):
    return {
        "car": rng.randint(20, 300), "bus": rng.randint(0, 25), "truck": rng.randint(0, 60),
        "motorbike": rng.randint(10, 220), "bicycle": rng.randint(0, 30),
        "person": rng.randint(0, 40), "auto_rickshaw": rng.randint(0, 50),
        "e_rickshaw": rng.randint(0, 30), "mini_bus": rng.randint(0, 10),
        "mini_truck": rng.randint(0, 25), "van": rng.randint(0, 20),
        "tractor": rng.randint(0, 8), "cow": rng.choices([0, 1, 2, 3], [80, 10, 6, 4])[0],
        "dog": rng.choices([0, 1, 2], [85, 10, 5])[0], "horse": 0, "sheep": 0, "bird": 0,
        "train": 0, "face": rng.randint(0, 15), "head": rng.randint(0, 40),
        "text": rng.randint(0, 5), "wagon_gap": 0,
        "LaneName": f"Lane {rng.randint(1, 4)}",
    }


def gen_vehicle_zone(rng, zone_key="zoneid"):
    return {"vehicle_view": rng.choice(VIEWS), "type": rng.choice(VEHICLES),
            zone_key: rng.choice(ZONES)}


def gen_illegal(rng):
    return {"vehicle_view": rng.choice(VIEWS), "zoneid": rng.choice(ZONES),
            "type": rng.choice(["No Parking", "Restricted Zone", "Wrong Lane", "Heavy Vehicle Ban"])}


def gen_lane(rng):
    return {"vehicle_view": rng.choice(VIEWS), "type": rng.choice(VEHICLES),
            "laneNo": str(rng.randint(1, 4)),
            "area": rng.choice(["Highway", "Junction", "Flyover", "Tunnel"]),
            "zoneId": rng.choice(ZONES)}


def gen_human_crossing(rng):
    return {"vehicle_view": rng.choice(VIEWS),
            "type": rng.choice(["person", "pedestrian", "child"]),
            "zoneId": rng.choice(ZONES)}


def gen_stopped(rng):
    return {**gen_vehicle_zone(rng), "trackid": rng.randint(1000, 99999)}


def gen_objects_entered(rng):
    me, fe = rng.randint(0, 60), rng.randint(0, 50)
    mx, fx = rng.randint(0, me), rng.randint(0, fe)
    male = rng.random() < 0.55
    age = rng.choice(["AgeYoung", "AgeYoungAdult", "AgeAdult", "AgeOld"])
    return {
        "male_entry": me, "male_exit": mx, "female_entry": fe, "female_exit": fx,
        "entry": me + fe, "exit": mx + fx,
        "type": rng.choices(["person", "vehicle"], [80, 20])[0],
        "lineName": rng.choice(["Main Gate Line", "Lobby Line", "Parking Line", "Canteen Line"]),
        "male": male, "female": not male,
        **{k: k == age for k in ("AgeYoung", "AgeYoungAdult", "AgeAdult", "AgeOld")},
    }


def gen_perimeter(rng):
    return {"linename": rng.choice(["North Fence", "South Fence", "East Wall", "Mine Boundary"]),
            "type": rng.choices(["person", "vehicle", "animal"], [70, 20, 10])[0],
            "Zone": rng.choice(ZONES)}


def gen_safety(rng):
    gear = {"helmet": rng.random() < 0.6, "safetyVest": rng.random() < 0.6,
            "safetyshoes": rng.random() < 0.7, "safetyBelt": rng.random() < 0.7}
    if all(gear.values()):  # a violation always has at least one missing item
        gear[rng.choice(list(gear))] = False
    return gear


def gen_motion(rng, ts: datetime):
    stay = timedelta(seconds=rng.randint(5, 900))
    frame = rng.randint(100, 90000)
    return {"zoneID": rng.choice(ZONES),
            "entryTimeStamp": ts.isoformat(timespec="seconds"),
            "exitTimeStamp": (ts + stay).isoformat(timespec="seconds"),
            "frameEntryTimeStamp": f"F{frame}",
            "frameExitTimeStamp": f"F{frame + int(stay.total_seconds() * 25)}"}


GENERATORS = {
    "ANPR Properties": gen_anpr,
    "Face Recognition Properties": gen_face,
    "Crowd Detected Properties": gen_crowd,
    "Highway ATCC Properties": gen_atcc,
    "Collison Detected Properties": gen_vehicle_zone,
    "Human Crossing Road Properties": gen_human_crossing,
    "Illegal Vehicle Properties": gen_illegal,
    "Lane Changed Properties": gen_lane,
    "Objects Entered Properties": gen_objects_entered,
    "Perimeter Violation Properties": gen_perimeter,
    "Reverse Traffic Properties": gen_vehicle_zone,
    "Safety Gear Violation Properties": gen_safety,
    "Vehicle Accelerated Properties": gen_vehicle_zone,
    "Vehicle Stopped Properties": gen_stopped,
}


# ── Assembly ─────────────────────────────────────────────────────────────────


def load_schemas() -> dict[str, dict]:
    """Title → schema, found by title (not filename) so misnamed files still load."""
    schemas = {}
    for path in sorted(config.SCHEMA_DIR.glob("*.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        schemas[schema["title"]] = schema
    return schemas


def cameras_for(event_type: str, cameras: list[dict]) -> list[dict]:
    family = CAMERA_FAMILY.get(event_type, TRAFFIC_CAMS)
    chosen = [c for c in cameras if any(f in c["name"] for f in family)]
    return chosen or cameras


def make_event(event_type, ts, cam, props, attributes=None) -> dict:
    return {
        "timestamp": ts.isoformat(timespec="seconds"),
        "event_type": event_type,
        "analytics": event_type.removesuffix(" Properties").replace(" ", "_"),
        "camera_name": cam["name"],
        "camera_id": cam["id"],
        "camera_ip": cam["ip"],
        "properties": props,
        "attributes": attributes or {},
    }


def planted_events(cams_by_name: dict[str, dict]) -> list[dict]:
    """Hand-made events so the app's default demo query has real hits."""
    papa, pepper = cams_by_name["PAPA_JOHNS_ENTRY_CAM01"], cams_by_name["DR_PEPPER_ENTRY_CAM01"]
    home = {"address": "MG Road, Gurugram"}
    events = []
    for days_ago, hour, cam, speed in [(1, 18, papa, 104.2), (3, 9, pepper, 96.5),
                                       (5, 21, papa, 99.0), (20, 11, pepper, 101.3)]:
        ts = (ANCHOR - timedelta(days=days_ago)).replace(hour=hour, minute=12, second=40)
        events.append(make_event("ANPR Properties", ts, cam, {
            "plateNumber": "HR5653RT78", "speed": speed, "VehicleColor": "Red",
            "Category": "Stolen", "numberOfRiders": 1, "redLightViolated": True,
            "speedViolated": True, "trippleRiding": False, "noHelmet": True}, home))
    for days_ago, hour, cam in [(1, 18, papa), (4, 13, pepper), (20, 11, pepper)]:
        ts = (ANCHOR - timedelta(days=days_ago)).replace(hour=hour, minute=10, second=5)
        events.append(make_event("Face Recognition Properties", ts, cam, {
            "age": 34, "glasses": False, "mask": False, "gender": "male",
            "emotion": "angry", "personName": "Karan Desai", "identity": "Wanted",
            "detConf": 0.93}, home))
    return events


def generate(count: int, days: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    schemas = load_schemas()
    cameras = json.loads(config.VIDEO_JSON_PATH.read_text(encoding="utf-8"))
    cams_by_name = {c["name"]: c for c in cameras}
    validators = {t: Draft202012Validator(s) for t, s in schemas.items()}

    events = planted_events(cams_by_name)
    while len(events) < count:
        event_type = pick(rng, EVENT_WEIGHTS)
        day = ANCHOR.date() - timedelta(days=rng.randrange(days))
        ts = datetime(day.year, day.month, day.day,
                      rng.choices(range(24), weights=HOUR_WEIGHTS)[0],
                      rng.randrange(60), rng.randrange(60))
        cam = rng.choice(cameras_for(event_type, cameras))
        if event_type == "Motion Analysis Properties":
            props = gen_motion(rng, ts)
        else:
            props = GENERATORS[event_type](rng)
        attributes = ({"address": rng.choice(ADDRESSES)}
                      if event_type in ("ANPR Properties", "Face Recognition Properties")
                      and rng.random() < 0.8 else {})
        events.append(make_event(event_type, ts, cam, props, attributes))

    for event in events:
        errors = list(validators[event["event_type"]].iter_errors(event["properties"]))
        if errors:
            raise ValueError(f"{event['event_type']}: {errors[0].message}")

    events.sort(key=lambda e: e["timestamp"])
    for i, event in enumerate(events, 1):
        event["event_id"] = f"EVT-{i:05d}"
    return events


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--count", type=int, default=2000)
    parser.add_argument("--days", type=int, default=60)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    events = generate(args.count, args.days, args.seed)
    config.DUMMY_EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(config.DUMMY_EVENTS_PATH, "w", encoding="utf-8", newline="\n") as fh:
        for event in events:
            fh.write(json.dumps({"event_id": event.pop("event_id"), **event}) + "\n")
    print(f"Wrote {len(events)} events -> {config.DUMMY_EVENTS_PATH}")


if __name__ == "__main__":
    main()
