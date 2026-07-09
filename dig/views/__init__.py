"""Ways of looking at one recorded DIG.

The graph (`dig`) is the representation: it records, delivers,
and observes. A VIEW is a way of looking at that same underlying record.
Each view is a subpackage: `view.py` holds the way of looking (its
structure/materialization), and sibling topical modules hold its ANALYSES
-- the questions and computations that way of looking makes easy (query a
property, check coverage, compute a statistic). There is deliberately no
inner `query/` or `utility/` folder: analyses sit beside `view.py`,
promoted into a subfolder only if a view accumulates many.

  bipartite/  every activation and event as a
              node-and-edge trace (`view.py`), with lineage/root-coverage
              analysis (`lineage.py`) and node-detail views (`detail.py`)
  agent/      one node per agent, directed edges
              bundling the event flows between each pair, grouped by
              reaction kind (`view.py`)

Views never own state and the core layers never import them; viz and heal
consume views. To add a view: a new subpackage with `view.py` (+ analyses),
re-exported here.
"""

from .agent.view import (
    ROOT_AGENT,
    AgentGraph,
    AgentGraphEdge,
    AgentGraphLink,
    agent_edge_key,
    agent_node_key,
    build_agent_graph,
    producer_agent,
)
from .bipartite.detail import (
    activation_detail_fields,
    activation_detail_text,
)
from .bipartite.lineage import (
    any_coverage_complete,
    lineage_covers_root_events,
    lineage_event_ids_from,
    root_events,
    submit_activations,
    uncovered_root_events,
    untouched_root_events,
)
from .bipartite.view import (
    DIGBipartiteEdge,
    DIGBipartiteGraphData,
    DIGBipartiteNode,
    activation_event_graph,
    edges,
)

__all__ = [
    # the bipartite view
    "DIGBipartiteNode",
    "DIGBipartiteEdge",
    "DIGBipartiteGraphData",
    "edges",
    "activation_event_graph",
    # its lineage analysis
    "root_events",
    "submit_activations",
    "lineage_event_ids_from",
    "lineage_covers_root_events",
    "uncovered_root_events",
    "untouched_root_events",
    "any_coverage_complete",
    # its node-detail analysis
    "activation_detail_fields",
    "activation_detail_text",
    # the agent view
    "ROOT_AGENT",
    "AgentGraph",
    "AgentGraphEdge",
    "AgentGraphLink",
    "agent_edge_key",
    "agent_node_key",
    "build_agent_graph",
    "producer_agent",
]
