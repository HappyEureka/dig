"""Shared Plotly primitives for DIG-family interactive visualizations."""

from __future__ import annotations

from dataclasses import fields as dataclass_fields, is_dataclass
from enum import Enum
import html
import json
import textwrap
from typing import Any

from matplotlib.colors import to_rgba

from ...graph import DIGEvent
from ...views import activation_detail_fields


def with_alpha(color: str, alpha: float) -> str:
    """Return an rgba string for any matplotlib-parseable color."""
    if color.startswith("rgba"):
        return color
    r, g, b, _ = to_rgba(color)
    return f"rgba({round(r * 255)},{round(g * 255)},{round(b * 255)},{alpha})"


def plotly_dash(line_style: str) -> str:
    return "dash" if line_style == "--" else "solid"


def plotly_node_size(matplotlib_scatter_size: float) -> float:
    """Convert a matplotlib scatter area into a Plotly marker diameter."""
    return max(8.0, (matplotlib_scatter_size ** 0.5) * 0.9)


def wrap_text(text: Any, width: int = 80) -> str:
    """HTML-escape and wrap text for a Plotly detail field."""
    if text is None:
        return ""
    wrapped: list[str] = []
    for line in str(text).split("\n"):
        if line.strip():
            wrapped.extend(
                html.escape(part, quote=False)
                for part in textwrap.wrap(line, width=width)
            )
        else:
            wrapped.append("")
    return "<br>".join(wrapped)


def expand_escaped_newlines(text: str) -> str:
    return text.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\r", "\n")


def escape(value: Any) -> str:
    return html.escape(str(value), quote=False)


def relative_time_text(at: float, dig: Any) -> str:
    """Display an absolute wall-clock timestamp as relative seconds."""
    rel = dig.offset(float(at))
    sign = "+" if rel >= 0 else "-"
    return f"{sign}{abs(rel):.3f}s"


def timestamp_text(timestamp: DIGEvent.Timestamp, dig: Any | None = None) -> str:
    """Readable timestamp summary for detail panels."""
    at = relative_time_text(timestamp.at, dig) if dig is not None else f"{timestamp.at:.6f}"
    if timestamp.label == DIGEvent.Timestamp.Label.GENERATED:
        text = f"generated at {at}"
        if timestamp.by:
            text += f" by {timestamp.by}"
    elif timestamp.label == DIGEvent.Timestamp.Label.DELIVERED:
        text = f"delivered to {timestamp.to} at {at}"
        if timestamp.by:
            text += f" by {timestamp.by}"
    elif timestamp.label == DIGEvent.Timestamp.Label.MODIFIED:
        text = f"modified at {at}"
        if timestamp.by:
            text += f" by {timestamp.by}"
    elif timestamp.label == DIGEvent.Timestamp.Label.REACTED:
        text = f"{timestamp.agent_id} reacted as {timestamp.reaction_label.value} at {at}"
        if timestamp.activation_id:
            text += f" in activation {timestamp.activation_id}"
    else:
        text = f"{timestamp.label.value} at {at}"

    if timestamp.metadata:
        details = ", ".join(f"{k}={v!r}" for k, v in timestamp.metadata.items())
        text += f" ({details})"
    return text


def jsonable(value: Any, *, dig: Any | None = None, field_name: str | None = None) -> Any:
    if isinstance(value, DIGEvent.Timestamp):
        return timestamp_text(value, dig)
    if (
        dig is not None
        and field_name in {"started_at", "ended_at"}
        and isinstance(value, (float, int))
    ):
        return relative_time_text(float(value), dig)
    if is_dataclass(value):
        return str(value)
    if isinstance(value, dict):
        return {str(k): jsonable(v, dig=dig) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonable(v, dig=dig, field_name=field_name) for v in value]
    if isinstance(value, Enum):
        return value.value
    return value


