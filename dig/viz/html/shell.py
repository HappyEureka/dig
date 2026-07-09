"""HTML shell around the interactive DIG figure.

``write_interactive_html`` renders the Plotly figures; this module owns the
static page chrome: the tab bar, extra tab sections, the draggable node-detail
panel, and the client-side registry navigation. The stylesheet and the page
script are real files under ``assets/``; this module splices them, the
detail-panel markup, and the per-run JSON payloads into one fragment. The tab
bar is built from the sections present in the page, so adding a view is just
one more section.
"""

from __future__ import annotations

import html
from importlib import resources


def _asset(name: str) -> str:
    return (resources.files(__package__) / "assets" / name).read_text(
        encoding="utf-8"
    )


_DETAIL_PANEL_HTML = """
<div id="dig-node-detail-panel" aria-live="polite">
  <div id="dig-node-detail-header">
    <button id="dig-node-detail-back" type="button" aria-label="Back to previous node" title="Back">&#8592;</button>
    <span id="dig-node-detail-title">Node details</span>
    <button id="dig-node-detail-close" type="button" aria-label="Close node details">&times;</button>
  </div>
  <div id="dig-node-detail-content">Click a node to inspect it.</div>
</div>
"""


def render_shell(
    registry_json: str,
    sections: list[tuple[str, str, str]],
) -> str:
    """Render the page chrome to splice before ``</body>``.

    ``sections`` is an ordered list of ``(name, tab_label, inner_html)`` for
    every tab after the bipartite-view tab (which is the figure itself).
    ``registry_json`` is the click-detail registry: every clickable node's
    ``customdata`` key mapped to its rendered detail HTML.
    """
    sections_html = "".join(
        f'<section id="dig-{name}-section" class="dig-tab-panel dig-tab-section" '
        f'data-dig-panel="{name}" '
        f'data-dig-tab-label="{html.escape(label, quote=True)}" '
        f'aria-label="{html.escape(label, quote=True)}">'
        f"{content}</section>"
        for name, label, content in sections
    )
    # Only the script carries payload placeholders, so substitute there before
    # assembly -- section content can never collide with a placeholder name.
    script = _asset("shell.js")
    script = script.replace("__DIG_NODE_DETAILS_JSON__", registry_json)
    return (
        "<style>\n" + _asset("shell.css") + "</style>\n"
        + _DETAIL_PANEL_HTML
        + sections_html
        + "\n<script>\n" + script + "</script>\n"
    )
