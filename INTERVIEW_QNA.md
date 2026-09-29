# Interview Q&A: Natural Language Query Pipeline

> Questions an interviewer is likely to ask about this project, with answers grounded in the actual code.
> Deeper references: [OVERVIEW.md](OVERVIEW.md) (how it works) and [STRUCTURE.md](STRUCTURE.md) (file by file).
> Live demo: https://naturallanguagequery-8gnfxtsnlumfgsantjrgqb.streamlit.app/

---

## 0. Numbers cheat sheet (memorise these)

| Fact | Value |
|---|---|
| Event types (JSON Schemas) | 15 |
| Cameras in the catalog | 97 |
| Time taxonomy | 6 intents, 18 subclasses |
| Event selection accuracy | micro **F1 97.5%** (P 98.0%, R 97.1%) on 717 queries |
| Field extraction accuracy | micro **F1 87.0%** (P 99.1%, R 77.5%) on 610 queries |
| Time intent accuracy | micro **F1 93.8%** on 308 queries |
| Offline rules mode (no LLM), event selection | F1 87.1% (P 94.6%, R 80.7%) on the same 717 queries |
| LLM calls per query | 3 + one per matched event (events, attributes, time, then fields per event) |
| Fuzzy match threshold | 75 (RapidFuzz `token_set_ratio`) |
| Dummy dataset | 2,000 synthetic events over 60 days |

---

## 1. The pitch

**Q1. Describe the project in 30 seconds.**
It turns a plain-English question from a CCTV operator into a structured search request for a video-analytics platform. For example, *"stolen red bike, plate HR5653RT78, last 7 days, from 192.168.9"* becomes the ANPR event with the filters Category = Stolen, VehicleColor = Red and plateNumber = …, an exact date range, and the matching camera IDs. It runs on a LangGraph pipeline with FastAPI and Streamlit, and every result carries **source attribution**: the piece of the query that produced it.

**Q2. Now the 2-minute version.**
The query is split into five dimensions: **events** (which analytics), **fields** (per-event filters), **attributes** (person/entity metadata such as an address), **time**, and **cameras**. The core design rule is *"the LLM classifies, the code computes."* The LLM only does what needs language understanding: picking event types, pulling out filter values, and classifying the *kind* of time expression. Everything that must be exact is deterministic Python: calendar arithmetic, fuzzy camera matching, and validating every LLM output against JSON Schemas and whitelists. Stages run in parallel through LangGraph. Every node has a fallback, so the pipeline never crashes. A human-in-the-loop evaluation setup (annotation tools plus metric scripts) measures it at 97.5% F1 on event selection. I also built a demo app with 2,000 synthetic events, a Data Explorer page, and an offline rule-based mode, deployed on Streamlit Community Cloud.

**Q3. What problem does it solve for the user?**
Surveillance platforms have powerful filters (per-analytics properties, time windows, camera trees) that are slow to use by hand. Operators think in sentences like "angry man near gate 2 yesterday evening". This removes the form-filling and outputs the exact API payload (`transform.py`) the existing search backend already understands. The backend doesn't need to change.

---

## 2. Architecture and orchestration

**Q4. Walk me through the pipeline.**
It's a LangGraph `StateGraph` (`graph.py`):
1. `start` fans out to **event_selection** and **attribute_extraction**, which run in parallel.
2. Both flow into a `sync` barrier, and the router `route_after_parallel_one` decides: no events **and** no attribute values means the query is **irrelevant**.
3. Otherwise `fanout_2` runs **time_extraction**, **video_resolution** and **field_extraction** in parallel, and all three go to END.
4. Optionally, `transform()` maps the raw output to the backend API payload.

**Q5. Why is attribute extraction in stage 1, not stage 2?**
The router needs it. A query like "anyone whose address is MG Road" has no event type but is still relevant. If attributes ran later, that query would be wrongly discarded as irrelevant.

**Q6. Why can't field extraction run in stage 1?**
It depends on `matched_events`. Fields are extracted per event, against that event's JSON Schema, so we must first know which events matched.

**Q7. Three nodes write `source_attributions` at the same time. How is that safe?**
`state.py` declares the key as `Annotated[SourceAttributions, merge_source_attributions]`. That's a **reducer**: LangGraph merges the concurrent updates (`{**a, **b}`) instead of rejecting them. Each node writes its own sub-key (`time`, `video`, `fields`), so nothing collides.

