"""DIG -- Dynamic Interaction Graph: a representation for the emergent
collaboration of LLM agents.

DIG predefines no protocol, workflow, or role structure -- it records
whatever actually happens as agents interact. A run becomes a bipartite
graph of first-class nodes -- activations (one agent firing) and events
(one thing that flowed between agents) -- and DIG can optionally deliver
those events (DIG as the message bus, or use it observe-only). Internally
the package is split by ownership:

  node/       DIGEvent and DIGActivation -- first-class DIG node types.
  util/       generic leaf helpers (expect_type, jsonable).
  graph/      DIGGraph, roster, and delivery -- the representation only.
  agent/      persistent DIGAgentEntity identity/state plus DIGMailbox.
  interface/  DIGAgent, the callable adapter that records into DIG.
  views/      derived ways of looking at one recorded DIG.
  heal/       Healer + Intervention -- detect graph-shaped anomalies and
              repair the run in place (every applied intervention is
              recorded as a system activation).
  viz/        renderers (live matplotlib window; agent-view HTML).

A runtime records by handing the graph a DIGActivation -- what one agent
firing saw + produced; the graph materializes it into nodes + edges:

    dig = DIGGraph()
    seen = DIGEvent(payload={"problem": "root"}, recipients=["agent_1"])
    out = DIGEvent(payload={"answer": "..."}, recipients=["agent_2"])
    activation = dig.record_activation(DIGActivation(agent_id="agent_1", inputs=[seen], outputs=[out]))

`record_event` sits alongside `record_activation` for callers that record
events directly -- a root event, or a late event that forward-links onto its
source activation (named on `source_activation_id`).
"""

from .graph import (
    DIGActivation,
    DIGEvent,
    DIGGraph,
    SYSTEM_AGENT_ID,
)

__all__ = [
    # Node types. A runtime reports these and DIGGraph records them
    # (record_activation); DIGGraph records activation annotations under
    # metadata["dig"].
    "DIGEvent",
    "DIGActivation",
    # DIGGraph facade
    "DIGGraph",
    # The reserved system actor id.
    "SYSTEM_AGENT_ID",
]
