"""Node-detail analysis of the bipartite view.

Structured summaries of one activation -- ordered fields, per-event input/
output summaries, and a text dump: what a trace node "opens up" to. Like
`lineage`, an analysis with no renderer dependencies -- renderers consume these views; the node classes themselves
stay lean.
"""

from __future__ import annotations

import json
from enum import Enum
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from ...node import DIGActivation, DIGEvent, DIG_METADATA, DIG_STRUCTURAL


def activation_detail_fields(act: DIGActivation) -> Iterable[Tuple[str, Any]]:
    """Ordered (name, value) pairs for one activation's detail panel."""
    fields: List[Tuple[str, Any]] = [
        ("agent_id", act.agent_id),
        ("id", act.id),
        ("dig", _dig_summary(act)),
        ("inputs", _input_event_summaries(act)),
        ("outputs", _output_event_summaries(act)),
    ]
    if act.native_input is not None:
        fields.append(("native_input", act.native_input))
    if act.native_output is not None:
        fields.append(("native_output", act.native_output))
    metadata = {
        key: value
        for key, value in act.metadata.items()
        if key != DIG_METADATA
    }
    fields.extend([
        ("input_reactions", act.input_reactions),
        ("started_at", act.started_at),
        ("ended_at", act.ended_at),
        ("metadata", metadata),
        ("tool_calls", act.tool_calls),
    ])
    return fields


def activation_detail_text(
    act: DIGActivation,
    *,
    time_formatter: Optional[Callable[[float], str]] = None,
) -> str:
    """Multi-line text dump of one activation's detail fields."""
    lines = []
    for name, value in activation_detail_fields(act):
        rendered = _format_detail_value(name, value, time_formatter)
        lines.append(f"{name}: {rendered}")
    return "\n".join(lines)


def _dig_summary(act: DIGActivation) -> Dict[str, Any]:
    dig = dict(act.metadata.get(DIG_METADATA, {}))
    dig.setdefault(DIG_STRUCTURAL, act.label.value)
    return dig


def _input_event_summaries(act: DIGActivation) -> List[Dict[str, Any]]:
    return [
        {
            "id": event.id,
            "label": event.label.value,
            "source_activation_id": event.source_activation_id,
            "recipients": _recipient_summary(event),
            "reaction": _display_reaction(act, event.id),
        }
        for event in act.inputs
    ]


def _output_event_summaries(act: DIGActivation) -> List[Dict[str, Any]]:
    return [
        {
            "id": event.id,
            "label": event.label.value,
            "source_activation_id": event.source_activation_id,
            "recipients": _recipient_summary(event),
        }
        for event in act.outputs
    ]


def _recipient_summary(event: DIGEvent) -> Dict[str, str]:
    return {
        agent_id: str(reaction)
        for agent_id, reaction in event.recipients.items()
    }


def _display_reaction(act: DIGActivation, event_id: Optional[str]) -> str:
    if event_id is not None and event_id in act.input_reactions:
        return str(act.input_reactions[event_id])
    if event_id is None:
        # an unrecorded preview with an id-less input: nothing declared yet
        return DIGEvent.Reaction.Label.PENDING.value
    return act.reaction_to(event_id).value


def _format_detail_value(
    name: str,
    value: Any,
    time_formatter: Optional[Callable[[float], str]],
) -> str:
    if (
        time_formatter is not None
        and name in {"started_at", "ended_at"}
        and isinstance(value, (float, int))
    ):
        value = time_formatter(float(value))
    try:
        return json.dumps(
            _detail_jsonable(value),
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    except TypeError:
        return str(value)


def _detail_jsonable(value: Any) -> Any:
    if isinstance(value, DIGEvent):
        return str(value)
    if isinstance(value, DIGEvent.Reaction):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(k): _detail_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_detail_jsonable(v) for v in value]
    return value
