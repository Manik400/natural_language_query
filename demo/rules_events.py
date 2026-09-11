"""
Keyword rules standing in for the event-selection and attribute LLMs
(offline mode, used when no LLM key is configured).

Attribute candidates go through the project's own attribute validators
(nodes/attributes/validate.py), so the output shape is identical to AI mode.
"""

from __future__ import annotations

import re

from nodes.attributes.schema_loader import load_attributes
from nodes.attributes.validate import build_conditions, pre_validate

VEHICLE = (r"(?:bikes?|motorbikes?|motorcycles?|scooters?|two[- ]wheelers?|cars?|"
           r"vehicles?|trucks?|lorry|lorries|bus|buses|vans?|autos?|riders?|drivers?)")
_RIDING = r"\b(?:riders?|riding|bikes?|motorbikes?|motorcycles?|scooters?|two[- ]wheelers?)\b"

EVENT_KEYWORDS: dict[str, list[str]] = {
    "ANPR Properties": [
        r"\b(?:number|licen[cs]e|registration)\s+plates?\b", r"\bplates?\b", r"\banpr\b",
        r"\bred[\s-]?light\b", r"\btraffic\s+signals?\b", r"\bsignal\s+(?:jump|violation)",
        r"\bjump(?:ed|ing)?\s+(?:the\s+)?(?:red\s+)?signal", r"\bspeed\s+limit\b",
        r"\bover[\s-]?speed", r"\bspeeding\b(?!\s+up)", r"\btri?pple\s+riding\b",
        rf"\b(?:stolen|wanted|lost|suspicious|suspecious|unauthori[sz]ed|authori[sz]ed)\s+(?:\w+\s+)?{VEHICLE}\b",
        rf"\b(?:red|green|blue|yellow|orange)\s+(?:colou?red\s+)?{VEHICLE}\b",
    ],
    "Face Recognition Properties": [
        r"\bfaces?\b", r"\bfacial\b", r"\bnamed\b", r"\bperson(?:'s)?\s+name\b", r"\bemotions?\b",
        r"\b(?:angry|anger|happy|smiling|sad|scared|afraid|surprised|disgusted)\b",
        r"\bmasks?\b", r"\b(?:glasses|spectacles)\b", r"\bgender\b",
        r"\b(?:male|female)\s+(?:person|people|persons|visitors?|individuals?|employees?)\b",
        r"\b(?:man|woman|men|women)\b", r"\bage[ds]?\b", r"\byears?\s+old\b",
        r"\bwatch\s?list", r"\bblack\s?list", r"\bvips?\b", r"\bidentit(?:y|ies)\b",
        r"\bwanted\s+(?:person|man|woman|criminal|suspect|individual)", r"\bsuspects?\b",
        r"\bunknown\s+(?:person|people|faces?|individuals?)",
    ],
    "Crowd Detected Properties": [
        r"\bcrowd", r"\bgatherings?\b", r"\bmob\b", r"\bpeople\s+gathered", r"\bovercrowd",
        r"\bcongregat",
    ],
    "Highway ATCC Properties": [
        r"\batcc\b", r"\btraffic\s+(?:count|volume|density|flow)",
        r"\bvehicle\s+(?:count|counts|classification|volume)",
        r"\bcount(?:s|ing)?\s+of\s+(?:cars|trucks|buses|vehicles|motorbikes|bikes|autos)",
        r"\bhow\s+many\s+(?:cars|trucks|buses|vehicles|motorbikes|bikes)",
        r"\b(?:more|less|fewer)\s+than\s+\d+\s+(?:cars|trucks|buses|motorbikes|bicycles|tractors|vans)",
        r"\be[\s-]?rickshaws?\b", r"\bauto[\s-]?rickshaws?\b", r"\btractors?\b",
        r"\bmini[\s-]?(?:bus|truck)", r"\b(?:cows?|cattle|animals?)\s+on\s+(?:the\s+)?(?:road|highway)",
    ],
    "Collison Detected Properties": [
        r"\bcollisions?\b", r"\bcollison", r"\bcollid", r"\bcrash", r"\baccidents?\b",
    ],
    "Human Crossing Road Properties": [
        r"\bcross(?:ing|ed|es)?\s+(?:the\s+)?(?:road|street|highway)", r"\bjaywalk",
        r"\bpedestrians?\s+crossing",
    ],
    "Illegal Vehicle Properties": [
        r"\billegal(?:ly)?\s+(?:parked|vehicles?|parking|entry)", r"\bno[\s-]parking\b",
        r"\bwrong(?:ly)?\s+parked", r"\bheavy\s+vehicles?\s+ban",
        rf"\b{VEHICLE}\b[^.]*\b(?:restricted|prohibited)\s+(?:zone|area)",
    ],
    "Lane Changed Properties": [
        r"\blane\s+chang", r"\bchang(?:ed|ing|es)\s+(?:the\s+)?lanes?",
        r"\blane\s+(?:violation|cutting|departure)", r"\bswitch(?:ed|ing)\s+lanes?",
    ],
    "Objects Entered Properties": [
        r"\bentered\b", r"\bentering\b", r"\bentr(?:y|ies)\s+counts?", r"\bexit(?:ed|ing)?\s+counts?",
        r"\bfootfall", r"\bpeople\s+count", r"\b(?:came|walked|went)\s+(?:in|out)\b",
        r"\bcrossed\s+the\s+line\b", r"\b(?:entries|exits)\b",
    ],
    "Perimeter Violation Properties": [
        r"\bperimeter", r"\bintru(?:sion|ders?)", r"\btrespass", r"\bbreach", r"\bfence",
        r"\bboundary", r"\bclimb(?:ed|ing)?\s+(?:over|the)\b", r"\bunauthori[sz]ed\s+(?:entry|access)",
    ],
    "Reverse Traffic Properties": [
        r"\brevers(?:e|ing|ed)\b", r"\bbacking\s+up\b", r"\bwrong[\s-](?:way|direction|side)\b",
        r"\bagainst\s+(?:the\s+)?traffic\b",
    ],
    "Safety Gear Violation Properties": [
        r"\bppe\b", r"\bsafety\s+(?:gears?|equipment|vests?|shoes|boots|belts?|helmets?|jackets?)",
        r"\bhard\s*hats?\b", r"\breflective\s+(?:jackets?|vests?)", r"\bharness", r"\bvests?\b",
    ],
    "Vehicle Accelerated Properties": [
        r"\baccelerat", r"\bspeed(?:ing|ed)?\s+up\b", r"\brapid(?:ly)?\s+speed",
        r"\baggressive\s+driving",
    ],
    "Vehicle Stopped Properties": [
        r"\bstopped\b", r"\bstationary\b", r"\bhalted\b", r"\bstalled\b", r"\bbreak\s*down\b",
        r"\bbroken\s+down\b", r"\bidle\s+vehicles?", r"\bparked\s+on\s+(?:the\s+)?(?:road|highway|shoulder)",
    ],
}

