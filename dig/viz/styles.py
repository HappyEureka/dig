"""Renderer-neutral DIG visualization styles."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Tuple

from ..graph import DIGEvent
from ..node import SYSTEM_AGENT_ID
from .config import (
    ACTIVATION_COLORS,
    ACTIVATION_NODE_ALPHA,
    ACTIVATION_SIZE,
    EDGE_ACTION_COLORS,
    EDGE_ACTION_STYLES,
    EDGE_STYLE_DASHED,
    EVENT_DEFAULT_COLOR,
    EVENT_NODE_ALPHA,
    EVENT_ROOT_COLOR,
    EVENT_ROOT_SIZE,
    EVENT_SIZE,
    EVENT_TOOL_COLOR,
    EVENT_TOOL_SIZE,
    SYSTEM_ANNOTATION_COLOR,
    SYSTEM_COLOR,
    SYSTEM_SIZE,
)


@dataclass(frozen=True)
class DIGMarkerStyle:
    color: str
    alpha: float
    size: float
    marker: str


DIGLineStyle = Tuple[str, float, float, str]

EDGE_STYLES = {
    "consume": (
        EDGE_ACTION_COLORS["consume"], 0.85, 1.0, EDGE_ACTION_STYLES["consume"]
    ),
    "rerouted": (
        EDGE_ACTION_COLORS["rerouted"], 0.85, 1.0, EDGE_ACTION_STYLES["rerouted"]
    ),
    "reroute": (
        EDGE_ACTION_COLORS["reroute"], 0.70, 1.0, EDGE_ACTION_STYLES["reroute"]
    ),
    "discard": (
        EDGE_ACTION_COLORS["discard"], 0.70, 1.0, EDGE_ACTION_STYLES["discard"]
    ),
    "wait": (
        EDGE_ACTION_COLORS["wait"], 0.70, 1.0, EDGE_ACTION_STYLES["wait"]
    ),
    "pending": (
        EDGE_ACTION_COLORS["pending"], 0.40, 0.65, EDGE_ACTION_STYLES["pending"]
    ),
    "submit": (
        EDGE_ACTION_COLORS["submit"], 0.90, 1.5, EDGE_ACTION_STYLES["submit"]
    ),
}

# Healer/system edges are not a handling action, so they live outside
# EDGE_STYLES: one base style everywhere an intervention edge is drawn.
INTERVENTION_STYLE: DIGLineStyle = (
    SYSTEM_ANNOTATION_COLOR, 0.7, 1.6, EDGE_STYLE_DASHED,
)

# Display label per edge kind -- the single source for every legend.
EDGE_KIND_LABELS = {
    "consume": "Consume",
    "rerouted": "Reroute",
    "discard": "Discard",
    "wait": "Wait",
    "submit": "Submit",
    "pending": "Pending",
    "intervention": "Intervention",
}


def edge_kind(edge: Any, dig: Any) -> str:
    """The DIG edge's semantic kind, matching the legend categories: 'intervention' (a
    healer annotation / system-agent edge), else consume / wait / discard / rerouted /
    submit / pending. An intervention is specifically a healer-produced edge -- a normal
    agent's wait / discard / reroute is NOT an intervention."""
    if edge.metadata.get("annotation"):
        return "intervention"
    if edge.metadata.get("system_event") and edge.source in dig.activations:
        src_act = dig.activations.get(edge.source)
        if src_act and src_act.agent_id == SYSTEM_AGENT_ID:
            return "intervention"

    label = "pending"
    dst_act = dig.activations.get(edge.target)
    src_evt = dig.events.get(edge.source)
    if dst_act and src_evt:
        label = src_evt.reaction_label_for(activation_id=edge.target)
        if label == DIGEvent.Reaction.Label.CONSUME:
            label = "consume"
        elif label == DIGEvent.Reaction.Label.WAIT:
            label = "wait"
        elif label == DIGEvent.Reaction.Label.DISCARD:
            label = "discard"
        elif label == DIGEvent.Reaction.Label.REROUTE:
            label = "rerouted"
    if label == "pending" and src_evt and dst_act:
        reaction = src_evt.recipients.get(dst_act.agent_id)
        if reaction is not None and reaction.label == DIGEvent.Reaction.Label.REROUTE:
            label = "rerouted"
    if (
        label == DIGEvent.Reaction.Label.CONSUME.value
        and dst_act is not None
        and dst_act.is_submitting
    ):
        label = "submit"
    return label


def edge_style(edge: Any, dig: Any) -> DIGLineStyle:
    kind = edge_kind(edge, dig)
    if kind == "intervention":
        color, alpha, width, dash = INTERVENTION_STYLE
        if edge.metadata.get("annotation"):
            width = 2.0  # healer annotations draw heavier than plain system edges
        return (color, alpha, width, dash)
    return EDGE_STYLES.get(kind, EDGE_STYLES["pending"])


def activation_style(act: Any, nodes: List[Any]) -> DIGMarkerStyle:
    if act.agent_id == SYSTEM_AGENT_ID:
        return DIGMarkerStyle(
            SYSTEM_COLOR,
            ACTIVATION_NODE_ALPHA,
            SYSTEM_SIZE,
            "square",
        )
    classification = None
    for node in nodes:
        if node.id == act.id:
            classification = node.metadata.get("classification")
            break
    return DIGMarkerStyle(
        ACTIVATION_COLORS.get(classification, ACTIVATION_COLORS[None]),
        ACTIVATION_NODE_ALPHA,
        ACTIVATION_SIZE,
        "circle",
    )


def event_style(event: DIGEvent) -> DIGMarkerStyle:
    if event.source_activation_id is None:
        # A root event: no producing activation.
        return DIGMarkerStyle(
            EVENT_ROOT_COLOR,
            EVENT_NODE_ALPHA,
            EVENT_ROOT_SIZE,
            "square",
        )
    if event.label == DIGEvent.Label.TOOL:
        return DIGMarkerStyle(
            EVENT_TOOL_COLOR,
            EVENT_NODE_ALPHA,
            EVENT_TOOL_SIZE,
            "square",
        )
    return DIGMarkerStyle(
        EVENT_DEFAULT_COLOR,
        EVENT_NODE_ALPHA,
        EVENT_SIZE,
        "square",
    )


def legend_node_styles() -> List[Tuple[str, DIGMarkerStyle]]:
    return [
        ("Activation", DIGMarkerStyle("#1f77b4", 1.0, ACTIVATION_SIZE, "circle")),
        (
            "Comm event",
            DIGMarkerStyle(EVENT_DEFAULT_COLOR, 1.0, EVENT_SIZE, "square"),
        ),
        (
            "Tool event",
            DIGMarkerStyle(EVENT_TOOL_COLOR, 1.0, EVENT_TOOL_SIZE, "square"),
        ),
        ("System", DIGMarkerStyle(SYSTEM_COLOR, 1.0, SYSTEM_SIZE, "square")),
        (
            "Failed",
            DIGMarkerStyle(ACTIVATION_COLORS["failed"], 1.0, ACTIVATION_SIZE, "circle"),
        ),
    ]


def legend_edge_styles() -> List[Tuple[str, DIGLineStyle]]:
    color, alpha, _width, dash = INTERVENTION_STYLE
    styles: List[Tuple[str, DIGLineStyle]] = [
        (EDGE_KIND_LABELS[kind], EDGE_STYLES[kind])
        for kind in ("consume", "rerouted", "discard", "wait", "submit")
    ]
    # legend swatch drawn heavier so the dash pattern reads at legend scale
    styles.append((EDGE_KIND_LABELS["intervention"], (color, alpha, 2.5, dash)))
    return styles
