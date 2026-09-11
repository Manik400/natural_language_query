from __future__ import annotations

import asyncio

from exceptions import EventSelectionException, LLMException, TimeoutException
from llm.client import get_llm
from logger import get_logger, node_name_var

from .parser import parse_llm_output
from .prompt_builder import build_prompt
from .schema_loader import load_event_schemas
from .validate import validate_events

logger = get_logger("events.run")


class EventSelectionFallbackHandler:
    """Handle failures in event selection with graceful fallbacks."""

    def __init__(self, schema_dir: str):
        self.schema_dir = schema_dir
        self.logger = get_logger("events.fallback")

    def get_default_fallback(self) -> dict:
        """Return default fallback for complete event selection failure."""
        return {
            "status": "irrelevant",
            "message": "Unable to process query. Using fallback.",
            "matched_events": [],
            "error": {
                "type": "event_selection_failed",
                "recovered": True,
            },
        }

    def _merge_duplicate_events(self, matched_events: list) -> list:
        """
        Postprocess matched events by merging duplicates with the same event_name,
        combining their query_parts into a single entry.
        """
        merged: dict[str, list[str]] = {}

        for event in matched_events:
            name = event.get("event_name", "unknown")
            part = event.get("query_part", "").strip()
            if name not in merged:
                merged[name] = []
            if part:
                merged[name].append(part)

        result = [
            {"event_name": name, "query_part": ". ".join(parts)}
            for name, parts in merged.items()
        ]

        if len(result) < len(matched_events):
            self.logger.info(
                f"Merged {len(matched_events)} matched events into {len(result)} unique events"
            )

        return result

    async def select_events_with_fallback(
        self,
        query: str,
        max_retries: int = 2,
    ) -> dict:
        """
        Select events with comprehensive error handling.

        Args:
            query: User query string
            max_retries: Number of retries on transient failures

        Returns:
            dict with status and matched_events (always returns valid dict)
        """
        node_name_var.set("event_selection")
        self.logger.info(
            f"Starting event selection for query: {query[:100]}...",
            extra={"query_length": len(query)},
        )

        # Stage 1: Schema Loading
        try:
            schemas = await load_event_schemas(self.schema_dir)
            self.logger.debug(f"Loaded {len(schemas)} event schemas")
        except Exception as e:
            self.logger.error(
                f"Failed to load schemas: {e}",
                exc_info=True,
            )
            raise EventSelectionException(
                message="Could not load event schemas",
                context={"error": str(e)},
            )

        # Stage 2: Prompt Building (sync — pure CPU, no await needed)
        try:
            prompt, valid_event_names = build_prompt(
                query=query,
                schemas=schemas,
            )
            self.logger.debug(
                f"Built prompt with {len(valid_event_names)} valid events"
            )
        except Exception as e:
            self.logger.error(
                f"Failed to build prompt: {e}",
                exc_info=True,
            )
            raise EventSelectionException(
                message="Could not build prompt for event selection",
                context={"error": str(e)},
            )

        # Stage 3: LLM Call with Retry Logic
        llm_raw_response = None
        for attempt in range(max_retries + 1):
            try:
                self.logger.info(f"LLM call attempt {attempt + 1}/{max_retries + 1}")
                llm = get_llm()
                llm_raw_response = await asyncio.wait_for(
                    llm.ainvoke(prompt),
                    timeout=30,
                )

                if not llm_raw_response:
                    raise LLMException("LLM returned empty response")

                self.logger.debug(
                    f"LLM response: {str(llm_raw_response)[:200]}...",
                    extra={"response_length": len(str(llm_raw_response))},
                )
                break  # Success

            except (TimeoutError, asyncio.TimeoutError) as e:
                self.logger.warning(f"LLM timeout on attempt {attempt + 1}: {e}")
                if attempt == max_retries:
                    raise TimeoutException(
                        message="LLM call timed out",
                        node_name="event_selection",
                        timeout_seconds=30,
                        context={"attempts": attempt + 1},
                    )
                continue

            except Exception as e:
                self.logger.warning(f"LLM call failed on attempt {attempt + 1}: {e}")
                if attempt == max_retries:
                    raise LLMException(
                        message="Failed to call LLM for event selection",
                        llm_error=str(e),
                        context={"attempts": attempt + 1},
                    )
                continue

        if not llm_raw_response:
            raise LLMException("No LLM response after retries")

        # Stage 4: Parse Response (sync — pure CPU, no await needed)
        try:
            parsed, parse_error = parse_llm_output(llm_raw_response)

            if parse_error:
                self.logger.warning(f"Parse error: {parse_error}")
                return {
                    "status": "irrelevant",
                    "message": f"Could not parse LLM response: {parse_error}",
                    "matched_events": [],
                    "error": {
                        "type": "parse_error",
                        "recovered": True,
                    },
                }

            self.logger.debug(
                f"Parsed events: {[e.event_name for e in parsed.matched_events]}"
            )

        except Exception as e:
            self.logger.error(
                f"Exception during parsing: {e}",
                exc_info=True,
            )
            return {
                "status": "irrelevant",
                "message": "Failed to parse event selection response",
                "matched_events": [],
                "error": {
                    "type": "parse_exception",
                    "recovered": True,
                },
            }

        # Stage 5: Validate Events (sync — pure CPU, no await needed)
        try:
            valid_events, invalid_events = validate_events(
                parsed.matched_events,
                valid_event_names,
            )

            if invalid_events:
                self.logger.warning(
                    f"Hallucinated events removed: {[e.event_name for e in invalid_events]}"
                )

            self.logger.info(
                f"Event selection complete: {len(valid_events)} valid events"
            )

            matched_events = self._merge_duplicate_events(
                [
                    {"event_name": e.event_name, "query_part": e.query_part}
                    for e in valid_events
                ]
            )

            return {
                "status": "success",
                "matched_events": matched_events,
            }

        except Exception as e:
            self.logger.error(
                f"Exception during validation: {e}",
                exc_info=True,
            )
            if len(valid_events) > 0:
                self.logger.warning("Returning partially validated events")

                matched_events = self._merge_duplicate_events(
                    [
                        {"event_name": e.event_name, "query_part": e.query_part}
                        for e in valid_events
                    ]
                )

                return {
                    "status": "success",
                    "matched_events": matched_events,
                    "error": {
                        "type": "validation_partial",
                        "recovered": True,
                    },
                }

            return {
                "status": "irrelevant",
                "message": "No valid events could be selected",
                "matched_events": [],
                "error": {
                    "type": "validation_failed",
                    "recovered": True,
                },
            }


