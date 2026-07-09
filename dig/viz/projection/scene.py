"""Renderer-neutral DIG scene data."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from ...graph import DIGGraph
from ...views import (
    DIGBipartiteEdge,
    DIGBipartiteGraphData,
    DIGBipartiteNode,
    activation_event_graph,
)
from ...node import SYSTEM_AGENT_ID
from ..config import EDGE_STYLE_SOLID, MIN_ACT_WIDTH_FRAC
from .layout import DIGLayout, compute_layout
from ..styles import DIGLineStyle, activation_style, edge_style as style_edge


@dataclass(frozen=True)
class DIGRenderScene:
    dig: DIGGraph
    layout: DIGLayout
    graph: DIGBipartiteGraphData
    clean_edges: list[DIGBipartiteEdge]

    @property
    def nodes(self) -> list[DIGBipartiteNode]:
        return self.graph.nodes

    @property
    def edges(self) -> list[DIGBipartiteEdge]:
        return self.graph.edges

    @property
    def x_extent(self) -> float:
        xs = [p[0] for p in self.layout.positions.values()]
        for x0, x1 in self.layout.activation_extent.values():
            xs.append(x0)
            xs.append(x1)
        return (max(xs) - min(xs)) if xs else 1.0

    @property
    def agent_ticks(self) -> tuple[list[float], list[str]]:
        real_agents = [a for a in self.layout.agent_order if a != SYSTEM_AGENT_ID]
        has_system = SYSTEM_AGENT_ID in self.layout.lane_for_agent

        if len(real_agents) >= 8:
            first = real_agents[0]
            last = real_agents[-1]
            first_lane = self.layout.lane_for_agent[first]
            last_lane = self.layout.lane_for_agent[last]
            positions = [first_lane, (first_lane + last_lane) / 2, last_lane]
            labels = [first, "...", last]
            if has_system:
                positions.append(self.layout.lane_for_agent[SYSTEM_AGENT_ID])
                labels.append(SYSTEM_AGENT_ID)
            return positions, labels

        return (
            [self.layout.lane_for_agent[a] for a in self.layout.agent_order],
            list(self.layout.agent_order),
        )

    @property
    def y_range(self) -> tuple[float, float]:
        lanes = list(self.layout.lane_for_agent.values())
        if not lanes:
            return -1.0, 1.0
        # Enlarge the TOP margin by lane span so a thinned top label (agent_N) clears the
        # panel above's bottom label at a gapless seam (e.g. an embedding figure).
        top_margin = max(0.6, (max(lanes) - min(lanes)) * 0.07)
        return min(lanes) - 0.6, max(lanes) + top_margin

    def edge_style(self, edge: DIGBipartiteEdge) -> DIGLineStyle:
        return style_edge(edge, self.dig)

    def gantt_bars(self) -> Iterator[tuple[float, float, float, str, bool]]:
        """Per-activation gantt geometry: (x_start, x_end, lane_y, color,
        is_instant), shared by both renderers. ``is_instant`` marks activations
        shorter than the min-width fraction of the x-extent; those draw as a
        vertical tick instead of a bar."""
        x_extent = self.x_extent
        cutoff = x_extent * MIN_ACT_WIDTH_FRAC if x_extent > 0 else 0.0
        for aid, act in self.dig.activations.items():
            if aid not in self.layout.activation_extent:
                continue
            x0, x1 = self.layout.activation_extent[aid]
            yield (
                x0, x1,
                self.layout.lane_for_agent.get(act.agent_id, 0),
                activation_style(act, self.nodes).color,
                (x1 - x0) <= cutoff,
            )


def build_render_scene(dig: DIGGraph) -> DIGRenderScene:
    layout = compute_layout(dig)
    graph = activation_event_graph(dig)
    clean_edges = [
        edge for edge in graph.edges
        if style_edge(edge, dig)[3] == EDGE_STYLE_SOLID
    ]
    return DIGRenderScene(
        dig=dig,
        layout=layout,
        graph=graph,
        clean_edges=clean_edges,
    )