**Q8. Why LangGraph instead of plain `asyncio.gather`?**
- An explicit shared state and a typed contract (`PipelineState`)
- Declarative fan-out, fan-in and conditional routing
- Reducers for concurrent writes
- Adding or removing a node is a one-line edge change

For a two-stage DAG, plain asyncio would work, but the graph makes the control flow readable and extensible. For example, adding a new stage or a retry branch only touches `build_graph()`.

**Q9. What does the output look like?**
A dict with `status`, `time {start, end}`, `video_resources {groups, resolved_cameras}`, `extracted_fields [{event_name, relevant_fields}]`, `attribute_conditions {conditionType, conditions}`, `source_attributions`, and per-stage error keys. `matched_events` is internal and gets stripped. With `transform=true` you get the backend payload instead: epoch-ms times, camera UUIDs, integer operator codes, `propertyFilters` and `AttributeFilters`.

---

## 3. Event selection

**Q10. How are event types chosen?**
All 15 schemas are loaded concurrently (`aiofiles` + `asyncio.gather`), and only their `title` and `description` go into the prompt. The prompt adds domain definitions, **7 disambiguation rules** and a multi-intent rule, and asks for the exact query span behind each event. The reply is parsed with LangChain's `PydanticOutputParser`, checked against a **whitelist** of real titles (hallucinated names are dropped), and duplicate events are merged.

**Q11. Give an example of a disambiguation rule.**
The helmet rule: helmet + rider/bike means ANPR (the `noHelmet` field), helmet + worker/site means Safety Gear Violation, and with no context we prefer Safety Gear. Others: "wrong way" vs "reversing"; "overspeeding" (ANPR) vs "sudden acceleration" vs "crowd moving fast"; counting line crossings (Objects Entered) vs trespassing (Perimeter Violation). Motion Analysis is an explicit fallback.

**Q12. How do you handle LLM hallucinations here?**
Two layers. The prompt says "match from the provided list only", and a code whitelist removes any name not in the catalog. The whitelist is the real guarantee; the prompt instruction just reduces how often it has to act.

**Q13. What if the LLM is slow or down?**
A 30 s timeout per call and up to 3 attempts. After that, typed exceptions (`TimeoutException`, `LLMException`) are turned into a valid result (`matched_events: []`, `status: irrelevant`, plus an error object) instead of crashing the graph.

---

## 4. Attribute extraction

**Q14. What are attributes and how are they validated?**
Attributes are entity metadata keys declared in `artifacts/attributes.json` (for example `address`). The LLM returns `{conditionType, conditions: [{key, operator, raw_value, raw_slice}]}`. Validation has two stages:
- **`pre_validate`**: drops unknown keys, unknown operators, and items with no source slice.
- **`build_conditions`**: drops duplicate keys, coerces types ("42" → 42, "yes" → True, comma-separated values into lists for IN/BETWEEN), and checks each operator against the attribute's type using a compatibility matrix (`GREATERTHAN` only on numbers, `CONTAINS` only on strings, `BETWEEN` needs exactly `[min, max]` with min ≤ max).

**Q15. How do ALL/ANY work?**
`conditionType` is the logical combiner: ALL = AND (code 15), ANY = OR (code 14). The prompt picks ANY for an explicit "or" and defaults to ALL. If no condition survives validation, it must be `null`.

---

## 5. Field extraction

**Q16. How do you get reliable structured output for fields?**
For each matched event, a **function-calling tool schema** is built on the fly from the event's JSON Schema (`build_tool_schema`):
- `field` is an **enum** of that event's real property names,
- `operator` is an enum of the 13 allowed operators,
- `value` is a union type,
- each field's type, enum and description go into the tool description.

The model is called with `with_structured_output(tool_schema, method="function_calling")`, so it can't invent a field name.

**Q17. Why a flat item schema instead of `oneOf` per field?**
A per-field `oneOf` with `const` gives precise typing, but LLMs follow deeply nested unions poorly. The flat schema is reliably followed, and precise per-field typing is enforced **afterwards** by the validator. That's a deliberate trade-off: keep generation simple and put the strictness in code.