async def select_events_with_error_handling(
    query: str,
    schema_dir: str,
) -> dict:
    """
    Public API for event selection with error handling.

    Args:
        query: User query string
        schema_dir: Path to event schemas directory

    Returns:
        dict with guaranteed structure (status, matched_events, optional error)
    """
    handler = EventSelectionFallbackHandler(schema_dir)

    try:
        return await handler.select_events_with_fallback(query)
    except EventSelectionException as e:
        logger.error(f"Event selection exception: {e.message}")
        return {
            "status": "irrelevant",
            "message": e.message,
            "matched_events": [],
            "error": e.to_dict(),
        }
    except LLMException as e:
        logger.error(f"LLM exception: {e.message}")
        return {
            "status": "irrelevant",
            "message": "LLM service unavailable",
            "matched_events": [],
            "error": e.to_dict(),
        }
    except TimeoutException as e:
        logger.error(f"Timeout exception: {e.message}")
        return {
            "status": "irrelevant",
            "message": "Event selection timed out",
            "matched_events": [],
            "error": e.to_dict(),
        }
    except Exception as e:
        logger.error(f"Unexpected error in event selection: {e}", exc_info=True)
        return {
            "status": "error",
            "message": "Unexpected error occurred",
            "matched_events": [],
            "error": {
                "type": "unknown",
                "message": str(e),
            },
        }
