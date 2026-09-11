# Natural Language Query Pipeline

> A Natural Language Query pipeline for extracting structured event, filter fields, time, and video resource information from free-text queries — built on **LangGraph**, **FastAPI**, and **Streamlit**.

## Overview

The Natural Language Query Pipeline accepts natural language queries and returns structured extractions across four dimensions:

| Dimension | Example Input | Example Output |
|-----------|---------------|----------------|
| **Events** | "crowd detected" | `crowd_detection` schema matched |
| **Time** | "between 5pm and 7pm yesterday" | `{start: "2026-03-05T17:00", end: "2026-03-05T19:00"}` |
| **Video Resources** | "camera 12" | `{groups: {"camera 12": ["camera_12_id"]}}` |
| **Fields** | "confidence > 90%" | `{field: "confidence", operator: ">", value: 90}` |
| **Attributes** | "aadhar 123456" | `{key: "aadhar", operator: "=", value: "123456"}` |

Each extraction includes **source attribution** — tracing which part of the original query led to each result.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Streamlit UI (app.py)                        │
│              Query Input → POST /pipeline → Display              │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                  FastAPI (api.py + graph.py)                     │
│                    LangGraph State Machine                        │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
                   ┌──────────────────┐
                   │  Event Selection │
                   │     (LLM)        │
                   └────────┬─────────┘
                            │
                            ▼
                   ┌──────────────────┐
                   │   Attribute      │
                   │   Extraction     │
                   │     (LLM)        │
                   └────────┬─────────┘
                            │
              ┌─────────────┴─────────────┐
           relevant?               irrelevant?
              │                         │
              ▼                         ▼
  ┌───────────────────────┐       [irrelevant]
  │  Time Extract (LLM)   │
  │  Video Resolve        │
  │  (Fuzzy, Parallel)    │
  └───────────┬───────────┘
              │
              ▼
     ┌─────────────────┐
     │ Field Extraction│
     │ (Per Event,     │
     │  Parallel)      │
     └────────┬────────┘
              │
              ▼
        Final State Dict
```

**Technology Stack:**

| Layer | Technology |
|-------|-----------|
| UI | Streamlit |
| API | FastAPI |
| Pipeline Orchestration | LangGraph |
| LLM | OpenAI (configurable) |

---

## Pipeline Workflow

The pipeline is modelled as a **LangGraph state machine**. Each node reads from and writes to a shared `PipelineState` dict. Routing between nodes is conditional.

```
[Entry] ──► event_selection
                │
                ▼
        attribute_extraction
                │
         ┌──────┴──────┐
      relevant?       irrelevant?
         │                │
         ▼                ▼
   time_and_video     [irrelevant]
         │
         ▼
   field_extraction
         │
         ▼
   [Final State]
```

---

### Node: Event Selection

**File:** `nodes/events/run.py`, invoked from `pipeline_nodes.py`

**What it does:**
1. Loads all event schemas from `artifacts/events_schema/`
2. Builds an LLM prompt listing available event types
3. Calls the LLM to identify which events the query refers to
4. Parses and validates the response against the known schema list

**Inputs (from state):** `query: str`

**Outputs (to state):**
```python
{
  "matched_events": [{"event_name": str, "query_part": str, ...}],
  "status": "success" | "irrelevant" | "parse_error"
}
```

**Routing:**
- `matched_events` not empty → proceed to `attribute_extraction`
- `matched_events` empty → proceed to `attribute_extraction` (routing decided after attributes)

---

### Node: Attribute Extraction

**File:** `nodes/attributes/run.py`, invoked from `pipeline_nodes.py`

**What it does:**
1. Calls the LLM to extract person/entity attribute conditions from the query
2. Identifies attribute keys, operators, and values (e.g. aadhar, bank number, plate number)
3. Determines the logical combiner (`AND` / `OR`) across multiple conditions
4. Returns structured attribute conditions for use in `AttributeFilters`

**Inputs (from state):** `query: str`

**Outputs (to state):**
```python
{
  "attribute_conditions": {
    "conditionType": "ALL" | "ANY" | None,
    "conditions": [
      {"key": str, "operator": str, "value": any, "valueType": str}
    ]
  }
}
```

**Routing (after attribute extraction):**
- `matched_events` not empty **or** any condition has a populated value → proceed to `time_and_video`
- Both empty → route to `irrelevant`

---

### Node: Time & Video Extraction

**File:** `pipeline_nodes.py` → `node_time_and_video()`

**Time Extraction:**
1. Builds a time-intent prompt from the query
2. Calls LLM — returns `timeIntent`, `timeIntentSubClass`, `raw_time_query`
3. Dispatches to a rule-based resolver that converts intent → ISO datetime range
4. Returns `{start: {date, time}, end: {date, time}}`

**Video Resource Resolution:**
1. Tokenizes the query
2. Attempts exact-match lookup against camera index
3. Falls back to fuzzy match (configurable threshold, default 75)
4. Groups matched cameras by query token
5. Returns `{groups: {token: [camera_ids]}}`

**Outputs (to state):**
```python
{
  "time": {"start": {...}, "end": {...}},
  "video_resources": {"groups": {token: [camera_ids]}}
}
```

---

### Node: Field Extraction

**File:** `nodes/fields/run.py`, invoked from `pipeline_nodes.py`

**What it does:**
For each event in `matched_events`, **in parallel**:
1. Loads the event's JSON schema from disk
2. Builds an OpenAI function-calling tool schema from the event schema
3. Calls the LLM with structured output (function calling)
4. Parses and validates operators (`=`, `!=`, `>`, `<`, `>=`, `<=`, `in`)
5. Filters out null/empty fields
6. Records the originating `query_snippet` for attribution

**Outputs (to state):**
```python
{
  "extracted_fields": [
    {
      "event_name": str,
      "relevant_fields": [
        {"field": str, "operator": str, "value": any, "query_snippet": str}
      ]
    }
  ],
  "source_attributions": {
    "fields": {
      event_name: {
        "query_part": str,
        "fields": [{"field": str, "operator": str, "value": any, "query_snippet": str}]
      }
    }
  }
}
```

---

### Node: Irrelevant Query

**File:** `pipeline_nodes.py` → `node_irrelevant()`

**What it does:**
- Sets `status = "irrelevant"`
- Sets a human-readable `message`
- Clears / zeroes out source attributions

**Outputs (to state):**
```python
{
  "status": "irrelevant",
  "message": "No relevant events found for this query.",
}
```

---

**Example `.env`:**
```env
OPENAI_API_KEY=sk-...
LLM_MODEL=gpt-4-turbo
SCHEMA_DIR=./artifacts/events_schema
VIDEO_JSON_PATH=./artifacts/video_resources.json
API_PORT=8081
```

---

## Running the Project

### Prerequisites

- Python 3.10+
- OpenAI API key

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Start the API

```bash
uvicorn api.main:app --host 0.0.0.0 --port 8081 
```

### Start the Streamlit UI

```bash
streamlit run app.py
```

---

"""
temp
## config
## widget
## events loop 
## events addition
"""