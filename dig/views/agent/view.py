"""The agent view of a recorded DIG.

The agent view drops the time axis entirely: each agent becomes one
node, and a directed edge from agent A to agent B bundles every *link* where
an activation of A produced an event addressed to (or reacted to by) B.
Edges are grouped by reaction kind, so a renderer can style arcs to match
the trace-view legend.

Root events (no producing activation) flow out of a synthetic ``ROOT_AGENT``
node so every event stays visible on some edge; events with no recipient and
no reaction are recorded as the producer's dangling outputs instead of an
edge.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...graph import DIGEvent, DIGGraph, SYSTEM_AGENT_ID
from ...node import EVENT_SYSTEM_ACTIVATION_ID
from ...util import natural_sort_key

ROOT_AGENT = "(root)"  # synthetic source node for root events


@dataclass(frozen=True)
class AgentGraphLink:
    """One event flowing between two agents.

    ``producer_activation_id`` is None for a root event and
    ``consumer_activation_id`` is None while no activation of the recipient
    has reacted to the event yet.
    """

    producer_activation_id: str | None
    event_id: str
    consumer_activation_id: str | None
    kind: str


@dataclass(frozen=True)
class AgentGraphEdge:
    """All links of one reaction kind from ``src`` to ``dst``."""

    src: str
    dst: str
    kind: str
    links: tuple[AgentGraphLink, ...]


@dataclass(frozen=True)
class AgentGraph:
    """Agent nodes plus kind-grouped directed edges."""

    agents: tuple[str, ...]
    edges: tuple[AgentGraphEdge, ...]
    activation_ids: dict[str, tuple[str, ...]]
    dangling_event_ids: dict[str, tuple[str, ...]]


def agent_node_key(agent_id: str) -> str:
    """Stable string id for one agent node."""
    return f"agent-{agent_id}"


def agent_edge_key(edge: AgentGraphEdge) -> str:
    """Stable string id for one kind-grouped edge."""
    return f"agent-edge-{edge.src}->{edge.dst}:{edge.kind}"


# DIG reaction label -> legend edge kind (submit is refined from consume below).
_REACTION_KINDS = {
    DIGEvent.Reaction.Label.CONSUME: "consume",
    DIGEvent.Reaction.Label.WAIT: "wait",
    DIGEvent.Reaction.Label.DISCARD: "discard",
    DIGEvent.Reaction.Label.REROUTE: "rerouted",
    DIGEvent.Reaction.Label.PENDING: "pending",
}


def build_agent_graph(dig: DIGGraph) -> AgentGraph:
    """Project the DIG onto agent nodes and kind-grouped directed edges."""
    reacted = _reaction_activations(dig)

    grouped: dict[tuple[str, str, str], list[AgentGraphLink]] = {}
    dangling: dict[str, list[str]] = {}
    for event in dig.events.values():
        src = producer_agent(event, dig)
        # Address by the recipients record, plus any agent that actually
        # reacted to the event (a reroute can hand it to a non-recipient).
        recipients = set(event.recipients) | {
            stamp.agent_id for stamp in event.reaction_stamps
        }
        if not recipients:
            dangling.setdefault(src, []).append(event.id)
            continue
        for dst in sorted(recipients, key=natural_sort_key):
            kind, consumer = _link_kind(event, dst, dig, reacted)
            grouped.setdefault((src, dst, kind), []).append(AgentGraphLink(
                producer_activation_id=event.source_activation_id,
                event_id=event.id,
                consumer_activation_id=consumer,
                kind=kind,
            ))

        # A healer annotation on this event is an intervention edge from the
        # system agent to the agents whose input it rewrote.
        system_aid = event.metadata.get(EVENT_SYSTEM_ACTIVATION_ID)
        if system_aid:
            for dst in sorted(event.recipients, key=natural_sort_key):
                grouped.setdefault((SYSTEM_AGENT_ID, dst, "intervention"), []).append(
                    AgentGraphLink(
                        producer_activation_id=system_aid,
                        event_id=event.id,
                        consumer_activation_id=None,
                        kind="intervention",
                    )
                )

    agents = _agent_order(dig, grouped, dangling)
    order = {agent: index for index, agent in enumerate(agents)}
    edges = tuple(
        AgentGraphEdge(src=src, dst=dst, kind=kind, links=tuple(links))
        for (src, dst, kind), links in sorted(
            grouped.items(),
            key=lambda item: (order[item[0][0]], order[item[0][1]], item[0][2]),
        )
    )
    return AgentGraph(
        agents=agents,
        edges=edges,
        activation_ids=_activations_by_agent(dig),
        dangling_event_ids={
            agent: tuple(event_ids) for agent, event_ids in dangling.items()
        },
    )


def producer_agent(event: DIGEvent, dig: DIGGraph) -> str:
    src = dig.activations.get(event.source_activation_id or "")
    return src.agent_id if src is not None else ROOT_AGENT


def _reaction_activations(dig: DIGGraph) -> dict[tuple[str, str], str]:
    """(event id, agent id) -> latest activation that reacted to the event."""
    out: dict[tuple[str, str], str] = {}
    for event in dig.events.values():
        for stamp in event.reaction_stamps:
            out[(event.id, stamp.agent_id)] = stamp.activation_id
    return out


def _link_kind(
    event: DIGEvent,
    agent_id: str,
    dig: DIGGraph,
    reacted: dict[tuple[str, str], str],
) -> tuple[str, str | None]:
    """Reaction kind and consumer activation for one (event, recipient)."""
    label = event.reaction_label_for(agent_id=agent_id)
    if label is None:
        reaction = event.recipients.get(agent_id)
        label = reaction.label if reaction is not None else DIGEvent.Reaction.Label.PENDING
    kind = _REACTION_KINDS[label]
    consumer = reacted.get((event.id, agent_id))
    if kind == "consume" and consumer is not None:
        act = dig.activations.get(consumer)
        if act is not None and act.is_submitting:
            kind = "submit"
    return kind, consumer


def _agent_order(
    dig: DIGGraph,
    grouped: dict[tuple[str, str, str], list[AgentGraphLink]],
    dangling: dict[str, list[str]],
) -> tuple[str, ...]:
    """Every agent with a node: activated, registered, or on an edge.

    Real agents sort naturally; the system and root nodes pin to the end,
    matching the lane order of the trace view.
    """
    seen = {act.agent_id for act in dig.activations.values()}
    seen |= {
        getattr(agent, "agent_id", agent_id)
        for agent_id, agent in dig.agents.items()
    }
    for src, dst, _kind in grouped:
        seen.add(src)
        seen.add(dst)
    seen |= set(dangling)

    real = sorted(
        (a for a in seen if a not in (SYSTEM_AGENT_ID, ROOT_AGENT)),
        key=natural_sort_key,
    )
    tail = [a for a in (SYSTEM_AGENT_ID, ROOT_AGENT) if a in seen]
    return tuple(real + tail)


def _activations_by_agent(dig: DIGGraph) -> dict[str, tuple[str, ...]]:
    by_agent: dict[str, list] = {}
    for act in dig.activations.values():
        by_agent.setdefault(act.agent_id, []).append(act)
    return {
        agent: tuple(
            a.id for a in sorted(
                acts,
                key=lambda a: (a.started_at if a.started_at is not None else 0.0, a.id or ""),
            )
        )
        for agent, acts in by_agent.items()
    }
