"""Plotly renderer for the bipartite view of the DIG.

Renders the same scene as the realtime matplotlib window -- the Full and
Clean activation/event panels over the agent lanes, plus the activation
spans -- as one interactive plotly figure with hover detail. Layout,
styles, and legend all come from the shared projection/styles tables, so
this renderer and the matplotlib one cannot drift apart.
"""

from __future__ import annotations

import math

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from ...graph import DIGGraph
from ..config import ACT_HEIGHT, NODE_LABEL_COLOR, NODE_OUTLINE_COLOR
from ..projection.scene import DIGRenderScene, build_render_scene
from ..styles import (
    activation_style,
    event_style,
    legend_edge_styles,
    legend_node_styles,
)
from .primitives import escape, plotly_dash, with_alpha

_ROWS = {"full": 1, "clean": 2, "gantt": 3}


def _marker_px(mpl_area: float) -> float:
    """The style tables carry matplotlib scatter areas; plotly wants px."""
    return math.sqrt(mpl_area) * 1.3


def build_bipartite_viz(dig: DIGGraph) -> "go.Figure | None":
    """Build the bipartite-view figure; None when the DIG is empty."""
    if not dig.activations and not dig.events:
        return None
    scene = build_render_scene(dig)

    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True,
        row_heights=[0.4, 0.4, 0.2], vertical_spacing=0.07,
        subplot_titles=("Full", "Clean", "Activation spans"),
    )
    _draw_panel(fig, scene, scene.edges, row=_ROWS["full"])
    _draw_panel(fig, scene, scene.clean_edges, row=_ROWS["clean"])
    _draw_gantt(fig, scene, row=_ROWS["gantt"])
    _draw_legend(fig)

    ticks, labels = scene.agent_ticks
    lo, hi = scene.y_range
    for row in _ROWS.values():
        fig.update_yaxes(
            tickvals=ticks, ticktext=labels, range=[lo, hi], row=row, col=1,
        )
    fig.update_xaxes(title_text="Time (s)", row=_ROWS["gantt"], col=1)
    fig.update_layout(
        template="plotly_white",
        margin=dict(l=40, r=20, t=70, b=40),
        height=780,
        legend=dict(orientation="h", yanchor="bottom", y=1.04, x=0),
    )
    return fig


def _draw_panel(fig: go.Figure, scene: DIGRenderScene, edges, *, row: int) -> None:
    layout = scene.layout
    for edge in edges:
        if edge.source not in layout.positions or edge.target not in layout.positions:
            continue
        x0, y0 = layout.positions[edge.source]
        x1, y1 = layout.positions[edge.target]
        color, alpha, width, dash = scene.edge_style(edge)
        fig.add_trace(go.Scatter(
            x=[x0, x1], y=[y0, y1],
            mode="lines",
            line=dict(color=with_alpha(color, alpha), width=width + 0.4,
                      dash=plotly_dash(dash)),
            hoverinfo="skip",
            showlegend=False,
        ), row=row, col=1)

    # Activations and events draw the same way; they differ only in style
    # source, label placement, and hover kind.
    node_groups = (
        ("Activation", scene.dig.activations,
         lambda act: activation_style(act, scene.nodes), "markers+text"),
        ("Event", scene.dig.events, lambda ev: event_style(ev), "markers"),
    )
    for kind, nodes, style_of, mode in node_groups:
        xs, ys, colors, sizes, symbols, texts, hovers, keys = (
            [], [], [], [], [], [], [], [],
        )
        for nid, node in nodes.items():
            if nid not in layout.positions:
                continue
            x, y = layout.positions[nid]
            style = style_of(node)
            xs.append(x)
            ys.append(y)
            colors.append(with_alpha(style.color, style.alpha))
            sizes.append(_marker_px(style.size))
            symbols.append(style.marker)
            texts.append(nid)
            hovers.append(f"<b>{kind} {escape(nid)}</b><br>Click for details")
            keys.append(nid)
        if not xs:
            continue
        fig.add_trace(go.Scatter(
            x=xs, y=ys,
            mode=mode,
            marker=dict(size=sizes, color=colors, symbol=symbols,
                        line=dict(width=1.2, color=NODE_OUTLINE_COLOR)),
            text=texts,
            textposition="middle center",
            textfont=dict(size=8, color=NODE_LABEL_COLOR, family="monospace"),
            customdata=keys,
            hovertext=hovers,
            hovertemplate="%{hovertext}<extra></extra>",
            showlegend=False,
        ), row=row, col=1)


def _draw_gantt(fig: go.Figure, scene: DIGRenderScene, *, row: int) -> None:
    for x0, x1, lane, color, instant in scene.gantt_bars():
        if instant:
            fig.add_trace(go.Scatter(
                x=[x0, x0], y=[lane - ACT_HEIGHT / 2, lane + ACT_HEIGHT / 2],
                mode="lines",
                line=dict(color=color, width=2.5),
                hoverinfo="skip",
                showlegend=False,
            ), row=row, col=1)
            continue
        fig.add_trace(go.Bar(
            x=[x1 - x0], base=[x0], y=[lane],
            orientation="h", width=ACT_HEIGHT,
            marker=dict(color=with_alpha(color, 0.75),
                        line=dict(color="white", width=1)),
            hovertemplate=f"{x0:.2f}s - {x1:.2f}s<extra></extra>",
            showlegend=False,
        ), row=row, col=1)
    fig.update_layout(barmode="overlay")


def _draw_legend(fig: go.Figure) -> None:
    """Legend entries from the shared style tables, drawn as dummy traces."""
    for label, style in legend_node_styles():
        fig.add_trace(go.Scatter(
            x=[None], y=[None],
            mode="markers",
            marker=dict(size=10, color=style.color, symbol=style.marker,
                        line=dict(width=1, color=NODE_OUTLINE_COLOR)),
            name=label,
            showlegend=True,
        ), row=1, col=1)
    for label, (color, alpha, width, dash) in legend_edge_styles():
        fig.add_trace(go.Scatter(
            x=[None], y=[None],
            mode="lines",
            line=dict(color=with_alpha(color, alpha), width=width,
                      dash=plotly_dash(dash)),
            name=label,
            showlegend=True,
        ), row=1, col=1)
