# Natural Language Query Pipeline: Code Structure

> Companion doc: [OVERVIEW.md](OVERVIEW.md) explains *what the system does and which algorithms it uses*. This file explains *where everything lives and what each file does*.

---

## 1. Directory tree

```
natural_language_query-master/
│
├── app.py                    # Streamlit UI: query box → POST /pipeline → rendered cards
├── graph.py                  # LangGraph state machine: nodes, edges, router, run_pipeline()
├── pipeline_nodes.py         # Graph node functions: thin wrappers that call nodes/* and shape state
├── state.py                  # PipelineState TypedDict + source-attribution types + reducer
├── transform.py              # Raw NLP JSON → downstream search-API payload
├── config.py                 # Artifact paths + Settings (.env: LLM model/key/base URL/timeout)
├── logger.py                 # Structured JSON logging + request_id/node_name context vars
├── exceptions.py             # Typed exception hierarchy (NLIPipelineException and subclasses)
├── requirements.txt          # Pinned dependencies
├── .pre-commit-config.yaml   # black, isort, flake8, large-file check
├── .gitignore                # ignores .env, pipeline.log, __pycache__
├── README.md                 # Original project README
├── __init__.py               # (empty)
│
├── api/                      # FastAPI application
│   ├── main.py               # App factory: registers routers + exception handlers
│   ├── schemas.py            # QueryRequest {query, transform}
│   ├── handlers.py           # HTTPException handler
│   └── routers/
│       ├── pipeline.py       # POST /pipeline: the main endpoint
│       ├── debug.py          # POST /debug/{datetime,video_resources,events,fields,attributes}
│       ├── sync.py           # POST /sync/{attributes,video_resources,events_schema}
│       ├── artifacts.py      # GET  /artifacts/{attributes,video_resouces,events}
│       └── health.py         # GET  /health, /status
│
├── llm/
│   ├── client.py             # get_llm() → ChatOpenAI configured from Settings
│   └── __int__.py            # (empty; typo of __init__.py)
│
├── nodes/                    # One package per extraction stage
│   ├── events/               # Which analytics event(s) does the query mean?     (LLM)
│   ├── attributes/           # Person/entity attribute conditions                (LLM)
│   ├── fields/               # Per-event field filters                           (LLM function calling)
│   ├── time/                 # Time intent → concrete date range                 (LLM + Python)
│   └── video_resource/       # Camera matching                                   (pure Python)
│
├── sync/                     # Schema synchronisation from the main platform
│   ├── models.py             # RuleType enum, RuleType→JSON-type map, request models
│   ├── schema_sync.py        # Hash-based change detection, schema build/patch, parallel save
│   └── schema_docs.py        # LLM-generated event/property descriptions
│
├── artifacts/                # Runtime "knowledge base" (data, not code)
│   ├── events_schema/        # 15 JSON Schemas, one per analytics event
│   ├── video_resources.json  # 97 cameras {id, name, ip, type}
│   └── attributes.json       # Declared attribute keys + types
│
├── annotate/                 # Streamlit tools for humans to correct LLM output
│   ├── events.py
│   ├── fields.py
│   └── time.py
│
└── evaluate/                 # Offline evaluation
    ├── response_generator.py # Batch-calls /debug/<stage> for a queries file
    ├── metric/{events,fields,time}.py   # Precision/recall/F1 scorers
    ├── data/{events,fields,time}/       # queries.jsonl, response.jsonl, annotated.jsonl
    └── results/*.json                   # Stored metric outputs
```

---

## 2. Layered architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│  PRESENTATION   app.py (Streamlit)        annotate/*.py (Streamlit)    │
└───────────────┬────────────────────────────────────────────────────────┘
                │ HTTP (requests → localhost:8081)
┌───────────────▼────────────────────────────────────────────────────────┐
│  API            api/main.py → routers: pipeline, debug, sync,          │
│                 artifacts, health                                       │
└───────────────┬────────────────────────────────────────────────────────┘
                │ run_pipeline(query, transform_output)
┌───────────────▼────────────────────────────────────────────────────────┐
│  ORCHESTRATION  graph.py (LangGraph)  +  state.py (PipelineState)      │
│                 pipeline_nodes.py (adapts node results → state keys)   │
│                 transform.py (optional final payload mapping)          │
└───────────────┬────────────────────────────────────────────────────────┘
                │
