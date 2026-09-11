import asyncio
import datetime as dt
from typing import Optional

from exceptions import TimeExtractionException
from llm.client import get_llm
from logger import get_logger, node_name_var

from .dispatcher import dispatch
from .parser import parse_llm_output
from .utility import build_anchors, build_classifier_prompt
from .validate import validate_llm_response

logger = get_logger("time.run")


class TimeExtractionFallbackHandler:
    """Handle failures in time extraction with graceful fallbacks."""

    def __init__(self):
        self.logger = get_logger("time.fallback")

    def get_default_fallback(self) -> dict:
        """Return default fallback when time extraction completely fails."""
        now = dt.datetime.now()
        today = f"{now.day:02d}-{now.month:02d}-{now.year:04d}"
        current_time = f"{now.hour:02d}:{now.minute:02d}:{now.second:02d}"

        return {
            "llm_response": None,
            "validation": {"success": False, "errors": ["Using fallback time range"]},
            "resolved": {
                "start": {
                    "date": today,
                    "time": "00:00:00",
                },
                "end": {
                    "date": today,
                    "time": current_time,
                },
            },
            "error": {
                "type": "time_extraction_failed",
                "fallback": "current_day",
                "recovered": True,
            },
        }

    async def time_extraction_with_fallback(
        self,
        user_query: str,
        current_datetime: Optional[dt.datetime] = None,
    ) -> dict:
        """
        Extract time with comprehensive error handling.

        Args:
            user_query: User query string
            current_datetime: Override current datetime for testing

        Returns:
            dict with resolved time range (always returns valid structure)
        """
        node_name_var.set("time_extraction")
        self.logger.info(f"Starting time extraction for query: {user_query[:100]}...")

        # Build anchors
        try:
            anchors = build_anchors(current_datetime)
            self.logger.debug("Built time anchors")
        except Exception as e:
            self.logger.error(f"Failed to build anchors: {e}", exc_info=True)
            return self.get_default_fallback()

        # Build prompt
        try:
            prompt = build_classifier_prompt(user_query=user_query)
            self.logger.debug("Built time extraction prompt")
        except Exception as e:
            self.logger.error(f"Failed to build prompt: {e}", exc_info=True)
            return self.get_default_fallback()

        # LLM call with error handling
        try:
            self.logger.info("Calling LLM for time extraction")
            llm_caller = get_llm()
            llm_raw_response = await asyncio.wait_for(
                llm_caller.ainvoke(prompt), timeout=20
            )

            if not llm_raw_response:
                self.logger.warning("LLM returned empty response")
                return self.get_default_fallback()

            self.logger.debug(f"LLM response: {str(llm_raw_response)[:200]}...")

        except asyncio.TimeoutError:
            self.logger.error("LLM call timed out")
            return self.get_default_fallback()
        except Exception as e:
            self.logger.error(f"LLM call failed: {e}", exc_info=True)
            return self.get_default_fallback()

        # Parse response with error handling
        try:
            parsed, parse_error = parse_llm_output(llm_raw_response)

            if parse_error or parsed is None:
                self.logger.warning(f"Parse error: {parse_error}")
                return self.get_default_fallback()

            llm_response_dict = parsed.model_dump()
            self.logger.debug(f"Parsed intent: {parsed.timeIntent}")

        except Exception as e:
            self.logger.error(f"Parse exception: {e}", exc_info=True)
            return self.get_default_fallback()

        # Validate response with error handling
        try:
            validation = validate_llm_response(llm_raw_response)
            validation_dict = {
                "success": validation.success,
                "errors": validation.errors,
            }

            if not validation.success:
                self.logger.warning(
                    f"Validation failed: {validation.errors}",
                    extra={"errors": validation.errors},
                )
                return {
                    "llm_response": llm_response_dict,
                    "validation": validation_dict,
                    "resolved": None,
                    "error": {
                        "type": "validation_failed",
                        "errors": validation.errors,
                        "fallback_used": True,
                    },
                }

            self.logger.debug("Validation successful")

        except Exception as e:
            self.logger.error(f"Validation exception: {e}", exc_info=True)
            return self.get_default_fallback()

        # Dispatch/resolve with error handling
        try:
            self.logger.info("Dispatching to resolver")
            dispatch_result = dispatch(validation, anchors)

            if not dispatch_result.get("success"):
                self.logger.warning(
                    "Dispatch returned unsuccessful",
                    extra={"result": dispatch_result},
                )
                return {
                    "llm_response": llm_response_dict,
                    "validation": validation_dict,
                    "resolved": None,
                    "error": {
                        "type": "dispatch_failed",
                        "reason": dispatch_result.get("error"),
                        "fallback_used": True,
                    },
                }

            resolved = dispatch_result.get("resolved")
            if resolved is None:
                self.logger.warning("Dispatch returned None resolved time")
                return self.get_default_fallback()

            resolved_dict = {
                "start": resolved.start,
                "end": resolved.end,
            }

            self.logger.info(
                "Time extraction successful",
                extra={
                    "start": str(resolved.start),
                    "end": str(resolved.end),
                },
            )

            return {
                "llm_response": llm_response_dict,
                "validation": validation_dict,
                "resolved": resolved_dict,
            }

        except Exception as e:
            self.logger.error(f"Dispatch exception: {e}", exc_info=True)
            return self.get_default_fallback()


async def time_extraction_with_error_handling(
    user_query: str,
    current_datetime: Optional[dt.datetime] = None,
) -> dict:
    """
    Public API for time extraction with error handling.

    Args:
        user_query: User query string
        current_datetime: Override current datetime for testing

    Returns:
        dict with guaranteed structure (always has resolved field)
    """
    handler = TimeExtractionFallbackHandler()

    try:
        return await handler.time_extraction_with_fallback(user_query, current_datetime)
    except TimeExtractionException as e:
        logger.error(f"Time extraction exception: {e.message}")
        return handler.get_default_fallback()
    except Exception as e:
        logger.error(f"Unexpected error in time extraction: {e}", exc_info=True)
        return handler.get_default_fallback()
