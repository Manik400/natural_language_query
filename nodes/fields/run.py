import asyncio
import json
from typing import List

from exceptions import FieldExtractionException
from llm.client import get_llm
from logger import get_logger, node_name_var

from .prompt import FIELD_EXTRACTION_PROMPT
from .schema_loader import build_tool_schema, load_schema
from .validate import ResponseValidator, validate_fields

logger = get_logger("fields.run")


class FieldExtractionFallbackHandler:
    """Handle failures in field extraction with partial recovery."""

    def __init__(self, schema_dir: str):
        self.schema_dir = schema_dir
        self.logger = get_logger("fields.fallback")
        self.validator = ResponseValidator(schema_dir)

    async def extract_for_event_with_fallback(
        self,
        event: dict,
    ) -> dict:
        """
        Extract fields for a single event with fallback.

        Args:
            event: Event dict with event_name and query_part

        Returns:
            EventFieldResult dict (always valid, may be empty)
        """
        event_name = event.get("event_name", "unknown")
        query_part = event.get("query_part", "")

        self.logger.info(f"Extracting fields for event: {event_name}")

        # Stage 1: Load schema
        try:
            event_schema = await load_schema(self.schema_dir, event_name)
            self.logger.debug(f"Loaded schema for {event_name}")
        except Exception as e:
            self.logger.warning(f"Failed to load schema for {event_name}: {e}")
            return {
                "event_name": event_name,
                "query_part": query_part,
                "relevant_fields": [],
                "error": {
                    "type": "schema_load_failed",
                    "recovered": True,
                },
            }

        # Stage 2: Build tool schema (sync — pure CPU, no await needed)
        try:
            tool_schema = build_tool_schema(event_name, event_schema)
            self.logger.debug(f"Built tool schema for {event_name}")
        except Exception as e:
            self.logger.warning(f"Failed to build tool schema for {event_name}: {e}")
            return {
                "event_name": event_name,
                "query_part": query_part,
                "relevant_fields": [],
                "error": {
                    "type": "tool_schema_failed",
                    "recovered": True,
                },
            }

        # Stage 3: Build prompt (sync — pure CPU, no await needed)
        try:
            prompt = FIELD_EXTRACTION_PROMPT.format(
                query=query_part,
                event=event_name,
                schema=json.dumps(event_schema, indent=2),
            )
            self.logger.debug(f"Built prompt for {event_name}")
        except Exception as e:
            self.logger.warning(f"Failed to build prompt for {event_name}: {e}")
            return {
                "event_name": event_name,
                "query_part": query_part,
                "relevant_fields": [],
                "error": {
                    "type": "prompt_build_failed",
                    "recovered": True,
                },
            }

        # Stage 4: LLM call with error handling
        try:
            llm_with_structure = get_llm().with_structured_output(
                tool_schema,
                method="function_calling",
            )

            self.logger.info(f"Calling LLM for {event_name}")
            response = await asyncio.wait_for(
                llm_with_structure.ainvoke(prompt),
                timeout=20,
            )

            if not response:
                self.logger.warning(f"Empty LLM response for {event_name}")
                return {
                    "event_name": event_name,
                    "query_part": query_part,
                    "relevant_fields": [],
                    "error": {
                        "type": "empty_llm_response",
                        "recovered": True,
                    },
                }

            raw_fields = response.get("relevant_fields", [])
            self.logger.debug(f"Got {len(raw_fields)} fields for {event_name}")

        except (TimeoutError, asyncio.TimeoutError):
            self.logger.warning(f"LLM timeout for {event_name}")
            return {
                "event_name": event_name,
                "query_part": query_part,
                "relevant_fields": [],
                "error": {
                    "type": "llm_timeout",
                    "recovered": True,
                },
            }
        except Exception as e:
            self.logger.warning(
                f"LLM call failed for {event_name}: {e}",
                exc_info=True,
            )
            return {
                "event_name": event_name,
                "query_part": query_part,
                "relevant_fields": [],
                "error": {
                    "type": "llm_failed",
                    "message": str(e),
                    "recovered": True,
                },
            }

        # Stage 5: Filter null fields (sync — pure CPU, no await needed)
        try:
            non_null_fields = [
                f
                for f in raw_fields
                if f.get("field") is not None
                and f.get("operator") is not None
                and f.get("value") is not None
                and f.get("query_snippet") is not None
            ]

            if not non_null_fields:
                self.logger.debug(f"No non-null fields for {event_name}")
                return {
                    "event_name": event_name,
                    "query_part": query_part,
                    "relevant_fields": [],
                    "error": {
                        "type": "no_non_null_fields",
                        "recovered": True,
                    },
                }

            self.logger.debug(f"Filtered to {len(non_null_fields)} non-null fields")

        except Exception as e:
            self.logger.warning(f"Error filtering null fields for {event_name}: {e}")
            return {
                "event_name": event_name,
                "query_part": query_part,
                "relevant_fields": [],
                "error": {
                    "type": "filter_failed",
                    "recovered": True,
                },
            }

        # Stage 6: Validate fields with error handling
        try:
            valid_fields = await validate_fields(
                event_name,
                non_null_fields,
                event_schema,
                self.validator,
            )

            self.logger.info(
                f"Field extraction complete for {event_name}",
                extra={"valid_fields": len(valid_fields)},
            )

            return {
                "event_name": event_name,
                "query_part": query_part,
                "relevant_fields": valid_fields,
            }

        except Exception as e:
            self.logger.warning(
                f"Validation failed for {event_name}: {e}",
                exc_info=True,
            )
            return {
                "event_name": event_name,
                "query_part": query_part,
                "relevant_fields": non_null_fields,
                "error": {
                    "type": "validation_failed",
                    "message": str(e),
                    "recovered": True,
                },
            }

    async def extract_fields_with_fallback(
        self,
        matched_events_response: dict,
    ) -> List[dict]:
        """
        Extract fields for multiple events with partial recovery.

        Args:
            matched_events_response: dict with matched_events list

        Returns:
            List of EventFieldResult dicts (partial results on failure)
        """
        node_name_var.set("field_extraction")
        matched_events = matched_events_response.get("matched_events", [])

        self.logger.info(f"Starting field extraction for {len(matched_events)} events")

        if not matched_events:
            self.logger.debug("No matched events to extract")
            return []

        raw_results = await asyncio.gather(
            *[self.extract_for_event_with_fallback(event) for event in matched_events],
            return_exceptions=True,
        )

        results = []
        errors = []

        for event, result in zip(matched_events, raw_results):
            if isinstance(result, Exception):
                self.logger.error(
                    f"Unexpected error in field extraction for "
                    f"{event.get('event_name')}: {result}",
                    exc_info=result,
                )
                errors.append(
                    {
                        "event_name": event.get("event_name"),
                        "error": str(result),
                    }
                )
                results.append(
                    {
                        "event_name": event.get("event_name"),
                        "query_part": event.get("query_part", ""),
                        "relevant_fields": [],
                        "error": {"type": "unknown", "recovered": True},
                    }
                )
            else:
                results.append(result)

        if errors:
            self.logger.warning(
                f"Field extraction had {len(errors)} errors (partial recovery)",
                extra={"errors": errors},
            )

        self.logger.info(
            "Field extraction complete",
            extra={"successful": len(results) - len(errors), "failed": len(errors)},
        )

        return results


async def extract_fields_with_error_handling(
    matched_events_response: dict,
    schema_dir: str,
) -> List[dict]:
    """
    Public API for field extraction with error handling.

    Args:
        matched_events_response: dict with matched_events list
        schema_dir: Path to schema directory

    Returns:
        List of EventFieldResult dicts (always returns list, may be partial)
    """
    try:
        handler = FieldExtractionFallbackHandler(schema_dir)
        return await handler.extract_fields_with_fallback(matched_events_response)
    except FieldExtractionException as e:
        logger.error(f"Field extraction exception: {e.message}")
        matched_events = matched_events_response.get("matched_events", [])
        return [
            {
                "event_name": event.get("event_name"),
                "query_part": event.get("query_part", ""),
                "relevant_fields": [],
                "error": e.to_dict(),
            }
            for event in matched_events
        ]
    except Exception as e:
        logger.error(f"Unexpected error in field extraction: {e}", exc_info=True)
        matched_events = matched_events_response.get("matched_events", [])
        return [
            {
                "event_name": event.get("event_name"),
                "query_part": event.get("query_part", ""),
                "relevant_fields": [],
                "error": {"type": "unknown", "message": str(e)},
            }
            for event in matched_events
        ]