**Q18. Describe the validation.**
First, null field/operator/value/snippet entries are dropped. Then two stages:
1. **Stage 1**: `jsonschema` Draft 2020-12 checks each item against the tool item schema (enums, types, required keys).
2. **Stage 2** (`ResponseValidator`): the field must exist in the event schema; no duplicate fields; the **operator must fit the field's type** (`GreaterThan` only on numbers, `Contains` only on strings, `Between` needs `[min, max]`); and the value is validated against the event schema itself, so enums (`VehicleColor ∈ {Red, Green, …}`) and minimums (`speed ≥ 0`) are enforced.

**Q19. How do you stop one bad event from breaking the others?**
Events are processed with `asyncio.gather(..., return_exceptions=True)`. Every per-event failure (missing schema, timeout, empty response, validation error) returns that event with `relevant_fields: []` and an error type, and all other events still succeed.

**Q20. Fields have 99% precision but only 77.5% recall. Why?**
The model leaves fields out far more often than it invents them. Invented or invalid values are also filtered by validation, which pushes precision up. There's also a context issue: the field LLM only sees `query_part` (the span for that event), not the full query, so details mentioned elsewhere in the sentence are missed. To raise recall, I'd pass the full query with the span highlighted and add few-shot examples for the weak events.

---

## 6. Time extraction (the most interesting part)

**Q21. Why not ask the LLM to return the dates directly?**
LLMs are unreliable at date arithmetic (month lengths, leap years, "last week" boundaries), and their answers can't be checked. So the LLM **only classifies**. It returns an intent, a subclass and *symbolic* parameters (`n_units: "7"`, `unit: "day"`). The prompt doesn't even include today's date. Deterministic resolvers compute the actual range from the server clock. Every date is exact, reproducible and unit-testable.

**Q22. What's the taxonomy?**
6 intents with 18 subclasses:
- **none**
- **invalid** (incomplete, ambiguous, conflicting, malformed date)
- **relative** (current_period, rolling_window, completed_period, future_window, offset_from_anchor_date)
- **duration** (full_year, single_month, month_to_month_range)
- **instant** (today_or_yesterday, weekday_reference, specific_date)
- **absolute** (explicit_date_range, date_to_now_range)

**Q23. "Last week" vs "past week" vs "last 7 days": how do you tell them apart?**
With a rule table in the prompt:
- "past" + unit → **rolling window** (a sliding window that ends now)
- "last" + number → **rolling window**
- "last" + bare unit → **completed period** ("last week" = the previous Monday to Sunday)
- "previous" → always a completed period

The prompt ends with a self-check step that re-verifies exactly this rule before the model answers.

**Q24. How is the LLM's time answer validated?**
Three layers:
1. **Envelope**: Pydantic checks that all 4 keys exist.
2. **Registry**: `INTENT_REGISTRY` confirms the intent/subclass pair is real, every required param is present, and there are no unexpected params.
3. **Logical**: dates are `DD-MM-YYYY`, times are `HHMMSS` within range, `n_units` > 0, enum values are allowed, end is after start, and month ranges are in order.

**Q25. How does the resolver work?**
A two-level dispatch table, `DISPATCHER[intent][subclass]`, maps each pair to one pure function. That's the strategy pattern: adding a subclass means a registry entry, a prompt line, a resolver and one dispatch entry. Month arithmetic clamps the day (31 Jan + 1 month = 28/29 Feb). The end-time rule: if the range ends today, it ends *now*; if it ends on a past day, it ends at 23:59:59.

**Q26. What happens when time extraction fails?**
It falls back to today 00:00:00 → now, marked `recovered: true`. That's a safe, narrow default that never returns an unbounded search.

---

## 7. Camera (video resource) matching

**Q27. Why is camera matching not done by the LLM?**
The camera list can be huge and changes all the time. The results must be exact IDs, and the step should be fast, free and deterministic. A classic string-matching algorithm fits better than an LLM here.

**Q28. Walk me through the algorithm.**
1. **Split into clauses** on "," and "and"; each clause is resolved separately and the results are unioned.
2. **IP fast path**: a regex finds full IPs (exact match, confidence 100) and 3-octet prefixes like `192.168.9` (the whole subnet, confidence 75).
3. **Remove about 200 stopwords.** The list is curated so dropping a word can never change the intended camera ("cam" is kept on purpose because `CAM01` matters).
4. **Generate n-grams of every length, longest first**, each with its word positions. Compound tokens like `SECL_KSM_SARANGI` are also tried whole, and letter-digit runs are split (`cam01` → `cam 01`).
5. **Score each token against each camera/folder name** as a cascade:
   - exact → 100
   - partial (one is a substring of the other and at least 50% of its length) → at least 80
   - fuzzy → RapidFuzz `token_set_ratio`, accepted at **≥ 75**
