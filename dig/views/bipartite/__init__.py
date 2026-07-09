"""The bipartite view of a recorded DIG --
every activation and event as a node-and-edge trace (`view.py`), plus its
analyses (`lineage.py`: ancestry and root coverage; `detail.py`: what one
trace node opens up to)."""

from .detail import activation_detail_fields, activation_detail_text
from .lineage import (
    any_coverage_complete,
    lineage_covers_root_events,
    lineage_event_ids_from,
    root_events,
    submit_activations,
    uncovered_root_events,
    untouched_root_events,
)
from .view import (
    DIGBipartiteEdge,
    DIGBipartiteGraphData,
    DIGBipartiteNode,
    activation_event_graph,
    edges,
)

__all__ = [
    "DIGBipartiteNode",
    "DIGBipartiteEdge",
    "DIGBipartiteGraphData",
    "edges",
    "activation_event_graph",
    "root_events",
    "submit_activations",
    "lineage_event_ids_from",
    "lineage_covers_root_events",
    "uncovered_root_events",
    "untouched_root_events",
    "any_coverage_complete",
    "activation_detail_fields",
    "activation_detail_text",
]