def json_block(
    value: Any,
    *,
    width: int = 88,
    dig: Any | None = None,
    field_name: str | None = None,
) -> str:
    try:
        text = json.dumps(
            jsonable(value, dig=dig, field_name=field_name),
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    except TypeError:
        text = str(value)
    return wrap_text(expand_escaped_newlines(text), width=width)


def _known_node_ids(dig: Any | None) -> set:
    if dig is None:
        return set()
    return set(getattr(dig, "activations", {})) | set(getattr(dig, "events", {}))


def node_ref_anchor(node_id: str, text: str | None = None) -> str:
    """Render a registry key as a clickable in-panel cross-reference link.

    ``text`` is the visible label; it defaults to the key itself.
    """
    return (
        '<a class="dig-node-link" href="#" '
        f'data-node-id="{html.escape(str(node_id), quote=True)}">'
        f'{html.escape(str(text if text is not None else node_id), quote=False)}</a>'
    )


# ---------------------------------------------------------------------------
# Collapsible detail rendering. Each field renders as a native <details>
# (collapsed) when its value is a non-empty container, and inline when it is a
# scalar or empty. Reference fields are the exception: the referenced node
# name(s) stay visible as cross-links and only each node's own data collapses.
# ---------------------------------------------------------------------------

_REFERENCE_LIST_FIELDS = {"inputs", "outputs"}
_SINGLE_REF_FIELDS = {"source_activation_id"}
_TIME_FIELDS = {"started_at", "ended_at"}


def _is_inline_value(value: Any) -> bool:
    if value is None or isinstance(value, (str, int, float, bool)):
        return True
    if isinstance(value, (dict, list, tuple, set)) and not value:
        return True
    return False


def _scalar_html(value: Any) -> str:
    """One-line JSON-style rendering of a scalar/empty value, HTML-escaped."""
    try:
        text = json.dumps(jsonable(value), ensure_ascii=False, default=str)
    except TypeError:
        text = str(value)
    return escape(text)


def _ref_value_html(value: Any, known_ids: set, self_id: Any | None) -> str:
    """A single node reference: a cross-link unless it names this node itself."""
    if isinstance(value, str) and value in known_ids and value != self_id:
        return node_ref_anchor(value)
    return _scalar_html(value)


def _inline_row(name: str, value_html: str) -> str:
    return f'<div class="dig-row">{escape(name)}: {value_html}</div>'


def _collapsible_field(name: str, body_html: str) -> str:
    return (
        f'<details class="dig-field"><summary class="dig-field-label">'
        f'{escape(name)}:</summary>'
        f'<div class="dig-body">{body_html}</div></details>'
    )


def _node_item_html(summary: dict, dig: Any, known_ids: set, self_id: Any | None) -> str:
    """One referenced node: name visible as a cross-link, its data collapsed in."""
    node_id = summary.get("id")
    if node_id in known_ids and node_id != self_id:
        name_html = node_ref_anchor(node_id)
    else:
        name_html = escape(str(node_id))
    rows = []
    for key, value in summary.items():
        if key == "id":
            continue
        if key in _SINGLE_REF_FIELDS:
            rows.append(_inline_row(key, _ref_value_html(value, known_ids, self_id)))
        elif _is_inline_value(value):
            rows.append(_inline_row(key, _scalar_html(value)))
        else:
            rows.append(_collapsible_field(key, json_block(value, dig=dig, field_name=key)))
    return (
        f'<details class="dig-node-item"><summary>{name_html}</summary>'
        f'<div class="dig-body">{"".join(rows)}</div></details>'
    )


def _reference_list_html(
    name: str, summaries: Any, dig: Any, known_ids: set, self_id: Any | None
) -> str:
    if summaries:
        items = "".join(_node_item_html(s, dig, known_ids, self_id) for s in summaries)
    else:
        items = '<div class="dig-row dig-empty">(none)</div>'
    return (
        f'<div class="dig-ref-field">'
        f'<div class="dig-row dig-field-label">{escape(name)}:</div>{items}</div>'
    )


def _render_detail_fields(fields: Any, dig: Any, self_id: Any | None = None) -> str:
    known_ids = _known_node_ids(dig)
    out = []
    for name, value in fields:
        if name in _REFERENCE_LIST_FIELDS:
            out.append(_reference_list_html(name, value, dig, known_ids, self_id))
        elif name in _SINGLE_REF_FIELDS:
            out.append(_inline_row(name, _ref_value_html(value, known_ids, self_id)))
        elif name in _TIME_FIELDS and isinstance(value, (int, float)):
            out.append(_inline_row(name, _scalar_html(relative_time_text(float(value), dig))))
        elif _is_inline_value(value):
            out.append(_inline_row(name, _scalar_html(value)))
        else:
            out.append(_collapsible_field(name, json_block(value, dig=dig, field_name=name)))
    return "".join(out)


def activation_detail_html(act, dig) -> str:
    """Click-detail panel HTML for a DIG activation node (collapsible fields)."""
    return _render_detail_fields(activation_detail_fields(act), dig, self_id=act.id)


def event_detail_html(event, *, dig: Any | None = None) -> str:
    """Click-detail panel HTML for a DIG event node (collapsible fields)."""
    header = (
        f'<div class="dig-detail-title"><b>Event '
        f'{escape(event.id or "")}</b></div>'
    )
    fields = [(f.name, getattr(event, f.name)) for f in dataclass_fields(event)]
    return header + _render_detail_fields(fields, dig, self_id=event.id)
