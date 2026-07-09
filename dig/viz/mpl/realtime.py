"""Real-time matplotlib visualization of the DIG."""

import queue

import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from matplotlib.lines import Line2D

from ...graph import DIGGraph
from ..config import (
    ACT_HEIGHT,
    ACTIVATION_LABEL_FONTSIZE,
    AXIS_LABEL_FONTSIZE,
    EVENT_LABEL_FONTSIZE,
    LEGEND_FONTSIZE,
    NODE_LABEL_COLOR,
    NODE_OUTLINE_COLOR,
    PANEL_LABEL_FONTSIZE,
    TICK_FONTSIZE,
)
from ..projection.scene import DIGRenderScene, build_render_scene
from ..styles import (
    activation_style,
    event_style,
    legend_edge_styles,
    legend_node_styles,
)


_MPL_MARKERS = {"circle": "o", "square": "s"}


class RealtimeDIGVisualizer:
    """Matplotlib realtime DIG visualizer."""

    def __init__(self, update_interval: int = 500):
        self.update_interval = update_interval
        self.update_queue: queue.Queue = queue.Queue()
        self.current_dig: DIGGraph | None = None
        self.window_closed = False
        self.anim = None
        self.fig, (self.ax_full, self.ax_clean, self.ax_gantt) = plt.subplots(
            3, 1, figsize=(14, 11), sharex=True,
        )
        self.fig.canvas.mpl_connect("close_event", self._on_close)

    def update_from_dig(self, dig: DIGGraph) -> None:
        """Queue a DIG snapshot for the next animation frame."""
        if self.is_closed():
            return
        self.update_queue.put(dig)
        try:
            if self.fig and self.fig.canvas:
                self.fig.canvas.draw_idle()
                self.fig.canvas.flush_events()
        except Exception:  # noqa: BLE001
            pass

    def start(self, block: bool = True) -> None:
        """Open the window + start the FuncAnimation loop."""
        if self.is_closed():
            return
        plt.ion()
        self.anim = FuncAnimation(
            self.fig, self._render,
            interval=self.update_interval,
            cache_frame_data=False,
        )
        plt.show(block=block)
        if not block:
            plt.pause(0.001)

    def wait_for_close(self) -> None:
        """Block until the user closes the matplotlib window."""
        while not self.is_closed():
            plt.pause(0.05)

    def render(self, dig: DIGGraph) -> None:
        """Draw one frame immediately."""
        if self.is_closed():
            return
        self.update_from_dig(dig)
        self._render(0)

    def freeze(self) -> None:
        """Stop polling while leaving the current frame visible."""
        self._stop_animation()
        try:
            if not self.is_closed() and self.fig and self.fig.canvas:
                self.fig.canvas.draw_idle()
        except Exception:  # noqa: BLE001
            pass

    def _render(self, frame) -> None:
        """FuncAnimation callback. Drains the update queue and repaints."""
        while not self.update_queue.empty():
            try:
                self.current_dig = self.update_queue.get_nowait()
            except queue.Empty:
                break

        if self.current_dig is None:
            return

        dig = self.current_dig

        self.ax_full.clear()
        self.ax_clean.clear()
        self.ax_gantt.clear()

        if not dig.activations:
            for ax in (self.ax_full, self.ax_clean, self.ax_gantt):
                ax.text(0.5, 0.5, "Waiting for activations...",
                        ha="center", va="center", transform=ax.transAxes)
            return

        try:
            scene = build_render_scene(dig)
        except Exception as exc:  # noqa: BLE001
            print(f"[DIG VIZ] Error building graph: {exc}")
            return

        self._render_panel(self.ax_full, scene, scene.edges,
                           title="DIG (Full)")
        self._render_panel(self.ax_clean, scene, scene.clean_edges,
                           title="DIG (Clean)")
        self._render_gantt_panel(self.ax_gantt, scene)
        self._draw_legend()
        self.fig.tight_layout(rect=[0.0, 0.0, 1.0, 0.95])

    def _render_gantt_panel(self, ax, scene: DIGRenderScene) -> None:
        """Draw activation durations only."""
        ax.set_ylabel("Agent Activation", fontsize=PANEL_LABEL_FONTSIZE,
                      fontweight="bold", labelpad=12)
        ax.set_xlabel("Time (s)", fontsize=AXIS_LABEL_FONTSIZE,
                      fontweight="bold", labelpad=8)
        self._set_agent_yticks(ax, scene)
        ax.grid(False)

        for x0, x1, y, color, instant in scene.gantt_bars():
            if instant:
                ax.vlines(
                    x0, y - ACT_HEIGHT / 2, y + ACT_HEIGHT / 2,
                    color=color, alpha=0.9, linewidth=2.5, zorder=3,
                )
                continue
            ax.barh(
                y, x1 - x0, left=x0, height=ACT_HEIGHT,
                color=color, alpha=0.75,
                edgecolor="white", linewidth=1, zorder=2,
            )


    def _render_panel(self, ax, scene: DIGRenderScene, edges, *, title: str):
        """Draw activation/event nodes and edges."""
        dig = scene.dig
        layout = scene.layout
        ax.set_ylabel(title, fontsize=PANEL_LABEL_FONTSIZE,
                      fontweight="bold", labelpad=12)
        self._set_agent_yticks(ax, scene)
        ax.grid(False)

        for edge in edges:
            self._draw_edge(ax, scene, edge)

        # Activations and events draw the same way; they differ only in style
        # source, outline weight, stacking order, and label size.
        node_groups = (
            (dig.activations, lambda act: activation_style(act, scene.nodes),
             1.2, 3, ACTIVATION_LABEL_FONTSIZE),
            (dig.events, event_style, 1.1, 4, EVENT_LABEL_FONTSIZE),
        )
        for nodes, style_of, outline, zorder, label_size in node_groups:
            for nid, node in nodes.items():
                if nid not in layout.positions:
                    continue
                x, y = layout.positions[nid]
                style = style_of(node)
                ax.scatter(
                    x, y,
                    c=style.color,
                    marker=_MPL_MARKERS[style.marker],
                    s=style.size,
                    edgecolors=NODE_OUTLINE_COLOR,
                    linewidths=outline,
                    zorder=zorder,
                    alpha=style.alpha,
                )
                ax.text(
                    x, y, nid,
                    ha="center", va="center",
                    fontsize=label_size,
                    fontweight="bold",
                    color=NODE_LABEL_COLOR,
                    zorder=5,
                )

    def _draw_edge(self, ax, scene: DIGRenderScene, edge) -> None:
        """Draw one scene edge."""
        layout = scene.layout
        if edge.source not in layout.positions or edge.target not in layout.positions:
            return
        x0, y0 = layout.positions[edge.source]
        x1, y1 = layout.positions[edge.target]
        color, alpha, lw, ls = scene.edge_style(edge)
        ax.plot([x0, x1], [y0, y1],
                color=color, alpha=alpha, linewidth=lw, linestyle=ls,
                zorder=2)

    def _set_agent_yticks(self, ax, scene: DIGRenderScene) -> None:
        """Apply agent lane ticks."""
        positions, labels = scene.agent_ticks

        ax.set_yticks(positions)
        ax.set_yticklabels(labels, fontsize=TICK_FONTSIZE)
        ax.tick_params(axis="x", labelsize=TICK_FONTSIZE)
        ax.set_ylim(*scene.y_range)

    def _legend_handles(self) -> list:
        """Build the DIG legend handles from the shared style tables."""
        handles = []
        for label, style in legend_node_styles():
            handles.append(Line2D(
                [0], [0],
                marker=_MPL_MARKERS[style.marker],
                color="w",
                markerfacecolor=style.color,
                markersize=8,
                markeredgecolor=NODE_OUTLINE_COLOR,
                label=label,
            ))
        for label, style in legend_edge_styles():
            color, _alpha, width, line_style = style
            handles.append(Line2D(
                [0], [0],
                color=color,
                linewidth=width,
                linestyle=line_style,
                label=label,
            ))
        return handles

    def _draw_legend(self) -> None:
        """Draw the figure-level legend."""
        legend_elements = self._legend_handles()
        self.fig.legend(
            handles=legend_elements,
            loc="upper center",
            bbox_to_anchor=(0.5, 1.0),
            ncol=len(legend_elements),
            fontsize=LEGEND_FONTSIZE,
            frameon=True,
            columnspacing=1.4,
            handlelength=2.0,
            handletextpad=0.5,
        )

    def is_closed(self) -> bool:
        """Whether the matplotlib window has been closed."""
        if self.window_closed:
            return True
        if not plt.fignum_exists(self.fig.number):
            self.window_closed = True
            self._stop_animation()
            return True
        return False

    def _stop_animation(self) -> None:
        if self.anim is None:
            return
        try:
            self.anim.event_source.stop()
        except Exception:  # noqa: BLE001
            pass
        self.anim = None

    def _on_close(self, event) -> None:
        self.window_closed = True
        self._stop_animation()
