"""Finished-run DIG artifact folder writer.

`save_dig(dig, path)` bulk-writes the graph JSON (`DIGGraph.to_dict` plus
the derived edge view), a PNG of the realtime render, and one interactive
HTML presenting BOTH views -- the bipartite view and the agent view.
Rendering artifacts is a viz concern; the graph only provides `to_dict()`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from ..util.validate import jsonable
from ..views import edges as bipartite_edges


def save_dig(dig: Any, path: "str | Path | None" = None, *, dpi: int = 120) -> Dict[str, str]:
    """Write a finished-run DIG artifact folder from the current graph.

    `path` names the output folder. If it has a suffix (`dig.html`,
    `dig.png`), the suffix is stripped and the folder uses the stem. Each
    save bulk-overwrites the artifacts from the current graph."""
    out_dir = _artifact_dir(path or "dig")
    out_dir.mkdir(parents=True, exist_ok=True)

    graph_path = out_dir / "dig_graph.json"
    views_html_path = out_dir / "dig_views.html"
    png_path = out_dir / "dig.png"

    payload = dig.to_dict()
    # The derived edge view is a query answer; the artifact carries it so
    # downstream analysis needs no DIG install.
    payload["edges"] = [jsonable(edge) for edge in bipartite_edges(dig)]
    graph_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    html_written = _write_views_html(dig, views_html_path)
    png_written = _write_png(dig, png_path, dpi=dpi)

    return {
        "folder": str(out_dir),
        "graph": str(graph_path),
        "views_html": str(views_html_path) if html_written else "",
        "png": str(png_path) if png_written else "",
    }


def _write_views_html(dig: Any, output_file: Path) -> bool:
    """One HTML presenting both views: bipartite-view tab + agent-view tab,
    with the shared click-detail panel resolving every node against the
    detail registry."""
    from ..views import build_agent_graph
    from .html.agent_graph_view import (
        agent_graph_detail_registry,
        build_agent_graph_viz,
    )
    from .html.bipartite_view import build_bipartite_viz
    from .html.primitives import activation_detail_html, event_detail_html
    from .html.shell import render_shell

    bipartite = build_bipartite_viz(dig)
    if bipartite is None:
        return False

    registry: dict = {}
    for aid, act in dig.activations.items():
        registry[aid] = activation_detail_html(act, dig)
    for eid, ev in dig.events.items():
        registry[eid] = event_detail_html(ev, dig=dig)
    agent_graph = build_agent_graph(dig)
    registry.update(agent_graph_detail_registry(agent_graph, dig))
    agent_viz = build_agent_graph_viz(dig, graph=agent_graph)

    sections = []
    if agent_viz is not None:
        sections.append((
            "agentgraph",
            "Agent view",
            agent_viz.figure.to_html(full_html=False, include_plotlyjs=False),
        ))

    html_str = bipartite.to_html(include_plotlyjs="cdn")
    registry_json = json.dumps(registry).replace("</", "<\\/")
    html_str = html_str.replace(
        "</body>",
        render_shell(registry_json, sections) + "</body>",
    )
    output_file.write_text(html_str, encoding="utf-8")
    print(f"[SAVE] Saved views (bipartite + agent): {output_file}")
    return True


def _write_png(dig: Any, output_file: Path, *, dpi: int = 120) -> bool:
    from .mpl.realtime import RealtimeDIGVisualizer

    viz = RealtimeDIGVisualizer()
    viz.render(dig)
    fig = viz.fig
    if fig is None:
        return False
    fig.savefig(str(output_file), dpi=dpi, bbox_inches="tight")
    try:
        import matplotlib.pyplot as plt

        plt.close(fig)
    except Exception:  # noqa: BLE001
        pass
    return True


def _artifact_dir(path: "str | Path") -> Path:
    out = Path(path).expanduser()
    if out.suffix:
        out = out.with_suffix("")
    return out


__all__ = ["save_dig"]
