"""
Rule-based stand-in for the per-event field-extraction LLM (offline mode).

Candidates are produced with regex/vocabulary rules, then passed through the
project's own two-stage field validator (nodes/fields/validate.py), so every
returned field, operator and value is valid for the event's JSON Schema.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache

import config
from demo.rules_events import VEHICLE
from nodes.fields.validate import ResponseValidator, validate_fields

_NUMBER = r"(\d+(?:\.\d+)?)"
_COMPARATORS = [
    (r"(?:greater|more|higher|faster|older)\s+than|above|over|exceeding|exceeds|>", "GreaterThan"),
    (r"at\s+least|>=|minimum\s+of", "GreaterThanOrEqual"),
    (r"(?:less|fewer|lower|slower|younger)\s+than|below|under|<", "SmallerThan"),
    (r"at\s+most|<=|maximum\s+of|up\s+to", "SmallerThanOrEqual"),
    (r"exactly|equal\s+to|equals|=", "Equal"),
]
_CMP = "|".join(p for p, _ in _COMPARATORS)

# field → (words that come BEFORE the number, words that come AFTER the number)
NUMERIC_FIELDS: dict[str, dict[str, tuple[str | None, str | None]]] = {
    "ANPR Properties": {
        "speed": (r"speeds?|travell?ing\s+at|moving\s+at|going\s+at", r"km\s*/?\s*h|kmph|kph|km\s+per\s+hour"),
        "numberOfRiders": (r"riders?", r"riders|people\s+on|persons\s+on"),
    },
    "Face Recognition Properties": {
        "age": (r"age|aged", r"years?(?:\s+old)?|yrs?"),
        "detConf": (r"confidence|detconf", None),
    },
    "Crowd Detected Properties": {
        "count": (r"count|crowd\s+(?:of|size)", r"people|persons|individuals"),
        "threshold": (r"threshold", None),
    },
    "Objects Entered Properties": {
        "male_entry": (r"male\s+entr(?:y|ies)", r"males?\s+entered|men\s+entered"),
        "female_entry": (r"female\s+entr(?:y|ies)", r"females?\s+entered|women\s+entered"),
        "entry": (r"entr(?:y|ies)(?:\s+count)?", r"(?:people\s+)?entered|entries"),
        "exit": (r"exits?(?:\s+count)?", r"(?:people\s+)?exited|exits"),
    },
    "Vehicle Stopped Properties": {"trackid": (r"track\s*id|trackid", None)},
    "Highway ATCC Properties": {
        f: (rf"{w}\s+count", rf"{w}")
        for f, w in {
            "car": r"cars?", "bus": r"bus(?:es)?", "truck": r"trucks?", "motorbike": r"motorbikes?|bikes?",
            "bicycle": r"bicycles?|cycles?", "person": r"persons?|people|pedestrians?",
            "auto_rickshaw": r"auto[\s-]?rickshaws?|autos?", "e_rickshaw": r"e[\s-]?rickshaws?",
            "tractor": r"tractors?", "van": r"vans?", "mini_bus": r"mini[\s-]?bus(?:es)?",
            "mini_truck": r"mini[\s-]?trucks?", "cow": r"cows?|cattle", "dog": r"dogs?",
        }.items()
    },
}

ENUM_SYNONYMS = {
    ("ANPR Properties", "Category"): {
        "Unauthorized": r"unauthori[sz]ed", "Authorized": r"authori[sz]ed", "Stolen": r"stolen",
        "Wanted": r"wanted", "Lost": r"lost|missing", "Suspecious": r"suspicious|suspecious|suspected",
    },
    ("Face Recognition Properties", "gender"): {
        "male": r"male|man|men|boys?|gentlem[ae]n", "female": r"female|wom[ae]n|girls?|lad(?:y|ies)",
    },
    ("Face Recognition Properties", "emotion"): {
        "angry": r"angry|anger|furious", "happy": r"happy|smiling|joyful", "sad": r"sad|unhappy|crying",
        "scared": r"scared|afraid|fearful|frightened", "surprised": r"surprised|shocked",
        "disgusted": r"disgust(?:ed)?", "neutral": r"neutral|calm",
    },
}

# Vocabulary for free-text string fields, matching the values in the dummy data.
_VEHICLE_TYPES = {"car": r"cars?", "truck": r"trucks?|lorry|lorries", "bus": r"bus(?:es)?",
                  "motorbike": r"motorbikes?|motorcycles?|bikes?|scooters?|two[- ]wheelers?",
                  "auto_rickshaw": r"auto[\s-]?rickshaws?|autos?", "tractor": r"tractors?",
                  "dumper": r"dumpers?"}
STRING_VOCAB = {
    "identity": {"Employee": r"employees?|staff", "Visitor": r"visitors?|guests?",
                 "Contractor": r"contractors?", "VIP": r"vips?", "Watchlist": r"watch\s?list(?:ed)?|black\s?list(?:ed)?",
                 "Wanted": r"wanted\s+(?:person|man|woman|criminal|suspect|individual)|is\s+wanted",
                 "Unknown": r"unknown\s+(?:person|people|faces?|individuals?|identity)"},
    "area": {"Highway": r"highway", "Junction": r"junction", "Flyover": r"flyover", "Tunnel": r"tunnel"},
}
TYPE_VOCAB = {
    "Human Crossing Road Properties": {"person": r"persons?|people", "pedestrian": r"pedestrians?",
                                       "child": r"child(?:ren)?|kids?"},
    "Perimeter Violation Properties": {"person": r"persons?|people|intruders?|humans?",
                                       "vehicle": r"vehicles?|cars?|trucks?", "animal": r"animals?|dogs?|cows?"},
    "Crowd Detected Properties": {"Gathering": r"gatherings?", "Queue": r"queues?", "Protest": r"protests?",
                                  "Rally": r"rall(?:y|ies)"},
    "Illegal Vehicle Properties": {"No Parking": r"no[\s-]parking|illegally\s+parked|wrong(?:ly)?\s+parked",
                                   "Restricted Zone": r"restricted\s+(?:zone|area)|prohibited\s+(?:zone|area)",
                                   "Wrong Lane": r"wrong\s+lane", "Heavy Vehicle Ban": r"heavy\s+vehicles?"},
    "Objects Entered Properties": {"person": r"persons?|people", "vehicle": r"vehicles?"},
}

# field → (patterns meaning True, patterns meaning False). False is checked first.
_NEGATOR = r"(?:without|no|not\s+wearing|missing|lack(?:ing)?\s+(?:of\s+)?)\s+(?:a\s+|any\s+)?"
# "without X" or a later item in a list: "without helmet or safety vest"
_NEG = rf"(?:{_NEGATOR}|{_NEGATOR}(?:[a-z]+\s+){{1,3}}(?:or|and|nor|,)\s*(?:a\s+)?)"
_POS = r"(?:with|wearing|wore|has|had)\s+(?:a\s+)?"
BOOLEAN_FIELDS = {
    "ANPR Properties": {
        "redLightViolated": ([r"red[\s-]?light", r"traffic\s+signals?", r"signal\s+(?:jump|violation)",
                              r"jump(?:ed|ing)?\s+(?:the\s+)?(?:red\s+)?signal"], []),
        "speedViolated": ([r"speed\s+limit", r"over[\s-]?speed(?:ing)?", r"speeding(?!\s+up)", r"speed\s+violation"], []),
        "trippleRiding": ([r"tri?pple\s+riding", r"three\s+(?:people|riders|persons)\s+on"], []),
        "noHelmet": ([_NEG + r"helmets?", r"helmetless"], [_POS + r"helmets?"]),
    },
    "Face Recognition Properties": {
        "glasses": ([_POS + r"(?:glasses|spectacles|specs)"], [_NEG + r"(?:glasses|spectacles|specs)"]),
        "mask": ([_POS + r"(?:face\s+)?masks?"], [_NEG + r"(?:face\s+)?masks?"]),
    },
    "Safety Gear Violation Properties": {
        field: ([_POS + words], [_NEG + words])
        for field, words in {"helmet": r"(?:safety\s+)?(?:helmets?|hard\s*hats?)",
                             "safetyVest": r"(?:safety\s+|reflective\s+)?(?:vests?|jackets?)",
                             "safetyshoes": r"(?:safety\s+)?(?:shoes|boots)",
                             "safetyBelt": r"(?:safety\s+)?belts?|harness(?:es)?"}.items()
    },
}


@lru_cache(maxsize=1)
def schemas_by_title() -> dict[str, dict]:
    return {
        (s := json.loads(p.read_text(encoding="utf-8")))["title"]: s
        for p in sorted(config.SCHEMA_DIR.glob("*.json"))
    }


def _cand(field, operator, value, snippet) -> dict:
    return {"field": field, "operator": operator, "value": value, "query_snippet": snippet.strip()}


def _number(text: str) -> int | float:
    return float(text) if "." in text else int(text)


def _operator(cmp_text: str | None) -> str:
    if not cmp_text:
        return "Equal"
    for pattern, op in _COMPARATORS:
        if re.fullmatch(pattern, cmp_text.strip(), re.I):
            return op
    return "Equal"


def _numeric(query: str, field: str, before: str | None, after: str | None) -> dict | None:
    if before:
        m = re.search(rf"\b(?:{before})\b\s*(?:is|was|of)?\s*between\s+{_NUMBER}\s*(?:and|to|-)\s*{_NUMBER}", query, re.I)
        if m:
            return _cand(field, "Between", [_number(m.group(1)), _number(m.group(2))], m.group(0))
        m = re.search(rf"\b(?:{before})\b\s*(?:is|was|of|at)?\s*({_CMP})?\s*{_NUMBER}", query, re.I)
        if m:
            return _cand(field, _operator(m.group(1)), _number(m.group(2)), m.group(0))
    if after:
        m = re.search(rf"(?:\b({_CMP})\s*)?{_NUMBER}\s*(?:{after})\b", query, re.I)
        if m:
            return _cand(field, _operator(m.group(1)), _number(m.group(2)), m.group(0))
    return None


def _vocab(query: str, field: str, vocab: dict[str, str]) -> dict | None:
    best = None
    for value, pattern in vocab.items():
        m = re.search(rf"\b(?:{pattern})\b", query, re.I)
        if m and (best is None or m.start() < best[1].start()):
            best = (value, m)
    return _cand(field, "Equal", best[0], best[1].group(0)) if best else None


def _candidates(event: str, schema: dict, query: str) -> list[dict]:
    props = schema.get("properties", {})
    out: dict[str, dict] = {}

    def put(c):
        if c and c["field"] in props and c["field"] not in out:
            out[c["field"]] = c

    for field, (before, after) in NUMERIC_FIELDS.get(event, {}).items():
        put(_numeric(query, field, before, after))

    for field, (true_pats, false_pats) in BOOLEAN_FIELDS.get(event, {}).items():
        for value, pats in ((False, false_pats), (True, true_pats)):
            m = next((m for p in pats if (m := re.search(rf"\b{p}\b", query, re.I))), None)
            if m:
                put(_cand(field, "Equal", value, m.group(0)))
                break

    for field, defn in props.items():
        if "enum" not in defn or field in out:
            continue
        if event == "ANPR Properties" and field == "VehicleColor":
            colors = "|".join(defn["enum"])
            m = re.search(rf"\b({colors})\s+(?:colou?red\s+)?(?:\w+\s+)?{VEHICLE}\b", query, re.I)
            if m:
                put(_cand(field, "Equal", m.group(1).capitalize(), m.group(0)))
            continue
        synonyms = ENUM_SYNONYMS.get((event, field), {v: re.escape(v) for v in defn["enum"]})
        if event == "ANPR Properties" and field == "Category":
            # prefer the category word that sits next to a vehicle word ("stolen red bike")
            near = {v: rf"(?:{p})\s+(?:\w+\s+)?{VEHICLE}" for v, p in synonyms.items()}
            put(_vocab(query, field, near) or _vocab(query, field, synonyms))
        else:
            put(_vocab(query, field, synonyms))

    if "plateNumber" in props:
        m = re.search(r"\b(?:plate|registration|reg\.?)\s*(?:number|no\.?)?\s*(?:is|:|=|of)?\s*"
                      r"([A-Za-z]{2}[\s-]?\d[A-Za-z0-9\s-]{3,10}?\d)\b", query, re.I)
        if m:
            put(_cand("plateNumber", "Equal", re.sub(r"[\s-]", "", m.group(1)).upper(), m.group(0)))
    if "personName" in props:
        m = re.search(r"\b(?:named|called|name\s+is)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", query)
        if m:
            put(_cand("personName", "Equal", m.group(1), m.group(0)))

    for field in ("identity", "area"):
        if field in props:
            put(_vocab(query, field, STRING_VOCAB[field]))

    if "type" in props:
        put(_vocab(query, "type", TYPE_VOCAB.get(event, _VEHICLE_TYPES)))

    zone_field = next((f for f in ("zoneid", "zoneId", "zoneID", "Zone") if f in props), None)
    if zone_field:
        m = re.search(r"\bzone\s*(?:id\s*)?[:#-]?\s*z?(\d+)\b", query, re.I)
        if m:
            put(_cand(zone_field, "Equal", f"Z{m.group(1)}", m.group(0)))
    m = re.search(r"\blane\s*(?:no\.?|number)?\s*(\d)\b", query, re.I)
    if m and "LaneName" in props:
        put(_cand("LaneName", "Equal", f"Lane {m.group(1)}", m.group(0)))
    if m and "laneNo" in props:
        put(_cand("laneNo", "Equal", m.group(1), m.group(0)))
    if "vehicle_view" in props:
        m = (re.search(r"\b(front|rear|back|side)[\s-]+(?:view|facing|angle)\b", query, re.I)
             or re.search(r"\b(?:view|facing)\s+(?:from\s+)?(?:the\s+)?(front|rear|back|side)\b", query, re.I))
        if m:
            put(_cand("vehicle_view", "Equal", {"back": "rear"}.get(m.group(1).lower(), m.group(1).lower()), m.group(0)))
    if event == "Crowd Detected Properties" and "speed" in props:
        m = re.search(r"\b(slow|normal|fast)(?:[\s-]moving)?\b", query, re.I)
        if m:
            put(_cand("speed", "Equal", m.group(1).lower(), m.group(0)))

    return list(out.values())


async def extract_fields(query: str, matched_events: list[dict]) -> list[dict]:
    """Same result shape as nodes.fields.run.extract_fields_with_error_handling().

    Unlike AI mode, rules scan the whole query rather than just query_part,
    since keyword rules need the surrounding words for context."""
    schemas = schemas_by_title()
    validator = ResponseValidator(str(config.SCHEMA_DIR))
    results = []
    for event in matched_events:
        name = event["event_name"]
        schema = schemas.get(name)
        if schema is None:
            results.append({**event, "relevant_fields": [], "error": {"type": "schema_not_found"}})
            continue
        candidates = _candidates(name, schema, query)
        valid = await validate_fields(name, candidates, schema, validator) if candidates else []
        results.append({**event, "relevant_fields": valid})
    return results
