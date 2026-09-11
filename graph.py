from langgraph.graph import END, StateGraph

from pipeline_nodes import (
    node_attribute_extraction,
    node_event_selection,
    node_field_extraction,
    node_irrelevant,
    node_time_extraction,
    node_video_resolution,
)
from state import PipelineState
from transform import transform

_INTERNAL_KEYS = {"matched_events"}


# ─────────────────────────────────────────────
# Router
# ─────────────────────────────────────────────


def route_after_parallel_one(state: PipelineState) -> str:
    matched_events = state.get("matched_events", [])
    conditions = (state.get("attribute_conditions") or {}).get("conditions", [])

    has_attributes = any(c.get("value") not in (None, "", []) for c in conditions)

    if not matched_events and not has_attributes:
        return "irrelevant"
    return "relevant"


# ─────────────────────────────────────────────
# Build Graph
# ─────────────────────────────────────────────


def build_graph() -> StateGraph:
    graph = StateGraph(PipelineState)

    # ── Nodes ──────────────────────────────────────────────────────────
    graph.add_node("start", lambda state: state)
    graph.add_node("event_selection", node_event_selection)
    graph.add_node("attribute_extraction", node_attribute_extraction)
    graph.add_node("sync", lambda state: state)
    graph.add_node("fanout_2", lambda state: state)
    graph.add_node("time_extraction", node_time_extraction)
    graph.add_node("video_resolution", node_video_resolution)
    graph.add_node("field_extraction", node_field_extraction)
    graph.add_node("irrelevant", node_irrelevant)

    # ── Fan-out 1: start → event_selection + attribute_extraction ──────
    graph.set_entry_point("start")
    graph.add_edge("start", "event_selection")
    graph.add_edge("start", "attribute_extraction")

    # ── Fan-in 1: both converge to sync barrier ────────────────────────
    graph.add_edge("event_selection", "sync")
    graph.add_edge("attribute_extraction", "sync")

    # ── Route once both results are in state ───────────────────────────
    graph.add_conditional_edges(
        "sync",
        route_after_parallel_one,
        {
            "relevant": "fanout_2",
            "irrelevant": "irrelevant",
        },
    )

    # ── Fan-out 2: fanout_2 → time + video + fields in parallel ────────
    graph.add_edge("fanout_2", "time_extraction")
    graph.add_edge("fanout_2", "video_resolution")
    graph.add_edge("fanout_2", "field_extraction")

    # ── All parallel branches converge to END ──────────────────────────
    graph.add_edge("time_extraction", END)
    graph.add_edge("video_resolution", END)
    graph.add_edge("field_extraction", END)
    graph.add_edge("irrelevant", END)

    return graph.compile()


# ─────────────────────────────────────────────
# Run Pipeline
# ─────────────────────────────────────────────


async def run_pipeline(query: str, transform_output: bool = False) -> dict:
    """Run the full pipeline and return the final state.

    Args:
        query            : Natural language query string.
        transform_output : If True, returns API-ready payload via transform().
                           If False, returns raw NLP JSON (default).

    Returns:
        dict: Raw NLP output or API payload depending on transform_output flag.
    """
    raw = await build_graph().ainvoke({"query": query})

    query_json = {k: v for k, v in raw.items() if k not in _INTERNAL_KEYS}

    if not transform_output:
        return query_json

    if query_json.get("status") == "error":
        return query_json

    return transform(query_json)


pipeline = build_graph()
