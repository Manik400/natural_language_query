from __future__ import annotations

import json
import logging

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from exceptions import LLMException
from llm.client import get_llm

from .constants import ConditionType
from .models import Attribute, ExtractionResult
from .prompt import build_extraction_prompt
from .schema_loader import load_attributes
from .validate import build_conditions, pre_validate

logger = logging.getLogger(__name__)


async def extract_attributes(query: str) -> ExtractionResult:
    """
    Extract and validate attribute conditions from a natural language query.
    Attributes are loaded from the configured path (ATTRIBUTES_JSON_PATH).

    Args:
        query: Natural language or structured query string.

    Returns:
        ExtractionResult containing conditionType and validated conditions.
    """
    attributes: list[Attribute] = load_attributes()
    attribute_map = {attr.key: attr for attr in attributes}

    logger.info(
        "Starting attribute extraction",
        extra={"query": query, "attribute_count": len(attributes)},
    )

    # ── Build prompt ───────────────────────────────────────────────
    prompt = build_extraction_prompt(query, attributes)
    logger.debug("Extraction prompt built", extra={"prompt": prompt})

    # ── Call LLM ───────────────────────────────────────────────────
    try:
        llm: ChatOpenAI = get_llm()
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        raw_response = response.content
        logger.debug("LLM response received", extra={"raw_response": raw_response})
    except Exception as e:
        logger.exception("LLM call failed during attribute extraction")
        raise LLMException(
            message="LLM call failed during attribute extraction",
            llm_error=str(e),
            context={"query": query},
        ) from e

    # ── Parse JSON ─────────────────────────────────────────────────
    try:
        parsed: dict = json.loads(raw_response)
    except json.JSONDecodeError as e:
        logger.error(
            "LLM returned invalid JSON",
            extra={"raw_response": raw_response, "error": str(e)},
        )
        raise ValueError(
            f"LLM returned invalid JSON: {e}\nRaw response:\n{raw_response}"
        ) from e

    # ── Resolve conditionType ──────────────────────────────────────
    condition_type_raw = parsed.get("conditionType") or None
    condition_type: ConditionType | None = None

    if condition_type_raw is not None:
        condition_type_raw = condition_type_raw.strip().upper()
        logger.debug(
            "Resolved conditionType", extra={"conditionType": condition_type_raw}
        )
        try:
            condition_type = ConditionType[condition_type_raw]
        except KeyError as e:
            logger.error(
                "LLM returned unknown conditionType",
                extra={"conditionType": condition_type_raw},
            )
            raise ValueError(
                f"LLM returned unknown conditionType '{condition_type_raw}'"
            ) from e
    else:
        logger.debug("conditionType is null — no matching attributes found")

    # ── Validate & build conditions ────────────────────────────────
    llm_items: list[dict] = parsed.get("conditions", [])
    logger.info("Running pre-validation", extra={"item_count": len(llm_items)})

    pre_validated = pre_validate(llm_items, attribute_map)
    logger.info(
        "Pre-validation complete",
        extra={
            "total": len(llm_items),
            "passed": len(pre_validated),
            "dropped": len(llm_items) - len(pre_validated),
        },
    )

    conditions = build_conditions(pre_validated, attribute_map)
    logger.info(
        "Condition building complete",
        extra={
            "pre_validated": len(pre_validated),
            "built": len(conditions),
            "dropped": len(pre_validated) - len(conditions),
        },
    )

    result = ExtractionResult(conditionType=condition_type, conditions=conditions)

    logger.info(
        "Attribute extraction complete",
        extra={
            "conditionType": (
                condition_type.name if condition_type is not None else None
            ),
            "condition_count": len(conditions),
        },
    )

    return result
