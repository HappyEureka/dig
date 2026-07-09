"""The agent view of a recorded DIG -- one
node per agent, directed edges bundling every event flow between each pair,
grouped by reaction kind (`view.py`)."""

from .view import (
    ROOT_AGENT,
    AgentGraph,
    AgentGraphEdge,
    AgentGraphLink,
    agent_edge_key,
    agent_node_key,
    build_agent_graph,
    producer_agent,
)

__all__ = [
    "ROOT_AGENT",
    "AgentGraph",
    "AgentGraphEdge",
    "AgentGraphLink",
    "agent_edge_key",
    "agent_node_key",
    "build_agent_graph",
    "producer_agent",
]
