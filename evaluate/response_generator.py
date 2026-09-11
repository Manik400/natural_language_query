"""
Response Generator
==================
Reads queries.jsonl (each line: {"query": "..."}),
POSTs every query to a single FastAPI debug endpoint (specified via --endpoint),
and writes results to responses.jsonl (each line: {"query": "...", "response": {...}}).

Usage:
    python response_generator.py --endpoint events --input queries.jsonl --output responses.jsonl
"""

import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

import httpx

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL = "http://localhost:8081"
MAX_CONCURRENT = 2  # low default — fields endpoint is heavy
REQUEST_TIMEOUT = 60.0
RETRY_ATTEMPTS = 3
RETRY_DELAY = 2.0

VALID_ENDPOINTS = {"datetime", "events", "fields", "attributes"}

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("response_generator")

# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------


async def call_endpoint(
    client: httpx.AsyncClient,
    url: str,
    query: str,
) -> Any:
    """POST {"query": query} to url with retry logic. Returns parsed JSON (dict or list)."""
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            resp = await client.post(
                url, json={"query": query}, timeout=REQUEST_TIMEOUT
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Attempt %d/%d – HTTP %d: %s",
                attempt,
                RETRY_ATTEMPTS,
                exc.response.status_code,
                query[:80],
            )
            if attempt == RETRY_ATTEMPTS:
                return {
                    "status": "error",
                    "error": f"HTTP {exc.response.status_code}: {exc.response.text}",
                }
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            logger.warning(
                "Attempt %d/%d – %s: %s",
                attempt,
                RETRY_ATTEMPTS,
                type(exc).__name__,
                query[:80],
            )
            if attempt == RETRY_ATTEMPTS:
                return {"status": "error", "error": str(exc)}

        await asyncio.sleep(RETRY_DELAY * attempt)

    return {"status": "error", "error": "Max retries exceeded"}


# ---------------------------------------------------------------------------
# Core generator
# ---------------------------------------------------------------------------


async def generate_responses(
    input_path: Path,
    output_path: Path,
    endpoint: str,
    base_url: str,
    max_concurrent: int,
) -> None:
    url = f"{base_url}/debug/{endpoint}"

    # --- Read queries -------------------------------------------------------
    queries: list[str] = []
    with input_path.open(encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError as exc:
                logger.warning("Line %d – invalid JSON, skipping: %s", lineno, exc)
                continue
            if "query" not in obj:
                logger.warning("Line %d – missing 'query' key, skipping.", lineno)
                continue
            queries.append(obj["query"])

    if not queries:
        logger.error("No valid queries found in %s", input_path)
        sys.exit(1)

    logger.info("Loaded %d queries → endpoint: /debug/%s", len(queries), endpoint)

    # --- Dispatch concurrently ----------------------------------------------
    semaphore = asyncio.Semaphore(max_concurrent)
    results: list[dict[str, Any]] = [{}] * len(queries)

    async def process(idx: int, query: str) -> None:
        async with semaphore:
            logger.info("[%d/%d] %s", idx + 1, len(queries), query[:100])
            t0 = time.perf_counter()
            response = await call_endpoint(client, url, query)
            elapsed = time.perf_counter() - t0

            # response may be a dict or a list depending on the endpoint
            status = (
                response.get("status", "?") if isinstance(response, dict) else "success"
            )
            logger.info(
                "[%d/%d] status=%s  elapsed=%.3fs",
                idx + 1,
                len(queries),
                status,
                elapsed,
            )

        results[idx] = {"query": query, "response": response}

    async with httpx.AsyncClient() as client:
        await asyncio.gather(*[process(i, q) for i, q in enumerate(queries)])

    # --- Write output -------------------------------------------------------
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        for entry in results:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    logger.info("Done. Wrote %d responses to %s", len(results), output_path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Batch-generate responses from a FastAPI debug endpoint."
    )
    parser.add_argument(
        "--endpoint",
        "-e",
        required=True,
        choices=sorted(VALID_ENDPOINTS),
        help="Debug endpoint to call for every query.",
    )
    parser.add_argument(
        "--input",
        "-i",
        type=Path,
        required=True,
        help="Path to input queries.jsonl",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        required=True,
        help="Path to output responses.jsonl",
    )
    parser.add_argument(
        "--concurrency",
        "-c",
        type=int,
        default=MAX_CONCURRENT,
        help=f"Max parallel requests  (default: {MAX_CONCURRENT})",
    )
    parser.add_argument(
        "--base-url",
        default=BASE_URL,
        help=f"FastAPI server base URL  (default: {BASE_URL})",
    )

    args = parser.parse_args()

    asyncio.run(
        generate_responses(
            input_path=args.input,
            output_path=args.output,
            endpoint=args.endpoint,
            base_url=args.base_url.rstrip("/"),
            max_concurrent=args.concurrency,
        )
    )


if __name__ == "__main__":
    main()
