"""
dependency_warning.py

DependencyWarningHealer -- an agent has pending events in its buffer that
come from different ancestor "generators" at the same depth, suggesting
it's about to mix partials from disjoint lineages.

Trigger (graph-structural): scanning the agent's pending events (events
the agent has received but not yet consumed in any of its activations),
at least two relevant events have distinct problem-generating ancestors
at the same backward depth.

A problem-generating activation is, by default, one whose recorded shape
emitted more events than it consumed -- the structural
PROBLEM_REDUCING/GENERATING label DIG already derives; it is how new
sub-problems enter the DIG. The structural label is a proxy (a firing's
inputs are its whole buffer), so a domain with an exact notion of
generation can pass `is_generator` instead (e.g. a runtime that checks
for a decompose-family tool call).

Which pending events count as mixable partials is likewise domain
knowledge: `relevant` narrows the watched events (e.g. a runtime passes
a predicate for its solution events); with `relevant=None` every pending
event counts.

Intervention: annotate each implicated event with metadata identifying
its generator, so the agent's next activation gets the lineage hint
inline. The Runtime should prefer events from the same ancestor.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Set, Tuple

from ...graph import DIGActivation, DIGEvent, DIGGraph, SYSTEM_AGENT_ID
from ..intervention import Intervention
from ..healer import Healer


class DependencyWarningHealer(Healer):
    name = "DependencyWarningHealer"

    def __init__(
        self,
        *,
        max_depth: int = 10,
        relevant: Optional[Callable[[DIGEvent], bool]] = None,
        is_generator: Optional[Callable[[DIGActivation], bool]] = None,
    ) -> None:
        super().__init__()
        self._max_depth = max_depth
        self._relevant = relevant
        self._is_generator = is_generator
        # Dedup keyed on (recipient, sorted event_ids) so we don't
        # re-emit while the same buffer state persists across ticks.
        self._seen: Set[Tuple[str, Tuple[str, ...]]] = set()

    def on_event_delivered(
        self,
        dig: DIGGraph,
        event: DIGEvent,
        recipients: List[str],
    ) -> List[Intervention]:
        interventions: List[Intervention] = []
        for agent in recipients:
            interventions.extend(self._check_agent(dig, agent))
        return interventions

    # ------------------------------------------------------------------
    # Per-recipient lineage check
    # ------------------------------------------------------------------

    def _check_agent(
        self,
        dig: DIGGraph,
        agent: str,
    ) -> List[Intervention]:
        pending = self._pending_relevant_events(dig, agent)
        if len(pending) < 2:
            return []

        key = (agent, tuple(sorted(ev.id for ev in pending)))
        if key in self._seen:
            return []

        # Find the closest problem-generating ancestor for each pending event.
        gens: Dict[str, Tuple[Optional[str], int]] = {}
        by_level: Dict[int, Set[str]] = {}
        for ev in pending:
            gen, level = self._find_generator(dig, ev)
            gens[ev.id] = (gen, level)
            if gen:
                by_level.setdefault(level, set()).add(gen)

        # Conflict iff some depth has multiple distinct generators.
        if not any(len(gs) > 1 for gs in by_level.values()):
            return []

        self._seen.add(key)
        return [
            self._build_intervention(ev_id, gens[ev_id][0], agent)
            for ev_id in gens
            if gens[ev_id][0] is not None
        ]

    def _pending_relevant_events(
        self,
        dig: DIGGraph,
        agent: str,
    ) -> List[DIGEvent]:
        # Events received by this agent and still in play: not yet drained
        # out of its buffer by a firing. Drained = presented with any
        # reaction but WAIT (consume/discard/reroute all settle the copy);
        # a WAITED event stays pending, and a FAILED firing drained nothing.
        consumed: Set[str] = set()
        for act in dig.activations.values():
            if act.agent_id != agent or act.failed:
                continue
            consumed.update(
                eid for eid in act.input_event_ids
                if act.reaction_to(eid) != DIGEvent.Reaction.Label.WAIT
            )

        pending = []
        for ev in dig.events.values():
            if agent not in ev.received_at:
                continue
            if ev.id in consumed:
                continue
            if self._relevant is not None and not self._relevant(ev):
                continue
            pending.append(ev)
        return pending

    def _generates(self, act: DIGActivation) -> bool:
        if self._is_generator is not None:
            return self._is_generator(act)
        return act.label == DIGActivation.Label.PROBLEM_GENERATING

    def _find_generator(
        self,
        dig: DIGGraph,
        event: DIGEvent,
    ) -> Tuple[Optional[str], int]:
        """Walk backward through source activations until we hit a
        problem-generating one (`is_generator` if provided, else the
        structural label: it emitted more than it consumed; system
        activations don't count). Returns (agent_id, steps_back) -- or
        (None, depth_reached) if no generator was found within
        `max_depth`."""
        current_id = event.source_activation_id
        steps = 0
        while current_id and steps < self._max_depth:
            act = dig.activations.get(current_id)
            if act is None:
                break
            if act.agent_id != SYSTEM_AGENT_ID and self._generates(act):
                return act.agent_id, steps
            # Move to the parent: source activation of the first input.
            if not act.input_event_ids:
                break
            first_input = dig.events.get(act.input_event_ids[0])
            if first_input is None:
                break
            current_id = first_input.source_activation_id
            steps += 1
        return None, steps

    @staticmethod
    def _build_intervention(
        event_id: str,
        generator: str,
        agent: str,
    ) -> Intervention:
        message = (
            f"This event was generated by {generator}. When you have "
            f"multiple pending items, prioritize items from the same "
            f"ancestor -- mixing disjoint lineages risks inconsistent results."
        )
        return Intervention.annotate(
            label=Intervention.Label.DEPENDENCY_WARNING.value,
            target_event_id=event_id,
            message=message,
            metadata={
                "generator": generator,
                "receiving_agent": agent,
            },
        )
