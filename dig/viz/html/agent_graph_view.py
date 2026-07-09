"""Plotly renderer for the agent view of the DIG.

Agents sit on a circle; each kind-grouped directed edge draws as a bezier arc
styled like the trace-view legend, with a clickable count badge at its apex.
Clicking a node or badge opens the shared detail panel: the registry entries
built here cross-link straight into the activation/event entries, so the agent
view navigates into the underlying trace data.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import plotly.graph_objects as go

from ...graph import DIGGraph
from ...node import SYSTEM_AGENT_ID
from ...views.agent import (
    ROOT_AGENT,
    AgentGraph,
    AgentGraphEdge,
    agent_edge_key,
    agent_node_key,
    build_agent_graph,
)
from ..config import (
    ACTIVATION_COLORS,
    AGENT_ARC_CURVATURE,
    AGENT_ARC_KIND_SPREAD,
    AGENT_BADGE_FILL,
    AGENT_BADGE_SIZE,
    AGENT_EDGE_LABEL_FONTSIZE,
    AGENT_NODE_LABEL_FONTSIZE,
    AGENT_NODE_SIZE,
    AGENT_ROOT_NODE_SIZE,
    AGENT_SELF_LOOP_RADIUS,
    EVENT_ROOT_COLOR,
    NODE_LABEL_COLOR,
    NODE_OUTLINE_COLOR,
    SYSTEM_COLOR,
)
from .primitives import escape, node_ref_anchor, plotly_dash, with_alpha
from ..styles import EDGE_KIND_LABELS, EDGE_STYLES, INTERVENTION_STYLE


@dataclass(frozen=True)
class AgentGraphViz:
    """Rendered agent-graph tab: the figure plus the trace indices per arc,
    badge, and node, so client-side scripts can restyle exactly the
    traces an occurrence touches."""

    figure: go.Figure
    trace_index: dict[str, Any]


def _arc_style(kind: str):
    if kind == "intervention":
        return INTERVENTION_STYLE
    return EDGE_STYLES.get(kind, EDGE_STYLES["pending"])


def _node_positions(agents: tuple[str, ...]) -> dict[str, tuple[float, float]]:
    if len(agents) == 1:
        return {agents[0]: (0.0, 0.0)}
    out: dict[str, tuple[float, float]] = {}
    for index, agent in enumerate(agents):
        angle = math.pi / 2 - 2 * math.pi * index / len(agents)
        out[agent] = (math.cos(angle), math.sin(angle))
    return out


def _bezier(p0, p1, p2, samples: int = 24) -> tuple[list[float], list[float]]:
    xs, ys = [], []
    for i in range(samples + 1):
        t = i / samples
        u = 1.0 - t
        xs.append(u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0])
        ys.append(u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1])
    return xs, ys


def _arc_points(p0, p2, bow: float) -> tuple[list[float], list[float]]:
    """Quadratic arc bowing left of travel, so opposite directions separate."""
    dx, dy = p2[0] - p0[0], p2[1] - p0[1]
    length = math.hypot(dx, dy) or 1.0
    perp = (-dy / length, dx / length)
    mid = ((p0[0] + p2[0]) / 2.0, (p0[1] + p2[1]) / 2.0)
    control = (mid[0] + perp[0] * bow * length, mid[1] + perp[1] * bow * length)
    return _bezier(p0, control, p2)


def _self_loop_points(p, rank: int) -> tuple[list[float], list[float]]:
    """A loop just outside the node, growing per same-pair kind rank."""
    norm = math.hypot(p[0], p[1])
    u = (p[0] / norm, p[1] / norm) if norm > 1e-9 else (0.0, 1.0)
    radius = AGENT_SELF_LOOP_RADIUS * (1.0 + 0.45 * rank)
    center = (p[0] + u[0] * radius, p[1] + u[1] * radius)
    xs, ys = [], []
    for i in range(33):
        angle = 2 * math.pi * i / 32
        xs.append(center[0] + radius * math.cos(angle))
        ys.append(center[1] + radius * math.sin(angle))
    return xs, ys


def build_agent_graph_viz(
    dig: DIGGraph, *, graph: AgentGraph | None = None
) -> AgentGraphViz | None:
    """Build the agent-graph tab; None when the DIG has no agents."""
    graph = graph if graph is not None else build_agent_graph(dig)
    if not graph.agents:
        return None

    positions = _node_positions(graph.agents)
    fig = go.Figure()

    # Rank same-direction kinds so their arcs fan out instead of overlapping.
    pair_kinds: dict[tuple[str, str], list[str]] = {}
    for edge in graph.edges:
        pair_kinds.setdefault((edge.src, edge.dst), []).append(edge.kind)

    edge_traces: dict[str, dict[str, int]] = {}
    node_traces: dict[str, int] = {}

    seen_kinds: set[str] = set()
    for edge in graph.edges:
        color, alpha, width, dash = _arc_style(edge.kind)
        rank = pair_kinds[(edge.src, edge.dst)].index(edge.kind)
        if edge.src == edge.dst:
            xs, ys = _self_loop_points(positions[edge.src], rank)
        else:
            bow = AGENT_ARC_CURVATURE + AGENT_ARC_KIND_SPREAD * rank
            xs, ys = _arc_points(positions[edge.src], positions[edge.dst], bow)
        edge_traces[agent_edge_key(edge)] = {"arc": len(fig.data)}
        fig.add_trace(go.Scatter(
            x=xs, y=ys,
            mode="lines",
            line=dict(color=with_alpha(color, alpha), width=width + 0.6,
                      dash=plotly_dash(dash)),
            hoverinfo="skip",
            showlegend=False,
        ))
        if edge.src != edge.dst:
            # Arrowhead pointing along the arc into the target node.
            tail = len(xs) - 5
            fig.add_annotation(
                x=xs[-2], y=ys[-2], ax=xs[tail], ay=ys[tail],
                xref="x", yref="y", axref="x", ayref="y",
                showarrow=True, arrowhead=3, arrowsize=1.4,
                arrowwidth=max(1.0, width), arrowcolor=with_alpha(color, alpha),
                text="",
            )
        apex = len(xs) // 2
        edge_traces[agent_edge_key(edge)]["badge"] = len(fig.data)
        fig.add_trace(go.Scatter(
            x=[xs[apex]], y=[ys[apex]],
            mode="markers+text",
            marker=dict(size=AGENT_BADGE_SIZE, color=AGENT_BADGE_FILL,
                        line=dict(width=1.5, color=color)),
            text=[str(len(edge.links))],
            textposition="middle center",
            textfont=dict(size=AGENT_EDGE_LABEL_FONTSIZE, color=NODE_LABEL_COLOR,
                          family="monospace"),
            customdata=[agent_edge_key(edge)],
            hovertext=[
                f"<b>{escape(edge.src)} -> {escape(edge.dst)}</b><br>"
                f"{edge.kind} - {len(edge.links)} event(s)<br>Click for details"
            ],
            hovertemplate="%{hovertext}<extra></extra>",
            showlegend=False,
        ))
        seen_kinds.add(edge.kind)

    for agent in graph.agents:
        x, y = positions[agent]
        color, size, symbol = _node_style(agent)
        activation_count = len(graph.activation_ids.get(agent, ()))
        node_traces[agent] = len(fig.data)
        fig.add_trace(go.Scatter(
            x=[x], y=[y],
            mode="markers+text",
            marker=dict(size=size, color=with_alpha(color, 0.9), symbol=symbol,
                        line=dict(width=1.5, color=NODE_OUTLINE_COLOR)),
            text=[agent],
            textposition="bottom center",
            textfont=dict(size=AGENT_NODE_LABEL_FONTSIZE, color=NODE_LABEL_COLOR,
                          family="monospace"),
            customdata=[agent_node_key(agent)],
            hovertext=[
                f"<b>{escape(agent)}</b><br>{activation_count} activation(s)"
                "<br>Click for details"
            ],
            hovertemplate="%{hovertext}<extra></extra>",
            showlegend=False,
        ))

    for kind in sorted(seen_kinds):
        color, _alpha, width, dash = _arc_style(kind)
        fig.add_trace(go.Scatter(
            x=[None], y=[None],
            mode="lines",
            line=dict(color=color, width=width + 0.6, dash=plotly_dash(dash)),
            name=EDGE_KIND_LABELS.get(kind, kind),
            showlegend=True,
        ))

    fig.update_layout(
        height=700,
        hovermode="closest",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=60, r=60, t=60, b=60),
        legend=dict(
            orientation="h",
            yanchor="bottom", y=1.02,
            xanchor="center", x=0.5,
            font=dict(size=14),
            itemsizing="constant",
            bgcolor="rgba(255,255,255,0.95)",
            bordercolor="rgba(0,0,0,0.3)",
            borderwidth=1,
        ),
    )
    fig.update_xaxes(visible=False, range=[-1.55, 1.55])
    fig.update_yaxes(visible=False, range=[-1.55, 1.55], scaleanchor="x")
    return AgentGraphViz(
        figure=fig,
        trace_index={"edges": edge_traces, "nodes": node_traces},
    )


def _node_style(agent: str) -> tuple[str, float, str]:
    if agent == SYSTEM_AGENT_ID:
        return SYSTEM_COLOR, AGENT_NODE_SIZE, "square"
    if agent == ROOT_AGENT:
        return EVENT_ROOT_COLOR, AGENT_ROOT_NODE_SIZE, "square"
    return ACTIVATION_COLORS[None], AGENT_NODE_SIZE, "circle"


# ---------------------------------------------------------------------------
# Detail-panel registry entries. Anchors reuse the shared data-node-id
# navigation, so agent entries cross-link into activation/event entries and
# into each other.
# ---------------------------------------------------------------------------


def agent_graph_detail_registry(graph: AgentGraph, dig: DIGGraph) -> dict[str, str]:
    """Detail HTML for every agent node and kind-grouped edge."""
    registry: dict[str, str] = {}
    for agent in graph.agents:
        registry[agent_node_key(agent)] = _agent_node_detail_html(agent, graph)
    for edge in graph.edges:
        registry[agent_edge_key(edge)] = _agent_edge_detail_html(edge)
    return registry


def _agent_node_detail_html(agent: str, graph: AgentGraph) -> str:
    rows = [f'<div class="dig-detail-title"><b>Agent {escape(agent)}</b></div>']
    activation_ids = graph.activation_ids.get(agent, ())
    links = ", ".join(node_ref_anchor(aid) for aid in activation_ids) or "(none)"
    rows.append(f'<div class="dig-row">{len(activation_ids)} activations: {links}</div>')
    outgoing = [e for e in graph.edges if e.src == agent]
    incoming = [e for e in graph.edges if e.dst == agent]
    for title, edges in (("outgoing", outgoing), ("incoming", incoming)):
        if not edges:
            continue
        items = "".join(
            f'<div class="dig-row">{node_ref_anchor(agent_edge_key(e), _edge_label(e))}'
            f" - {len(e.links)} event(s)</div>"
            for e in edges
        )
        rows.append(
            f'<div class="dig-row dig-field-label">{title}:</div>{items}'
        )
    dangling = graph.dangling_event_ids.get(agent, ())
    if dangling:
        anchors = ", ".join(node_ref_anchor(eid) for eid in dangling)
        rows.append(
            f'<div class="dig-row">{len(dangling)} dangling outputs '
            f"(no recipient): {anchors}</div>"
        )
    return "".join(rows)


def _edge_label(edge: AgentGraphEdge) -> str:
    return f"{edge.src} -> {edge.dst} - {edge.kind}"


def _agent_edge_detail_html(edge: AgentGraphEdge) -> str:
    rows = [
        '<div class="dig-detail-title"><b>'
        f'{escape(edge.src)} -> {escape(edge.dst)} - {escape(edge.kind)}'
        "</b></div>",
        f'<div class="dig-row">{len(edge.links)} event(s)</div>',
    ]
    for link in edge.links:
        producer = (
            node_ref_anchor(link.producer_activation_id)
            if link.producer_activation_id else escape(ROOT_AGENT)
        )
        consumer = (
            node_ref_anchor(link.consumer_activation_id)
            if link.consumer_activation_id else "(no reaction)"
        )
        rows.append(
            f'<div class="dig-row">{producer} -> '
            f"{node_ref_anchor(link.event_id)} -> {consumer}</div>"
        )
    return "".join(rows)
