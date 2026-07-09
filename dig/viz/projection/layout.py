"""Timestamp-anchored layout for DIG renderers."""

from __future__ import annotations

import weakref
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from ...graph import DIGGraph
from ...node import SYSTEM_AGENT_ID
from ...util import natural_sort_key

EVENT_Y_SPREAD = 0.3


@dataclass(frozen=True)
class DIGLayout:
    """Renderer-neutral node positions and activation extents.

    All x coordinates are seconds since DIG start (``DIGGraph.offset``).
    """

    lane_for_agent: Dict[str, int]
    positions: Dict[str, Tuple[float, float]]
    activation_extent: Dict[str, Tuple[float, float]]
    agent_order: List[str]


# Render-time memo: one render pass (or an embedding renderer) calls
# compute_layout several times per frame. Viz owns the cache -- a single slot
# for the last dig laid out, held by weakref so the graph itself never carries
# render state -- keyed on activation/event counts so a growing (live) DIG
# re-derives when the counts change.
_layout_memo: Optional[Tuple[weakref.ref, Tuple[int, int], DIGLayout]] = None


def compute_layout(dig: DIGGraph) -> DIGLayout:
    """Compute node positions from recorded DIG timestamps."""
    global _layout_memo
    memo_key = (len(dig.activations), len(dig.events))
    if _layout_memo is not None:
        ref, key, cached = _layout_memo
        if ref() is dig and key == memo_key:
            return cached

    activated_agents = {
        a.agent_id for a in dig.activations.values()
        if a.agent_id != SYSTEM_AGENT_ID
    }
    registered_agents = {
        getattr(agent, "agent_id", agent_id)
        for agent_id, agent in dig.agents.items()
        if getattr(agent, "agent_id", agent_id) != SYSTEM_AGENT_ID
    }
    # Addressed-only agents get a lane too, so both views agree on which
    # agents exist: an event addressed to an agent that never fired is a
    # visible fact, not something absorbed into the producer's lane.
    addressed_agents = {
        agent_id
        for ev in dig.events.values()
        for agent_id in (
            set(ev.recipients) | {s.agent_id for s in ev.reaction_stamps}
        )
        if agent_id != SYSTEM_AGENT_ID
    }
    real_agents = sorted(
        activated_agents | registered_agents | addressed_agents,
        key=natural_sort_key,
    )
    lane_for_agent: Dict[str, int] = {
        name: idx for idx, name in enumerate(real_agents)
    }
    has_system = (
        any(a.agent_id == SYSTEM_AGENT_ID for a in dig.activations.values())
        or SYSTEM_AGENT_ID in dig.agents
    )
    if has_system:
        lane_for_agent[SYSTEM_AGENT_ID] = len(real_agents)

    agent_order: List[str] = list(real_agents)
    if has_system:
        agent_order.append(SYSTEM_AGENT_ID)

    positions: Dict[str, Tuple[float, float]] = {}
    activation_extent: Dict[str, Tuple[float, float]] = {}
    for aid, act in dig.activations.items():
        x_start = dig.offset(act.started_at)
        x_end = dig.offset(act.ended_at)
        y = lane_for_agent.get(act.agent_id, 0)
        positions[aid] = (x_start, y)
        activation_extent[aid] = (x_start, x_end)

    siblings: Dict[str, List[str]] = {}
    for eid, ev in dig.events.items():
        if ev.source_activation_id is not None:
            siblings.setdefault(ev.source_activation_id, []).append(eid)

    all_xs = [v for pair in activation_extent.values() for v in pair]
    all_xs += [dig.offset(ev.generated_at) for ev in dig.events.values()]
    x_extent = (max(all_xs) - min(all_xs)) if all_xs else 0.0
    initial_offset = x_extent * ROOT_EVENT_X_OFFSET_FRAC if x_extent > 0 else 0.01

    for eid, ev in dig.events.items():
        x, y = _event_position(
            ev, dig, lane_for_agent, siblings, initial_offset,
        )
        positions[eid] = (x, y)

    layout = DIGLayout(
        lane_for_agent=lane_for_agent,
        positions=positions,
        activation_extent=activation_extent,
        agent_order=agent_order,
    )
    _layout_memo = (weakref.ref(dig), memo_key, layout)
    return layout


def _event_position(
    event,
    dig: DIGGraph,
    lane_for_agent: Dict[str, int],
    siblings: Dict[str, List[str]],
    initial_offset: float,
) -> Tuple[float, float]:
    """Return one event node's layout position."""
    if event.source_activation_id is not None:
        src_act = dig.activations.get(event.source_activation_id)
        if src_act is not None:
            src_start = dig.offset(src_act.started_at)
            evt_gen = dig.offset(event.generated_at)
            x = (src_start + evt_gen) / 2.0
            src_lane = float(lane_for_agent.get(src_act.agent_id, 0))

            sibs = siblings.get(event.source_activation_id, [])
            if len(sibs) <= 1:
                return x, src_lane

            try:
                idx = sibs.index(event.id)
            except ValueError:
                idx = 0
            n = len(sibs)
            offset = -EVENT_Y_SPREAD + (2 * EVENT_Y_SPREAD * idx / (n - 1))
            return x, src_lane + offset

    x = dig.offset(event.generated_at) - initial_offset
    recipient_ys: List[float] = []
    for recipient in event.recipients:
        if recipient in lane_for_agent:
            recipient_ys.append(float(lane_for_agent[recipient]))
    if recipient_ys:
        y = sum(recipient_ys) / len(recipient_ys)
    else:
        y = 0.0
    return x, y


ROOT_EVENT_X_OFFSET_FRAC = 0.04