# Only used when nothing more specific matched (mirrors rule 7 of the LLM prompt).
FALLBACK_EVENT = ("Motion Analysis Properties",
                  [r"\bmotion\b", r"\bmovements?\b", r"\bloiter", r"\bdwell", r"\bactivity\s+in\b"])

# Punctuation only counts as a boundary when followed by a space/end, so IPs
# like 192.168.9 and decimals stay intact.
_CLAUSE_BOUNDARY = re.compile(r"[,.;!?](?=\s|$)|\b(?:and|also|then|while|where|but|with)\b", re.I)


def _context_span(query: str, start: int, end: int, context_words: int = 3) -> tuple[int, int]:
    """Character span around [start, end): up to a few words either side,
    never crossing a clause boundary."""
    left, right = 0, len(query)
    for b in _CLAUSE_BOUNDARY.finditer(query):
        if b.end() <= start:
            left = b.end()
        elif b.start() >= end:
            right = b.start()
            break
    before = list(re.finditer(r"\S+", query[left:start]))[-context_words:]
    after = list(re.finditer(r"\S+", query[end:right]))[:context_words]
    return (left + before[0].start() if before else start,
            end + after[-1].end() if after else end)


def _query_part(query: str, spans: list[tuple[int, int]]) -> str:
    """Merge overlapping context spans and join them in query order."""
    merged: list[list[int]] = []
    for s, e in sorted(spans):
        if merged and s <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return " … ".join(query[s:e].strip(" ,.;") for s, e in merged)


def select_events(query: str) -> dict:
    """Same result shape as nodes.events.run.select_events_with_error_handling()."""
    spans: dict[str, list[tuple[int, int]]] = {}

    def add(event: str, match: re.Match):
        spans.setdefault(event, []).append(_context_span(query, match.start(), match.end()))

    for event, patterns in EVENT_KEYWORDS.items():
        for pattern in patterns:
            for m in re.finditer(pattern, query, re.I):
                add(event, m)

    # Helmet rule: rider/bike context → ANPR, otherwise → safety gear.
    for m in re.finditer(r"\bhelmets?\b", query, re.I):
        target = "ANPR Properties" if re.search(_RIDING, query, re.I) else "Safety Gear Violation Properties"
        add(target, m)

    if not spans:
        event, patterns = FALLBACK_EVENT
        for pattern in patterns:
            for m in re.finditer(pattern, query, re.I):
                add(event, m)

    matched = [{"event_name": e, "query_part": _query_part(query, s)} for e, s in spans.items()]
    return {"status": "success", "matched_events": matched}


def extract_attribute_conditions(query: str) -> dict:
    """Same shape as the attribute_conditions state key written in AI mode."""
    attributes = load_attributes()
    attribute_map = {a.key: a for a in attributes}

    items = []
    for key in attribute_map:
        label = re.escape(key.replace("_", " "))
        m = re.search(
            rf"\b{label}\b\s*(?:is|was|=|:|of|as|equals?)?\s*"
            r"(not\s+|contains\s+|includes\s+|like\s+|in\s+|near\s+)?(.+?)\s*(?:[.;!?](?:\s|$)|$)",
            query, re.I,
        )
        if not m or not m.group(2).strip():
            continue
        modifier = (m.group(1) or "").strip().lower()
        operator = {"not": "NOTEQUAL", "contains": "CONTAINS", "includes": "CONTAINS",
                    "like": "CONTAINS", "in": "CONTAINS", "near": "CONTAINS"}.get(modifier, "EQUAL")
        items.append({"key": key, "operator": operator,
                      "raw_value": m.group(2).strip(), "raw_slice": m.group(0).strip(" .")})

    conditions = build_conditions(pre_validate(items, attribute_map), attribute_map)
    if not conditions:
        return {"conditionType": None, "conditions": []}
    condition_type = "ANY" if len(conditions) > 1 and re.search(r"\bor\b", query, re.I) else "ALL"
    return {"conditionType": condition_type, "conditions": [c.model_dump() for c in conditions]}
