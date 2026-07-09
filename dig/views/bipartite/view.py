"""Bipartite graph derived from DIG activations and events.

`DIGGraph` stores first-class activation nodes and event nodes; it does not
keep a separate edge table. These queries materialize the traditional
activation/event graph used by serialization, lineage analysis, and
renderers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ...graph import DIGGraph, SYSTEM_AGENT_ID
from ...node import EVENT_INTERVENTION_TYPE, EVENT_SYSTEM_ACTIVATION_ID


@dataclass
class DIGBipartiteNode:
    """Node in the derived activation/event graph."""

    id: str
    layer: str
    label: str
    metadata: Dict[str, Any]

    def __str__(self) -> str:
        return (
            f"DIGBipartiteNode(id={self.id}, layer={self.layer}, "
            f"label={self.label}, metadata={self.metadata})"
        )


@dataclass
class DIGBipartiteEdge:
    """Edge in the derived activation/event graph."""

    source: str
    target: str
    relation: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    id: Optional[str] = None
    index: int = 0

    def __str__(self) -> str:
        relation = self.relation or "edge"
        return (
            f"DIGBipartiteEdge(id={self.id}, {self.source}->{self.target}, "
            f"relation={relation}, metadata={self.metadata})"
        )


@dataclass
class DIGBipartiteGraphData:
    """Materialized activation/event graph plus lookup tables."""

    nodes: List[DIGBipartiteNode]
    edges: List[DIGBipartiteEdge]
    activation_inputs: Dict[str, List[str]]
    activation_outputs: Dict[str, List[str]]
    event_source: Dict[str, str]


def edges(dig: DIGGraph) -> List[DIGBipartiteEdge]:
    """The derived bipartite edge list over activation/event nodes."""
    out: List[DIGBipartiteEdge] = []

    def append(
        source: str,
        target: str,
        relation: str,
        metadata: Dict[str, Any],
        edge_id: str,
    ) -> None:
        out.append(
            DIGBipartiteEdge(
                source=source,
                target=target,
                relation=relation,
                metadata=metadata,
                id=edge_id,
                index=len(out),
            )
        )

    for aid, act in dig.activations.items():
        for output in act.outputs:
            # One production edge per event, from its TRUE producer: a
            # passed-through output (recorded elsewhere, flowing through this
            # outputs list) keeps its provenance and gets no second edge.
            if output.source_activation_id != aid:
                continue
            append(
                aid,
                output.id,
                "output",
                {
                    "event_id": output.id,
                    "relation": "output",
                    "system_event": act.agent_id == SYSTEM_AGENT_ID,
                    "submit": act.is_submitting,
                },
                f"{output.id}:prod",
            )
        for eid in act.input_event_ids:
            event = dig.events.get(eid)
            label = (
                event.reaction_label_for(activation_id=aid)
                if event is not None else None
            ) or act.reaction_to(eid)
            relation = label.value
            append(
                eid,
                aid,
                relation,
                {
                    "event_id": eid,
                    "dst_agent": act.agent_id,
                    "system_event": _system_produced(dig, event),
                    "label": relation,
                },
                f"{eid}->{aid}",
            )
    for eid, ev in dig.events.items():
        system_activation_id = ev.metadata.get(EVENT_SYSTEM_ACTIVATION_ID)
        if system_activation_id:
            append(
                system_activation_id,
                eid,
                "annotation",
                {
                    "event_id": eid,
                    "relation": "annotation",
                    "system_event": True,
                    "annotation": True,
                    "intervention_type": ev.metadata.get(EVENT_INTERVENTION_TYPE),
                },
                f"{eid}:annotation",
            )
    return out


def activation_event_graph(dig: DIGGraph) -> DIGBipartiteGraphData:
    """Materialize the activation/event bipartite graph and lookup tables."""
    nodes: List[DIGBipartiteNode] = []

    for aid, act in dig.activations.items():
        structural = act.label.value
        classification = None
        if act.agent_id != SYSTEM_AGENT_ID:
            classification = "submit" if act.is_submitting else structural
        if act.failed:
            # A failed firing is an attempt, not a reducing/generating step.
            label = "failed"
            if act.agent_id != SYSTEM_AGENT_ID:
                classification = "failed"
        elif act.agent_id == SYSTEM_AGENT_ID and act.intervention_type:
            label = act.intervention_type
        elif act.is_submitting:
            label = "submit"
        else:
            label = structural
        nodes.append(
            DIGBipartiteNode(
                id=aid,
                layer="Activation",
                label=label,
                metadata={
                    "type": "activation",
                    "classification": classification,
                },
            )
        )

    for ev in dig.events.values():
        nodes.append(DIGBipartiteNode(
            id=ev.id,
            layer="Event",
            label=ev.id or "event",
            metadata={"type": "event"},
        ))

    activation_inputs = {
        aid: list(act.input_event_ids)
        for aid, act in dig.activations.items()
    }
    activation_outputs = {
        aid: list(act.output_event_ids)
        for aid, act in dig.activations.items()
    }
    event_source = {
        ev.id: ev.source_activation_id
        for ev in dig.events.values()
        if ev.source_activation_id
    }

    return DIGBipartiteGraphData(
        nodes=nodes,
        edges=edges(dig),
        activation_inputs=activation_inputs,
        activation_outputs=activation_outputs,
        event_source=event_source,
    )


def _system_produced(dig: DIGGraph, event: Any) -> bool:
    if event is None or not event.source_activation_id:
        return False
    src_act = dig.activations.get(event.source_activation_id)
    return src_act is not None and src_act.agent_id == SYSTEM_AGENT_ID
