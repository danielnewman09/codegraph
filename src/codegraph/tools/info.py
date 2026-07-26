"""Graph info tools — list available tags and other metadata.

Each tool has a ``SCHEMA`` dict (JSON Schema for the LLM) and a
``handle(ctx, tool_input)`` function.
"""

import json

from codegraph.persistence.repository import GraphRepository


# ── graph_list_tags ────────────────────────────────────────────────────────

LIST_TAGS_SCHEMA = {
    "name": "graph_list_tags",
    "description": (
        "List all available tags in the codegraph, with node counts. "
        "Use this to discover what views exist before fetching one."
    ),
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


def handle_list_tags(ctx, tool_input: dict) -> str:
    from codegraph.constants import TAGS
    from codegraph.models.tags import CodeGraphNode

    counts: dict[str, int] = {}
    for tag in sorted(TAGS):
        results = GraphRepository().find_all_by_tag(tag)
        counts[tag] = len(results)

    return json.dumps({
        "available_tags": sorted(TAGS),
        "node_counts": counts,
    })


# ── Registration ───────────────────────────────────────────────────────────


def register_all(dispatcher) -> None:
    """Register all info tools on a dispatcher."""
    dispatcher.register(
        "graph_list_tags", LIST_TAGS_SCHEMA,
        lambda inp: handle_list_tags(dispatcher, inp),
    )