┌───────────────▼────────────────────────────────────────────────────────┐
│  DOMAIN LOGIC   nodes/events  nodes/attributes  nodes/fields           │
│                 nodes/time    nodes/video_resource                     │
└───────┬───────────────────────────────┬────────────────────────────────┘
        │                               │
┌───────▼──────────────┐     ┌──────────▼─────────────────────────────────┐
│ INFRA  llm/client.py │     │ DATA  artifacts/ (schemas, cameras, attrs) │
│ config.py logger.py  │     │ written by sync/ via /sync/* endpoints     │
│ exceptions.py        │     └────────────────────────────────────────────┘
└──────────────────────┘
```

Dependencies only point **downward**. `nodes/*` never imports from `graph.py` or `api/`, so each node can be tested on its own, and the `/debug/*` endpoints call nodes directly without going through the graph.

---

## 3. Root-level files

### `graph.py`: the state machine
| Item | What it does |
|---|---|
| `_INTERNAL_KEYS = {"matched_events"}` | State keys removed from the final output |
| `route_after_parallel_one(state)` | Returns `"irrelevant"` when there are **no** `matched_events` **and** no attribute condition has a non-empty value. Otherwise `"relevant"` |
| `build_graph()` | Defines the nodes `start`, `event_selection`, `attribute_extraction`, `sync`, `fanout_2`, `time_extraction`, `video_resolution`, `field_extraction`, `irrelevant`, then compiles. `start`, `sync` and `fanout_2` are pass-through (`lambda state: state`) nodes that only exist to shape the fan-out and fan-in |
| `run_pipeline(query, transform_output=False)` | `await graph.ainvoke({"query": query})`, strips the internal keys, and optionally calls `transform()` |
| `pipeline = build_graph()` | A precompiled module-level graph (the API calls `build_graph()` again on every request) |

### `pipeline_nodes.py`: graph node adapters
Each function takes `PipelineState` and returns **only the keys it updates**. They call the public functions in `nodes/*`, and every one catches exceptions.

| Node function | Calls | Writes to state |
|---|---|---|
| `node_event_selection` | `select_events_with_error_handling` | `matched_events`, `status`, `message`, `event_selection_error` |
| `node_attribute_extraction` | `extract_attributes` | `attribute_conditions {conditionType, conditions}`, `attribute_extraction_error` |
| `node_time_extraction` | `time_extraction_with_error_handling` | `time {start, end}`, `source_attributions.time`, `time_extraction_error` |
| `node_video_resolution` (sync) | `VideoResolutionFallbackHandler(...).resolve_with_fallback` | `video_resources {groups, resolved_cameras}`, `source_attributions.video`, `video_resolution_error` |
| `node_field_extraction` | `extract_fields_with_error_handling` | `extracted_fields`, `source_attributions.fields`, `field_extraction_errors` |
| `node_irrelevant` | none | `status="irrelevant"`, `message` |

### `state.py`: the shared state contract
```python
class PipelineState(TypedDict, total=False):
    query: str                                   # input
    time: dict                                   # {start:{date,time}, end:{date,time}}
    video_resources: dict                        # {groups:[...], resolved_cameras:[...]}
    extracted_fields: list[dict]                 # [{event_name, relevant_fields:[...]}]
    attribute_conditions: AttributeConditions    # {conditionType, conditions:[...]}
    matched_events: list[dict]                   # internal, removed from output
    source_attributions: Annotated[SourceAttributions, merge_source_attributions]
    event_selection_error / attribute_extraction_error / time_extraction_error /
    video_resolution_error / field_extraction_error: dict | None
    field_extraction_errors: dict[str, dict]     # per event
    status: str; message: str
```
`merge_source_attributions(a, b) = {**a, **b}` is the **reducer** that lets the three parallel stage-2 nodes each add their own sub-key without overwriting each other.

`SourceAttributions` = `{time: TimeAttribution, video: [VideoAttribution], fields: {event_name: FieldAttribution}}`.

### `transform.py`: API payload mapper
| Function | Role |
|---|---|
| `OPERATOR_MAP` | `{"equal":0, "notequal":1, …, "notlike":12}`, built from `nodes/fields/constants.OPERATORS` list indexes |
| `CONDITION_MAP` | `all/and → 15`, `any/or → 14` |
| `to_epoch_ms(date, time)` | Accepts `YYYY-MM-DD` or `DD-MM-YYYY`, reads the value as IST (+05:30), returns UTC epoch ms |
| `_current_day_range_ms()` | Today 00:00 IST → now (used for irrelevant queries) |
| `build_camera_lookup()` | camera name → UUID from `video_resources.json` |
| `build_attribute_lookup()` | attribute key → valueType from `attributes.json` |
| `load_event_schema` / `get_rule_type` | Look up a field's `ruleType`. ⚠ Uses the wrong filename pattern, so it always returns 1 |
| `transform(query_json)` | Builds `{startTime, endTime, pageNumber, pageLimit, order, resources.Video_Sources, analytics, propertyFilters, AttributeFilters}` |

### `config.py`
```python
VIDEO_JSON_PATH      = Path("artifacts/video_resources.json")
SCHEMA_DIR           = Path("artifacts/events_schema")
ATTRIBUTES_JSON_PATH = Path("artifacts/attributes.json")

class Settings(BaseSettings):   # read from .env
    LLM_MODEL: str              # required
    LLM_TEMPERATURE: float = 0
    LLM_TIMEOUT: int = 120
    OPENAI_API_KEY: str         # required
    LLM_BASE_URL: str           # required (any OpenAI-compatible endpoint)
```
The paths are **relative**, so the server has to be started from the project root.

### `logger.py`
- `StructuredLogFormatter` writes each record as one JSON line: `timestamp, level, logger, message, request_id, node_name, exception`.
- `setup_logging()` sets up a console handler plus a `RotatingFileHandler("pipeline.log", 10 MB, 5 backups)` on the `nli_pipeline` logger.
- `get_logger(name)` returns `nli_pipeline.<name>`.
- `request_id_var` and `node_name_var` are `contextvars`, so every log line inside one request carries the same ID.

### `exceptions.py`
```
NLIPipelineException(message, error_code, node_name, context) → .to_dict()
 ├── QueryValidationException      QUERY_VALIDATION_ERROR
 ├── EventSelectionException       EVENT_SELECTION_ERROR
 ├── TimeExtractionException       TIME_EXTRACTION_ERROR
 ├── VideoResolutionException      VIDEO_RESOLUTION_ERROR
 ├── FieldExtractionException      FIELD_EXTRACTION_ERROR
 ├── LLMException                  LLM_ERROR            (+ llm_error in context)
 ├── AttributeValidationException  ATTRIBUTE_VALIDATION_ERROR (+ key)
 └── TimeoutException              TIMEOUT_ERROR        (+ timeout_seconds)
```

### `app.py`: Streamlit UI
- Posts `{"query": …}` to `http://localhost:8081/pipeline` with a 180 s timeout.
- Renders: a status badge (ok or irrelevant) → the query echo → **row 1:** Time Range card | Video Resources card (groups with a match-type badge, matched token, raw slice, camera chips) | Attribute Conditions card → **row 2:** Extracted Event Fields (one card per event, showing the field, operator, typed value and snippet) → a "Raw Response" expander.
- It's all custom HTML and CSS through `st.markdown(unsafe_allow_html=True)`.

---

## 4. `nodes/`: the extraction stages

Every LLM-based stage follows the **same module pattern**:

| File | Role |
|---|---|
| `prompt.py` | The prompt template (a big string constant or a builder function) |
| `models.py` | Pydantic/dataclass models for the LLM output and results |
| `schema_loader.py` | Loads the relevant `artifacts/` data |
| `parser.py` | Turns the raw LLM text into models (usually `PydanticOutputParser`) |
| `validate.py` | Deterministic checks on the parsed output |
| `constants.py` | Enums, rule tables, registries |
| `run.py` | A `*FallbackHandler` class that runs the stages with error handling, plus a public `*_with_error_handling()` function |

### 4.1 `nodes/events/`
| File | Key contents |
|---|---|
| `schema_loader.py` | `load_event_schemas(dir)`: reads all `*.json` concurrently with `aiofiles` and returns `[{title, description, fields}]`. Files without a `title` are skipped |
| `prompt.py` | `EVENT_SELECTION_PROMPT`: domain definitions, 7 disambiguation rules, multi-event rule, matching strategy, strict JSON output format |
| `prompt_builder.py` | `build_events_block()` formats `TITLE:/DESCRIPTION:` lines. `build_prompt()` returns `(prompt, valid_event_titles)` |
| `models.py` | `MatchedEvent{event_name, query_part}`, `MatchedEvents{matched_events: [...]}` |
| `parser.py` | `parse_llm_output(raw)` → `(MatchedEvents, None)` or `(None, error)`. Accepts either a string or an `AIMessage` |
| `validate.py` | `validate_events(events, whitelist)` → `(valid, hallucinated)` |
| `run.py` | `EventSelectionFallbackHandler.select_events_with_fallback()`: 5 stages (load → prompt → LLM with 3 attempts / 30 s → parse → validate + `_merge_duplicate_events`). `select_events_with_error_handling()` turns exceptions into `{status, matched_events: [], error}` |

### 4.2 `nodes/attributes/`
| File | Key contents |
|---|---|
| `constants.py` | `AttributeValueType` (string 0, number 1, boolean 2). `Operators` IntEnum (EQUAL 0 … ALL 15). `ConditionType` (ANY 14, ALL 15). `MULTI_VALUE_OPERATORS`. `OPERATOR_RULES`: allowed value types plus the expected shape (`scalar`, `list`, `range`, `none`) for each operator |
| `schema_loader.py` | `load_attributes()` reads `attributes.json` into `[Attribute{key, valueType}]`, failing loudly on bad entries |
| `prompt.py` | `build_extraction_prompt(query, attributes)` fills in the declared keys, operators and condition types, and asks for `{conditionType, conditions:[{key, operator, raw_value, raw_slice}]}` |
| `parser.py` | `parse_value(raw, type, operator)` handles type coercion and comma-splitting for multi-value operators, and requires exactly 2 values for BETWEEN |
| `validate.py` | `pre_validate()` (key, operator, raw_slice present) → `build_conditions()` (duplicates, coercion, `validate_operator`) |
| `models.py` | `Attribute`, `AttributeExtractionResult{key, valueType, operator, value, raw_slice}`, `ExtractionResult{conditionType, conditions}`. Enums are serialised as names |
| `run.py` | `extract_attributes(query)`: load → prompt → LLM → `json.loads` → resolve `conditionType` → pre-validate → build. Raises on LLM failure or bad JSON (the graph node catches it) |

### 4.3 `nodes/fields/`
| File | Key contents |
|---|---|
| `constants.py` | `OPERATORS` list of 13 names. **The list index is the API operator code** |
| `schema_loader.py` | `normalize_event_to_filename("ANPR Properties") → "anpr.json"`. `load_schema()`. `build_tool_schema(event, schema)` builds the function-calling schema: `relevant_fields[]` of `{field: enum, operator: enum or null, value: union, query_snippet}` |
| `prompt.py` | `FIELD_EXTRACTION_PROMPT`: strict rules, field-uniqueness rule, operator specificity order, allowed operators |
| `validate.py` | `ResponseValidator` (operator/type rules, a `$id` schema registry for `$ref` resolution, `schema_validation()` with a Draft 2020-12 validator). `_validate_against_tool_schema()` is stage 1. `validate_fields()` runs both stages and keeps only `valid=True` |
| `models.py` | `RelevantField`, `EventFieldResult`, `MatchedEventsResponse` |
| `run.py` | `FieldExtractionFallbackHandler.extract_for_event_with_fallback()`: 6 stages (schema → tool schema → prompt → structured LLM call with a 20 s timeout → null filter → validation). `extract_fields_with_fallback()` runs every event through `asyncio.gather(return_exceptions=True)` |

### 4.4 `nodes/time/`
| File | Key contents |
|---|---|
| `constants.py` | `MONTH_NAME_TO_NUM`, `WEEKDAY_ORDER` (mon=1…sun=7), `QUARTER_BOUNDS`. `INTENT_REGISTRY[intent][subclass] = {required, optional}` for all 18 subclasses. `ALLOWED_VALUES` for enum params |
| `prompt.py` | `CLASSIFIER_PROMPT`: 5 steps (raw snippet → taxonomy → normalisation rules → output schema → self-check), including the last/past/previous disambiguation table |
| `utility.py` | `build_anchors(now)` → `Anchors(current_date, current_time, current_weekday)`. `build_classifier_prompt(query)` (no date is injected into the prompt) |
| `models.py` | `Anchors` (normalises to `DD-MM-YYYY` and has `day()`, `month()`, `year()`, `weekday_num()`). `ParsedIntent{raw_time_query, timeIntent, timeIntentSubClass, params}` with the safe accessor `p()`. `ValidationResult`. `ResolvedDateTime{start, end, …}` |
| `parser.py` | `PydanticOutputParser(ParsedIntent)` wrapper |
| `validate.py` | `validate_llm_response(raw)`: parse → `_validate_registry` → `_validate_logical` (formats, ranges, enum values, time ordering for single-day subclasses, date ordering, month-range ordering) |
| `dispatcher.py` | `DISPATCHER[intent][subclass] → resolver function`. `dispatch(validation, anchors)` |
| `resolver.py` | One function per subclass (`resolve_current_period`, `resolve_rolling_window`, `resolve_completed_period`, `resolve_future_window`, `resolve_offset_from_anchor_date`, `resolve_full_year`, `resolve_single_month`, `resolve_month_to_month_range`, `resolve_today_or_yesterday`, `resolve_weekday_reference`, `resolve_specific_date`, `resolve_explicit_date_range`, `resolve_date_to_now_range`, `resolve_null`), plus helpers `_add_days`, `_add_months` (with clamping), `_apply_unit`, `_parse_hhmmss`, `_end_time` |
| `run.py` | `TimeExtractionFallbackHandler.time_extraction_with_fallback()`: anchors → prompt → LLM (20 s) → parse → validate → dispatch. Any failure returns `get_default_fallback()` (today 00:00 → now) |

### 4.5 `nodes/video_resource/`
| File | Key contents |
|---|---|
| `models.py` | `FlatCamera{path, camera_name, ip, match_type, matched_token, matched_raw_slice, confidence}`. `key = (tuple(path), camera_name)` |
| `tree.py` | `flatten_tree()`, `build_node_index()` (folder → subtree cameras), `build_ip_index()` (ip → camera). Supports a nested `folder` / `camera` tree |
| `tokenizer.py` | `_IP_RE`, `extract_ips()`, `strip_ips()`, `split_clauses()` (on `,` and `and`), `strip_stopwords()`, `extract_tokens_prioritized()` (compound tokens + all n-grams longest-first, each with word positions) |
| `matching.py` | `normalize()`, `normalize_full()`, `is_meaningful()` (at least 3 chars and not a stopword), `exact_match()`, `partial_match()`, `fuzzy_score()` (RapidFuzz `token_set_ratio` + digit guard + coverage penalty), `score_match()` cascade, `match_ip_exact()`, `match_ip_prefix()` |
| `constants.py` | `FUZZY_THRESHOLD = 75`. `MATCH_ORDER` (exact 0 = ip 0 < partial 1 < fuzzy 2). `STOPWORDS` (~200 words, grouped with comments explaining why each group is included) |
| `resolver.py` | `_lookup_token()` (best folder vs camera candidate with 5-key tie-breaking), `_raw_slice()`, `_resolve_ips()`, `_resolve_clause()` (greedy non-overlapping selection + intersection), `resolve_video_resources()` (union across clauses, ranked `FlatCamera` list) |
| `run.py` | `VideoResolutionFallbackHandler` loads the JSON and builds the 3 indexes **on each construction** (so on every request). `_format_results()` groups by `(token, type, confidence, slice)` and sorts. `resolve_with_fallback()` |

---

## 5. `api/`: HTTP surface

Start it with `uvicorn api.main:app --host 0.0.0.0 --port 8081`. OpenAPI docs are at `/docs`.

| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/pipeline` | `{"query": str, "transform": bool=false}` | The full pipeline output (raw, or the API payload when `transform=true`) plus `request_id`. Returns `{status:"irrelevant", message, request_id}` when nothing relevant is found. 504 on timeout, 500 on unexpected errors |
| POST | `/debug/datetime` | `{"query"}` | The time stage alone: `{llm_response, validation, resolved, error?}` |
| POST | `/debug/video_resources` | `{"query"}` | The video stage alone: `{groups, resolved_cameras}` |
| POST | `/debug/events` | `{"query"}` | The event stage alone: `{status, matched_events}` |
| POST | `/debug/fields` | `{"query"}` | Events → fields (without the graph): `[{event_name, query_part, relevant_fields}]` |
| POST | `/debug/attributes` | `{"query"}` | `{status, result:{conditionType, conditions}}` |
| POST | `/sync/attributes` | `[{key, valueType:0-2}]` | Overwrites `attributes.json` |
| POST | `/sync/video_resources` | `[{id, name, ip, type}]` | Overwrites `video_resources.json` (`videoSource` → `camera`) |
| POST | `/sync/events_schema` | `[{name, properties:[{name, type:<RuleType int>}]}]` | Incremental schema sync → `{updated, skipped}` |
| GET | `/artifacts/attributes` | none | The declared attributes |
| GET | `/artifacts/video_resouces` | none | Cameras (`type: "videoSource"`) |
| GET | `/artifacts/events` | none | `[{name, properties:[{name, ruleType}]}]` |
| GET | `/health`, `/status` | none | Liveness info |

---

## 6. `sync/`: keeping `artifacts/` in step with the main platform

The main VMS platform pushes its event definitions here. `sync_event_schemas(events)` works like this:

1. `load_existing_schemas()` reads every schema, keyed by title without the " Properties" suffix.
2. `detect_schema_changes()` computes `sha256({"event": name, "properties": sorted(names)})` and compares it with the stored `schemaHash`. Only **new or changed** events continue past this step. The hash doesn't include property *types*.
3. `process_event()` runs in a `ThreadPoolExecutor(max_workers=6)`:
   - **New event:** `generate_event_and_property_docs()` asks the LLM for a one-sentence description of the event and each property, then `build_schema()` creates a Draft 2020-12 schema with `ruleType` → JSON type/format taken from `RULETYPE_TO_JSON`.
   - **Existing event:** it deletes removed properties and generates docs **only for the new ones**.
4. `save_schema()` writes `snake_case_name.json` with the new `schemaHash`.

The descriptions matter because **event selection only sees each event's title and description**. Better descriptions lead to better event matching.

`sync/models.py` → `RuleType` codes: number 0, string 1, float 2, boolean 3, ipAddress 4, dateTime 5, image 6, date 7, timeOfDay 8, dayOfWeek 9, imagePath 10, unixDateTime 11, filePath 12, array 13, custom 14, vector 18, guid 19, ArrayOfObject 21, Double 23, dateRange 24.

---

## 7. `artifacts/`: data formats

### Event schema (`artifacts/events_schema/anpr.json`, shortened)
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://example.com/schemas/anpr-properties.json",
  "title": "ANPR Properties",
  "description": "Detects vehicles using automatic number plate recognition ...",
  "type": "object",
  "properties": {
    "plateNumber":  { "type": "string",  "ruleType": 1, "description": "..." },
    "speed":        { "type": "number",  "ruleType": 0, "minimum": 0 },
    "VehicleColor": { "type": "string",  "ruleType": 1, "enum": ["Red","Green","Blue","Yellow","Orange"] },
    "Category":     { "type": "string",  "ruleType": 1, "enum": ["Stolen","Wanted","Lost","Suspecious","Authorized","Unauthorized"] },
    "noHelmet":     { "type": "boolean", "ruleType": 3 }
  },
  "minProperties": 1,
  "unevaluatedProperties": false
}
```
- `title` + `description` are used by **event selection**.
- `properties` (type, enum, minimum) are used by **field extraction and validation**.
- `ruleType` is used by **transform**.
- `$id` is required, because the field validator builds its `$ref` registry from it.

The 15 events, with their property counts: ANPR (9), Collison Detected (3), Crowd Detected (5), Face Recognition (8), Highway ATCC (23), Human Crossing Road (3), Illegal Vehicle (3), Lane Changed (5), Motion Analysis (5), Objects Entered (14), Perimeter Violation (3), Reverse Traffic (3), Safety Gear Violation (4), Vehicle Accelerated (3, file misspelled `vehicle_accelated.json`), Vehicle Stopped (4).

### `video_resources.json`
```json
[ { "id": "77a32339-...", "name": "PAPA_JOHNS_ENTRY_CAM01", "ip": "192.168.9.12", "type": "camera" }, ... ]
```
Right now this is a flat list of 97 cameras. The resolver also accepts nested `{"type": "folder", "name": ..., "children": [...]}` entries, and a `{"video_resources": [...]}` wrapper.

### `attributes.json`
```json
[ { "key": "address", "valueType": "string" } ]
```

---

## 8. Output contracts

### Raw pipeline output (`POST /pipeline`, `transform: false`). Illustrative example
```json
{
  "query": "...stolen red bike with plate number HR5653RT78 ... last 7 days from ip source 192.168.9 ... address is mg road, gurugram",
  "status": "success",
  "message": null,
  "event_selection_error": null,
  "attribute_conditions": {
    "conditionType": "ALL",
    "conditions": [
      { "key": "address", "valueType": "string", "operator": "EQUAL",
        "value": "mg road, gurugram", "raw_slice": "his address is mg road, gurugram" }
    ]
  },
  "attribute_extraction_error": null,
  "time": { "start": { "date": "04-09-2026", "time": "00:00:00" },
            "end":   { "date": "11-09-2026", "time": "14:30:00" } },
  "video_resources": {
    "groups": [ { "matched_token": "192.168.9", "matched_raw_slice": "192.168.9",
                  "match_type": "ip", "confidence": 75.0,
                  "cameras": ["PAPA_JOHNS_ENTRY_CAM01", "DR_PEPPER_ENTRY_CAM01"] } ],
    "resolved_cameras": ["PAPA_JOHNS_ENTRY_CAM01", "DR_PEPPER_ENTRY_CAM01"]
  },
  "extracted_fields": [
    { "event_name": "ANPR Properties",
      "relevant_fields": [
        { "field": "Category",     "operator": "Equal", "value": "Stolen" },
        { "field": "VehicleColor", "operator": "Equal", "value": "Red" },
        { "field": "plateNumber",  "operator": "Equal", "value": "HR5653RT78" } ] }
  ],
  "source_attributions": {
    "time":   { "raw_time_query": "last 7 days", "time_intent": "relative",
                "intent_subclass": "rolling_window", "resolved_start": "04-09-2026 00:00:00",
                "resolved_end": "11-09-2026 14:30:00" },
    "video":  [ { "matched_token": "192.168.9", "match_type": "ip", "confidence": 75.0, "cameras": ["..."] } ],
    "fields": { "ANPR Properties": { "query_part": "stolen red bike with plate number HR5653RT78",
                "fields": [ { "field": "Category", "operator": "Equal", "value": "Stolen",
                              "query_snippet": "stolen" } ] } }
  },
  "time_extraction_error": null,
  "video_resolution_error": null,
  "field_extraction_errors": {},
  "request_id": "8c0b…"
}
```

### Transformed payload (`transform: true`)
```json
{
  "startTime": 1788460200000,          // 04-09-2026 00:00:00 IST as UTC epoch ms
  "endTime":   1789117200000,          // 11-09-2026 14:30:00 IST
  "pageNumber": 1, "pageLimit": 50, "order": "DESC",
  "resources": { "Video_Sources": ["77a32339-…", "d247de39-…"] },
  "analytics": ["ANPR"],
  "propertyFilters": {
    "ANPR": { "condition": "AND", "rules": [
      { "field": "Category", "operator": 0, "value": "Stolen", "type": 1, "rules": [] } ] }
  },
  "AttributeFilters": {
    "field": "attributes", "operator": 15, "rules": [], "type": 21,
    "value": "[{\"key\":\"address\",\"valueType\":0,\"condition\":0,\"value\":\"mg road, gurugram\"}]"
  },
  "request_id": "8c0b…"
}
```
(The epoch values are computed for the example dates shown. The key names and structure match `transform.py` exactly. `"type": 1` for every rule comes from the ruleType lookup bug described in OVERVIEW.md §9.)

### Operator code tables
| Field operators (`transform.OPERATOR_MAP`) | Code | | Attribute `Operators` enum | Code |
|---|---|---|---|---|
| Equal | 0 | | EQUAL | 0 |
| NotEqual | 1 | | NOTEQUAL | 1 |
| GreaterThan | 2 | | GREATERTHAN | 2 |
| SmallerThan | 3 | | SMALLERTHAN | 3 |
| GreaterThanOrEqual | 4 | | GREATERTHANOREQUAL | 4 |
| SmallerThanOrEqual | 5 | | SMALLERTHANOREQUAL | 5 |
| Contains | 6 | | CONTAINS | 6 |
| NotContains | 7 | | NOTCONTAINS | 7 |
| In | **8** | | WASUPDATED | 8 |
| NotIn | **9** | | IN | **9** |
| Between | **10** | | NOTIN | **10** |
| Like | **11** | | BETWEEN | **11** |
| NotLike | **12** | | LIKE / NOTLIKE | 12 / 13 |
| | | | ANY / ALL | 14 / 15 |

The two tables **disagree from code 8 onward**. See OVERVIEW.md §9.

---

## 9. `annotate/` and `evaluate/`: the quality loop

| File | What it is |
|---|---|
| `evaluate/response_generator.py` | CLI: reads `queries.jsonl`, POSTs each query to `/debug/<endpoint>` (concurrency 2, 3 retries with backoff, 60 s timeout), writes `response.jsonl` |
| `annotate/events.py` | Streamlit tool: shows each query with the LLM's matched events. A human adds or removes events and edits spans. Saves `annotated.jsonl` atomically (temp file + `fsync` + move) |
| `annotate/fields.py` | Same idea for fields. Widgets come from each event schema (enum dropdowns, types, min/max) |
| `annotate/time.py` | Same idea for time. Intent/subclass dropdowns and parameter widgets come from `INTENT_REGISTRY` / `ALLOWED_VALUES`, with HHMMSS validation |
| `evaluate/metric/events.py` | Per-event multiset TP/FP/FN → precision, recall, F1, Jaccard accuracy, macro + micro |
| `evaluate/metric/fields.py` | Per event × per field. Flags `--match_operator` and `--match_value` make matching stricter |
| `evaluate/metric/time.py` | Intent-level and subclass-level confusion counts → precision, recall, F1 |
| `evaluate/data/*/` | Datasets: events 717, fields 610, time 308 queries |
| `evaluate/results/*.json` | Stored scores. Summary in OVERVIEW.md §6 |

All metric scripts share the flag `--reviewed_only` (only score annotations a human has confirmed) and `--output <file.json>`.

---

## 10. Running it

1. Create a `.env` in the project root:
   ```env
   OPENAI_API_KEY=sk-...
   LLM_MODEL=gpt-4o-mini
   LLM_BASE_URL=https://api.openai.com/v1
   # optional: LLM_TEMPERATURE=0, LLM_TIMEOUT=120
   ```
2. Install the dependencies. `aiofiles` and `jsonschema` are missing from requirements.txt, so they're added here:
   ```bash
   pip install -r requirements.txt aiofiles jsonschema
   ```
3. Start the API from the project root, because the artifact paths are relative:
   ```bash
   uvicorn api.main:app --host 0.0.0.0 --port 8081
   ```
4. Start the UI:
   ```bash
   streamlit run app.py
   ```
5. Evaluation, which needs the API running:
   ```bash
   python evaluate/response_generator.py -e events -i evaluate/data/events/queries.jsonl -o evaluate/data/events/response.jsonl
   ```
   ```bash
   python evaluate/metric/events.py --reviewed_only --output evaluate/results/events_result.json
   ```
6. Annotation:
   ```bash
   streamlit run annotate/events.py
   ```

---

## 11. How to extend

| You want to… | Do this |
|---|---|
| **Add a new event type** | `POST /sync/events_schema`, or add `artifacts/events_schema/<snake_name>.json` with `$id`, `title` ("X Properties"), a clear `description`, and `properties` that each have a `type` and `ruleType`. The filename must equal `normalize_event_to_filename(title)`. If the new event overlaps an existing one, add a disambiguation rule in `nodes/events/prompt.py` |
| **Add an attribute key** | `POST /sync/attributes` or edit `artifacts/attributes.json` (`valueType`: string, number or boolean) |
| **Add or update cameras** | `POST /sync/video_resources`. Nested folders also work if you write the JSON tree by hand |
| **Tune camera matching** | `FUZZY_THRESHOLD`, `STOPWORDS` (`nodes/video_resource/constants.py`), the partial-match ratio and coverage exponent `0.4` (`matching.py`) |
| **Add a time subclass** | (1) Add it to `INTENT_REGISTRY` with its required/optional params. (2) Describe it in `CLASSIFIER_PROMPT`. (3) Write `resolve_<subclass>()` in `resolver.py`. (4) Register it in `DISPATCHER`. (5) Optionally add logical checks in `validate.py` |
| **Switch LLM provider** | Point `LLM_BASE_URL` / `LLM_MODEL` at any OpenAI-compatible endpoint (Azure, vLLM, Ollama, LiteLLM proxy). It must support function calling for field extraction |
| **Add a new pipeline stage** | Create `nodes/<stage>/` following the module pattern, add `node_<stage>()` in `pipeline_nodes.py`, add a state key in `state.py`, and wire it in `build_graph()`. If it writes attributions, write a new sub-key of `source_attributions` |
