FIELD_EXTRACTION_PROMPT = """
You are extracting filter fields for an analytics event.

STRICT RULES:
- Use ONLY fields present in the event schema
- Use ONLY the allowed operators listed below
- Infer operator and value ONLY if clearly mentioned or implied
- If a field is mentioned but its value is not specified, set value to null
- Do NOT invent fields, operators, or values
- For each extracted field, include the exact snippet from the query that led to selecting that field and value

FIELD UNIQUENESS RULE (CRITICAL):
1. Each field MUST appear AT MOST ONCE in relevant_fields
2. If the same field is implied multiple times, merge into a SINGLE entry
3. Prefer the MOST SPECIFIC operator: Equal > In > Between > Contains > Like
4. If values conflict, choose the most explicit value from the query

ALLOWED OPERATORS:
Equal, NotEqual, GreaterThan, SmallerThan, GreaterThanOrEqual, SmallerThanOrEqual,
Contains, NotContains, In, NotIn, Between, Like, NotLike

User Query:
{query}

Event: {event}

Event Schema:
{schema}
"""