6. **Greedy non-overlapping selection**: the most specific match (fewest cameras) goes first, and matches whose words are already used are skipped.
7. **AND-intersect** the selected camera sets, **skipping a constraint if it would empty the result**.

**Q29. What are the "digit guard" and "coverage penalty"?**
- **Digit guard**: every number in the token must appear in the candidate. Otherwise "cam 02" would fuzzy-match "cam 03" with a high score.
- **Coverage penalty**: `token_set_ratio` gives 100 whenever one word set is a subset of the other, so "pit" would match every long name containing "pit". If the token's words are a strict subset, the score becomes `base × coverage^0.4`.

The side effect: a single distinctive word like "sarangi" scores about 64 against `SECL_KSM_SARANGI` and gets rejected. That's a known limitation.

**Q30. How does tie-breaking work?**
A lexicographic tuple: match type (exact > partial > fuzzy), then higher confidence, then folder match over camera-name match (a folder is more intentional), then shallower folder (broader coverage), then smaller subtree.

**Q31. How would it scale to 50,000 cameras?**
Today it's O(n-grams × candidates) per clause, and all-length n-grams are O(n²) in clause length. Four changes:
- build an **inverted index** from normalized words to candidates, and only score candidates that share a word,
- cap n-gram length at the longest camera name,
- cache the flattened indexes (they're currently rebuilt on every request),
- optionally precompute character n-gram or MinHash signatures.

---

## 8. Transform and integration

**Q32. What does `transform.py` produce?**
The backend payload:
- `startTime`/`endTime` as UTC epoch milliseconds (the input is read as IST),
- camera names mapped to UUIDs in `resources.Video_Sources`,
- `analytics` keys (e.g. "ANPR"),
- `propertyFilters` per analytics as `{condition: "AND", rules: [{field, operator: <int>, value, type: <ruleType>}]}`,
- `AttributeFilters` as `{field: "attributes", operator: 14/15, type: 21, value: "<JSON string>"}`,
- fixed paging.

An irrelevant query returns a safe default payload (today 00:00 → now, no filters).

**Q33. How do new event types get in?**
`POST /sync/events_schema`. The platform sends each event name with its property names and types. We SHA-256 hash (event name + sorted property names) to detect changes, and only changed events are processed, in a thread pool. New events and new properties get **LLM-written descriptions**. Those matter because event selection only sees the title and description. Each `ruleType` maps to a JSON Schema type and format.

---

## 9. Reliability, logging, errors

**Q34. How do you make an LLM pipeline robust?**
Every node is wrapped in a `*FallbackHandler`, and a node **never raises into the graph**. Each returns a well-formed result plus an error object with `recovered: true`. Timeouts use `asyncio.wait_for`; event selection retries. There's a typed exception hierarchy (`NLIPipelineException` → `LLMException`, `TimeoutException`, …) with error codes and `to_dict()` for API responses.

**Q35. How do you trace one request through parallel nodes?**
Structured JSON logs (`logger.py`) go to the console and a rotating file (10 MB × 5). A `request_id` and `node_name` travel in `contextvars`, so every log line from one request shares an ID even across async tasks.

**Q36. Why temperature 0?**
To make results reproducible for evaluation and debugging. Classification and extraction don't benefit from creativity.

---

## 10. Evaluation

**Q37. How did you measure quality?**
A human-in-the-loop loop:
1. `response_generator.py` batch-calls the `/debug/<stage>` endpoints for a queries file.
2. Streamlit **annotation tools** (`annotate/`) let a person correct each output, with dropdowns driven by the schemas and the time registry, and saves are atomic.
3. Metric scripts compare predictions with the corrected ground truth.

The `--reviewed_only` flag scores only examples a human confirmed.

**Q38. Which metrics, and why multiset counting?**
Precision, recall and F1 per label, plus Jaccard "accuracy" = TP / (TP + FP + FN), reported as both **macro** and **micro** averages. Counting is **multiset**: per query and label, TP = min(predicted count, gold count). A query can legitimately contain the same label more than once, and multiset counting never gives more TP credit than the ground truth contains.

**Q39. Macro vs micro: when does each matter?**
Micro pools all decisions, so frequent classes dominate; it reflects overall user experience. Macro averages per class, so rare classes count equally; it exposes weak spots. Our events: micro F1 97.5% vs macro F1 96.4%. The gap comes from rarer classes like Illegal Vehicle (60.9% precision, over-selected).

**Q40. What were the weakest areas?**
- **Events**: Illegal Vehicle precision 60.9%; Highway ATCC precision 87.5%.
- **Fields**: Vehicle Accelerated and Illegal Vehicle at 0%. The first is a real bug: a schema filename typo, so the schema never loads.
- **Time**: the `invalid` intent, where `ambiguous_reference` recall is only 37.5%. The model tends to "resolve" ambiguous phrases instead of flagging them.

**Q41. For fields you can score name-only or strictly. Why both?**
`--match_operator` and `--match_value` separate *"did we find the right field?"* from *"did we get the exact filter right?"*. Name-only shows recall of intent; strict matching shows end-to-end correctness. Reporting both tells you whether to fix field detection or value normalization.

---

## 11. Demo app, dummy data, offline mode, deployment

**Q42. Tell me about the demo you built.**
A two-page Streamlit app:
- **Search**: the original query UI, now also running the parsed filters against a dataset and listing the matching events with the applied filters shown as chips.
- **Data Explorer**: filters, stat tiles, an events-per-day chart, top-N bar charts (Altair), a selectable table with the full record, and CSV export.

It's deployed on Streamlit Community Cloud from GitHub, and every push to `main` redeploys it.

**Q43. How did you generate the dummy data?**
A seeded generator (`scripts/generate_dummy_data.py`) creates 2,000 events across the 15 analytics:
- realistic values: Indian number plates, speeds that stay consistent with `speedViolated`, crowd counts above their thresholds, safety violations that always miss at least one item,
- cameras chosen by event family (traffic events on gate/road cameras, PPE events on site cameras),
- **every event validated against its JSON Schema**, so the demo can't drift from the real contract,
- a few hand-planted events so the default demo query has real hits.

At load time, dates are shifted by whole days so the data always ends today.

**Q44. What is "offline rules mode", and why?**
The demo had to work without a paid LLM key. A keyword/regex engine (`demo/rules_*.py`) stands in for the LLM calls but emits **the exact same JSON**. It then reuses the project's real validators, time resolvers and camera matcher, so only the LLM parts are swapped. It scores 87.1% F1 on event selection against 97.5% for the LLM, which is good enough for a demo and a useful baseline showing what the LLM adds. When `OPENAI_API_KEY` and `LLM_MODEL` are present in secrets, the app switches to AI mode automatically.

**Q45. How does the search over the dummy data work?**
It mirrors the backend's semantics: time window AND cameras AND (any matched event type whose field rules all pass) AND attribute conditions (ALL/ANY). One `compare()` function supports both operator vocabularies (`GreaterThan`/`GREATERTHAN`, `In`, `Between`, `Like` with `%`, and so on), compares case-insensitively, and coerces booleans and numbers.

**Q46. Any deployment gotchas?**
Two real ones:
1. **Settings were read once at import time**, so secrets saved in Streamlit Cloud were ignored until a reboot. The fix reads settings fresh for each check and each LLM call, and re-exports secrets on every rerun.
2. After a push, Streamlit Cloud reloaded the page script but **kept a stale cached module**, which caused an `ImportError` for a newly added function. A reboot fixed it.

Also: cloud servers run on UTC while the resolvers assume IST, so the app sets `TZ=Asia/Kolkata` at startup.

**Q47. Any provider-portability concerns?**
The LLM client is LangChain's `ChatOpenAI` with a configurable `base_url`, so any OpenAI-compatible provider works (OpenAI, Azure, Gemini's compatibility endpoint, Groq, a local vLLM or Ollama server). The one hard requirement is **function-calling support** for field extraction, and each provider's schema support differs, so that's the first thing to test when switching.

