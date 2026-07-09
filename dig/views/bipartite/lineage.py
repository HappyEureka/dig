"""Lineage analysis of the bipartite view.

DIG coverage is interaction-lineage coverage: it asks whether an
activation's backward event lineage reaches the run's root events.
It does not assert task/artifact completeness; task correctness belongs
to a task/environment layer.

Provenance follows CONSUMED inputs only: an input the firing WAITED on,
DISCARDED, or REROUTED was not used, so it joins no lineage (the reaction
vocabulary exists exactly to make that distinction). FAILED firings
neither consume nor produce, so the coverage analyses skip them.
"""

from __future__ import annotations

from typing import List, Set

from ...graph import DIGActivation, DIGEvent, DIGGraph, SYSTEM_AGENT_ID


def root_events(dig: DIGGraph) -> List[DIGEvent]:
    """Events with no producing activation -- whether present from the
    start or injected mid-run without a source. Lineage/coverage checks
    quantify over these."""
    return [
        event for event in dig.events.values()
        if event.source_activation_id is None
    ]


def submit_activations(dig: DIGGraph) -> List[DIGActivation]:
    """Activations with the DIG submit annotation set (a FAILED firing did
    not submit, whatever it was attempting)."""
    return [
        activation for activation in dig.activations.values()
        if activation.is_submitting and not activation.failed
    ]


def lineage_event_ids_from(dig: DIGGraph, activation_id: str) -> Set[str]:
    """Backward event lineage reachable from one activation. A FAILED
    firing consumed nothing, so its lineage is empty."""
    start = dig.activations.get(activation_id)
    if start is not None and start.failed:
        return set()
    visited_events: Set[str] = set()
    visited_activations: Set[str] = {activation_id}
    queue: List[str] = [activation_id]
    while queue:
        current_id = queue.pop()
        activation = dig.activations.get(current_id)
        if activation is None:
            continue
        for event_id in activation.consumed_event_ids:   # used inputs only
            if event_id in visited_events:
                continue
            visited_events.add(event_id)
            event = dig.events.get(event_id)
            if event is None or event.source_activation_id is None:
                continue
            source_id = event.source_activation_id
            if source_id not in visited_activations:
                visited_activations.add(source_id)
                queue.append(source_id)
    return visited_events


def lineage_covers_root_events(dig: DIGGraph, activation_id: str) -> bool:
    """Whether an activation's backward lineage reaches every root event.

    Walks backward with early exit: stops as soon as every root has been
    seen, instead of materializing the full lineage first."""
    remaining = {event.id for event in root_events(dig)}
    if not remaining:
        return True
    start = dig.activations.get(activation_id)
    if start is not None and start.failed:
        return False   # a failed firing consumed nothing; it covers nothing
    visited_events: Set[str] = set()
    visited_activations: Set[str] = {activation_id}
    queue: List[str] = [activation_id]
    while queue and remaining:
        current_id = queue.pop()
        activation = dig.activations.get(current_id)
        if activation is None:
            continue
        for event_id in activation.consumed_event_ids:   # used inputs only
            if event_id in visited_events:
                continue
            visited_events.add(event_id)
            remaining.discard(event_id)
            event = dig.events.get(event_id)
            if event is None or event.source_activation_id is None:
                continue
            source_id = event.source_activation_id
            if source_id not in visited_activations:
                visited_activations.add(source_id)
                queue.append(source_id)
    return not remaining


def uncovered_root_events(dig: DIGGraph, activation_id: str) -> List[DIGEvent]:
    """Root events missing from one activation's backward lineage."""
    lineage = lineage_event_ids_from(dig, activation_id)
    return [
        event for event in root_events(dig)
        if event.id not in lineage
    ]


def untouched_root_events(dig: DIGGraph) -> List[DIGEvent]:
    """Root events that no activation has yet consumed."""
    consumed_ids: Set[str] = set()
    for activation in dig.activations.values():
        if activation.failed:
            continue   # a failed firing consumed nothing
        consumed_ids.update(activation.consumed_event_ids)
    return [
        event for event in root_events(dig)
        if event.id not in consumed_ids
    ]


def any_coverage_complete(dig: DIGGraph) -> bool:
    """Whether any non-system activation covers every root event.

    Root r is in activation A's backward lineage iff A is forward-reachable
    from r (event -> consuming activation -> its outputs -> ...), so instead
    of one backward walk per activation this does one forward walk per root
    and intersects: O(roots x graph), not O(activations x graph)."""
    if not any(
        activation.agent_id != SYSTEM_AGENT_ID and not activation.failed
        for activation in dig.activations.values()
    ):
        return False
    roots = root_events(dig)
    if not roots:
        return True  # an empty root set is covered by any activation

    consumers: dict[str, List[str]] = {}
    for aid, activation in dig.activations.items():
        if activation.failed:
            continue   # a failed firing consumed nothing and produced nothing
        for event_id in activation.consumed_event_ids:   # used inputs only
            consumers.setdefault(event_id, []).append(aid)

    covering: Set[str] | None = None
    for root in roots:
        reachable: Set[str] = set()
        seen_events: Set[str] = {root.id}
        queue: List[str] = [root.id]
        while queue:
            event_id = queue.pop()
            for aid in consumers.get(event_id, ()):
                if aid in reachable:
                    continue
                reachable.add(aid)
                for output in dig.activations[aid].outputs:
                    # Follow only events this activation actually PRODUCED:
                    # the backward walk trusts source_activation_id, and a
                    # passed-through output (recorded elsewhere, flowing
                    # through this outputs list) must not smuggle coverage.
                    if output.source_activation_id != aid:
                        continue
                    if output.id not in seen_events:
                        seen_events.add(output.id)
                        queue.append(output.id)
        covering = reachable if covering is None else covering & reachable
        if not covering:
            return False
    return any(
        dig.activations[aid].agent_id != SYSTEM_AGENT_ID for aid in covering
    )
