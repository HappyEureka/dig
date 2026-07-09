"""
orphan.py

OrphanEventHealer -- an event has been delivered to recipients but
ended up with no live consumer (all recipients discarded or rerouted
it away, and no productive activation took it as input).

Trigger (graph-structural): the event is past a small age threshold,
no live recipient still holds it, and no activation consumed it
productively.

Intervention: annotate the event with a system message and reroute it
back to its source agent so the originator can decide what to do
(re-send, discard, or handle itself).
"""

from __future__ import annotations

import time
from typing import List, Set

from ...graph import (
    DIGActivation,
    DIGEvent,
    DIGGraph,
    SYSTEM_AGENT_ID,
)
from ..intervention import Intervention
from ..healer import Healer


class OrphanEventHealer(Healer):
    name = "OrphanEventHealer"

    def __init__(self, *, orphan_timeout_sec: float = 5.0) -> None:
        super().__init__()
        self._orphan_timeout_sec = orphan_timeout_sec
        self._seen: Set[str] = set()  # event ids we've already flagged

    def on_activation_complete(
        self,
        dig: DIGGraph,
        activation: DIGActivation,
    ) -> List[Intervention]:
        # An activation that discards or reroutes may create orphans;
        # scan right away so we surface them at the earliest moment.
        return self._scan(dig)

    def on_idle_tick(
        self,
        dig: DIGGraph,
        idle_cycles: int,
    ) -> List[Intervention]:
        # Backup scan: catches events that orphaned without an
        # activation completing recently (e.g. recipients never showed up).
        return self._scan(dig)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _scan(self, dig: DIGGraph) -> List[Intervention]:
        now = time.time()  # wall-clock age, matching event.generated_at (its own time)
        interventions: List[Intervention] = []
        for ev_id, event in dig.events.items():
            if ev_id in self._seen:
                continue
            if not self._is_orphan(dig, event, now):
                continue
            source_agent = self._source_agent_of(dig, event)
            if source_agent is None:
                # No human agent to route back to (e.g. system event).
                continue
            self._seen.add(ev_id)
            interventions.append(self._build_intervention(event, source_agent, now))
        return interventions

    def _is_orphan(
        self,
        dig: DIGGraph,
        event: DIGEvent,
        now: float,
    ) -> bool:
        # Never addressed to anyone -> not an orphan: nothing was dropped;
        # a recipient-less record is the producer's choice, not a failure.
        if not event.recipients:
            return False

        # System events are never considered orphan candidates.
        if event.source_activation_id:
            src_act = dig.activations.get(event.source_activation_id)
            if src_act and src_act.agent_id == SYSTEM_AGENT_ID:
                return False

        # Must be old enough -- fresh events haven't had a chance yet.
        if now - event.generated_at < self._orphan_timeout_sec:
            return False

        # Live recipients still pending => not orphan.
        if any(
            reaction.label in {
                DIGEvent.Reaction.Label.PENDING,
                DIGEvent.Reaction.Label.WAIT,
            }
            for reaction in event.recipients.values()
        ):
            return False

        # Productive consumption means some AGENT is doing useful work with
        # it -- the event's own REACTED stamps already answer that. A system
        # activation citing the event as intervention evidence is not work.
        if any(
            stamp.reaction_label == DIGEvent.Reaction.Label.CONSUME
            and stamp.agent_id != SYSTEM_AGENT_ID
            for stamp in event.reaction_stamps
        ):
            return False
        return True

    @staticmethod
    def _source_agent_of(
        dig: DIGGraph,
        event: DIGEvent,
    ) -> str | None:
        if not event.source_activation_id:
            return None
        src_act = dig.activations.get(event.source_activation_id)
        if src_act is None or src_act.agent_id == SYSTEM_AGENT_ID:
            return None
        return src_act.agent_id

    @staticmethod
    def _build_intervention(
        event: DIGEvent,
        source_agent: str,
        now: float,
    ) -> Intervention:
        age = now - event.generated_at
        message = (
            f"SYSTEM: Your event {event.id} (age={age:.1f}s) "
            f"ended up with no live recipient (every recipient discarded "
            f"or rerouted it away). Please review and decide: "
            f"(1) reroute to a different agent, (2) discard if no longer "
            f"needed, or (3) handle it yourself."
        )
        return Intervention.annotate(
            label=Intervention.Label.ORPHANED_EVENT.value,
            target_event_id=event.id,
            message=message,
            reroute_to=[source_agent],
            metadata={
                "orphaned_age_sec": age,
                "source_agent": source_agent,
            },
        )