---

## 12. Performance and cost

**Q48. What's the latency profile?**
Latency ≈ max(event call, attribute call) + max(time call, video matching, field calls). Field calls run in parallel per event, so a 3-event query costs about one field call in wall-clock time, not three. Camera matching and all the validation are milliseconds. The LLM calls dominate.

**Q49. How would you cut cost and latency?**
- Cache schemas, the camera index and the compiled graph. They're currently rebuilt per request (`run_pipeline` calls `build_graph()` each time, and the video handler reloads its JSON).
- Merge event and attribute extraction into one call, trading prompt complexity for one fewer round trip.
- Use a smaller or faster model for time classification, which is a closed-set task.
- Cache repeated queries by normalized text.
- Short-circuit time extraction when a cheap regex finds no temporal words at all.

---

## 13. Security

**Q50. What about prompt injection?**
The blast radius is small by design. The LLM has **no tools with side effects**; it only produces data. Every output is constrained: event names by a whitelist, field names by an enum, values by JSON Schema, dates by resolvers, camera IDs by a lookup table. An injected instruction can at worst produce a wrong filter within the allowed vocabulary, never an unknown field, a new endpoint call, or arbitrary text in the payload.

**Q51. How are secrets handled?**
API keys come from environment variables or Streamlit secrets through `pydantic-settings`, and never from the repo. `.env` and `.streamlit/secrets.toml` are git-ignored. That matters because the repo is public. User text rendered as HTML in Streamlit is escaped, because the UI uses `unsafe_allow_html`.

