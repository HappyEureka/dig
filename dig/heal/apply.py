"""Intervention application -- how an intervention mutates the DIG.

Healing is three concepts, each owned by one place: a healer's
hooks DETECT and propose `Intervention`s; the healer's optional
`prepare_intervention` FINALIZES one just before application (e.g. picks a
designated handler from live load); `apply_intervention` here MUTATES the
graph by strategy. Detectors own no graph-mutation mechanics.
"""

from __future__ import annotations

from typing import List, Optional

from ..graph import (
    DIGActivation,
    DIGEvent,
    DIGGraph,
    SYSTEM_AGENT_ID,
)
from ..node import (
    EVENT_INTERVENTION_MESSAGE,
    EVENT_INTERVENTION_TYPE,
    EVENT_SYSTEM_ACTIVATION_ID,
)
from .intervention import Intervention


def _intervention_activation(
    itv: Intervention,
    *,
    inputs: Optional[List[DIGEvent]] = None,
    outputs: Optional[List[DIGEvent]] = None,
) -> DIGActivation:
    return DIGActivation(
        agent_id=SYSTEM_AGENT_ID,
        inputs=list(inputs or []),
        outputs=list(outputs or []),
        metadata={"dig": {"intervention": itv.label}},
    )


async def apply_intervention(
    itv: Intervention,
    *,
    dig: DIGGraph,
) -> Optional[DIGEvent]:
    """Apply one intervention by strategy.

    An ill-formed intervention -- unknown strategy, missing/unknown target,
    no recipients, or a cited input event not in the graph -- raises
    ValueError: a healer citing a nonexistent node is a bug, never a silent
    no-op."""
    if itv.strategy == Intervention.Strategy.ANNOTATE:
        return await _apply_annotate(itv, dig=dig)
    if itv.strategy == Intervention.Strategy.CREATE:
        return await _apply_create(itv, dig=dig)
    raise ValueError(f"unknown intervention strategy: {itv.strategy!r}")


async def _apply_annotate(
    itv: Intervention,
    *,
    dig: DIGGraph,
) -> Optional[DIGEvent]:
    if itv.target_event_id is None:
        raise ValueError(f"annotate intervention {itv.label!r} has no target_event_id")
    event = dig.events.get(itv.target_event_id)
    if event is None:
        raise ValueError(
            f"annotate intervention {itv.label!r} targets unknown event "
            f"{itv.target_event_id!r}"
        )

    sys_act = dig.record_activation(_intervention_activation(itv))

    # Annotations live in metadata (the annotation seam); the payload stays
    # the domain's opaque content and is never written by healers. The keys
    # are shared constants (`dig.node`) so the heal writers and the
    # views/viz readers can never drift apart.
    event.metadata[EVENT_INTERVENTION_TYPE] = itv.label
    event.metadata[EVENT_SYSTEM_ACTIVATION_ID] = sys_act.id
    event.metadata[EVENT_INTERVENTION_MESSAGE] = itv.message
    for k, v in itv.metadata.items():
        event.metadata[k] = v
    event.stamp_modified(
        by=SYSTEM_AGENT_ID,
        change="annotate",
        intervention_type=itv.label,
        system_activation_id=sys_act.id,
        message=itv.message,
    )

    if itv.reroute_to:
        dig.reroute_event(event, to=itv.reroute_to, by=sys_act.id)

    return event


async def _apply_create(
    itv: Intervention,
    *,
    dig: DIGGraph,
) -> Optional[DIGEvent]:
    if not itv.recipients:
        raise ValueError(f"create intervention {itv.label!r} has no recipients")

    input_events = []
    missing = []
    for ev_id in (itv.input_event_ids or []):
        ev = dig.events.get(ev_id)
        if ev is None:
            missing.append(ev_id)
        else:
            input_events.append(ev)
    if missing:
        raise ValueError(
            f"create intervention {itv.label!r} cites unknown input events: {missing}"
        )

    metadata = {
        EVENT_INTERVENTION_TYPE: itv.label,
        EVENT_INTERVENTION_MESSAGE: itv.message,
    }
    for k, v in itv.metadata.items():
        metadata[k] = v

    ev = DIGEvent(
        payload={},
        recipients={recipient: DIGEvent.Reaction() for recipient in itv.recipients},
        metadata=metadata,
    )
    dig.record_activation(_intervention_activation(
        itv,
        inputs=input_events,
        outputs=[ev],
    ))

    dig.deliver(ev)  # fans out through the event's recipients

    return ev