---

## 14. Limitations and what I'd improve

**Q52. What bugs or weaknesses did you find?**
- A schema filename typo (`vehicle_accelated.json`) means Vehicle Accelerated fields never extract, which explains its 0% field score.
- `transform.get_rule_type` looks for the wrong filename, so every rule gets `type: 1`.
- `completed_period` validates `n_units` but the resolver ignores it: "previous 3 months" resolves to 1 month.
- Field extraction sees only `query_part`, which loses context.
- Timezone: the server clock vs the IST assumption in `transform`.
- Two operator-numbering schemes (fields `In` = 8, attributes `IN` = 9).
- An "irrelevant" status from a failed event call can hide real attribute results.
- The FastAPI exception handler returns a `dict` instead of a `Response`.
- Single-word camera queries can fall below the fuzzy threshold.

**Q53. What would you do next?**
1. Fix the bugs above and add **unit tests**. The resolvers and matcher are pure functions and easy to test, and there are none yet.
2. Build an evaluation set for camera matching, which currently has no metrics.
3. Improve field recall with full-query context and few-shot examples.
4. Add cheap confidence scores (for example, agreement between the rules engine and the LLM) to flag uncertain parses for the user.
5. Feed annotator corrections back as few-shot examples.
6. Add caching and an inverted index for scale.

**Q54. How would you add support for Hindi or Hinglish queries?**
The LLM stages mostly work already, since modern models handle Hinglish. The deterministic parts need work: extend the stopwords, add number words ("saat din" = 7 days) and relative-time words ("kal" is ambiguous between yesterday and tomorrow, which should be classified as `ambiguous_reference`). Then build a separate Hinglish evaluation set before claiming support.

---

## 15. Rapid-fire

| Question | Short answer |
|---|---|
| What is a LangGraph reducer? | A function that merges concurrent writes to one state key |
| Why Pydantic parsers? | They strip markdown fences, parse JSON and validate types in one step, returning `(parsed, error)` instead of crashing |
| What if the LLM wraps JSON in ```json fences? | `PydanticOutputParser` strips them |
| `token_set_ratio` in one line? | A fuzzy score that compares the shared words plus each side's leftover words, ignoring word order |
| Precision vs recall? | Of what we predicted, how much was right, vs of what was right, how much we found |
| Jaccard accuracy? | TP / (TP + FP + FN): overlap over union |
| How do you add a new event type? | Push it through `/sync/events_schema` (or drop in a schema file with `$id`, title, description, properties); add a disambiguation rule if it overlaps an existing event |
| How do you add a new time phrase type? | Registry entry, prompt description, resolver function, dispatch entry, optional logical checks |
| Why does the camera matcher skip an intersection that empties the set? | Over-constraining returns nothing, which is worse than a slightly broader match |
| Why are IP prefixes confidence 75 but full IPs 100? | A prefix selects a whole subnet, which is intentional but less specific |
| What happens for "show me the weather"? | No events and no attributes, so the router marks it `irrelevant` and the pipeline returns early |
| Biggest design lesson? | Let the LLM do language and let code do anything that must be exact, then validate the boundary between them |
