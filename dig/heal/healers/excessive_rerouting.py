"""
excessive_rerouting.py

ExcessiveReroutingHealer -- an event has been rerouted more than the
allowed number of times. Signals that the team is passing the same
work around without anyone actually doing it (often because every
candidate hit a capacity rejection or didn't know what to do with it).

Trigger (graph-structural): count of reroute OCCURRENCES, derived from the
event's append-only log (REACTED reroute stamps + MODIFIED "reroute" stamps)
plus the current reaction records, deduped by the rerouting actor. The
current-state view alone is not enough: a ping-pong reroute rewrites the
same recipient entries each hop, so only the log accumulates.

Intervention: annotate the event with a "stop rerouting -- handle it"
system message. No reroute (the system shouldn't pick the new owner;
the current recipients should resolve it).
"""

from __future__ import annotations

from typing import Dict, List, Set

from ...graph import (
    DIGActivation,
    DIGEvent,
    DIGGraph,
)
from ..intervention import Intervention
from ..healer import Healer


class ExcessiveReroutingHealer(Healer):
    name = "ExcessiveReroutingHealer"

    def __init__(self, *, max_reroutes: int = 2) -> None:
        super().__init__()
        self._max_reroutes = max_reroutes
        self._seen: Set[str] = set()

    def on_activation_complete(
        self,
        dig: DIGGraph,
        activation: DIGActivation,
    ) -> List[Intervention]:
        # Only check events that the just-completed activation rerouted --
        # the rest of the DIG's reroute counts can't have changed.
        rerouted_ids = [
            ev_id for ev_id in activation.input_event_ids
            if self._was_rerouted_by(dig.events.get(ev_id), activation.id)
        ]
        if not rerouted_ids:
            return []

        counts = self._reroute_counts(dig, rerouted_ids)
        interventions: List[Intervention] = []
        for ev_id, count in counts.items():
            if count <= self._max_reroutes:
                continue
            if ev_id in self._seen:
                continue
            event = dig.events.get(ev_id)
            if event is None:
                continue
            self._seen.add(ev_id)
            interventions.append(self._build_intervention(event, count))
        return interventions

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _reroute_counts(
        dig: DIGGraph,
        event_ids: List[str],
    ) -> Dict[str, int]:
        counts: Dict[str, int] = {ev_id: 0 for ev_id in event_ids}
        for ev_id in set(event_ids):
            event = dig.events.get(ev_id)
            if event is None:
                continue
            counts[ev_id] = ExcessiveReroutingHealer._reroute_count(event)
        return counts

    @staticmethod
    def _reroute_count(event: DIGEvent) -> int:
        """Reroute occurrences for one event: distinct rerouting actors seen
        in the log and the current entries. An agent's reroute leaves a
        REACTED stamp (its activation id) and usually a MODIFIED "reroute"
        transport stamp with the same id; a system rewrite leaves a MODIFIED
        stamp (the system activation id). Deduping on the actor makes each
        reroute act count exactly once, and stamps are append-only, so
        ping-pong hops accumulate even though the current-state recipient
        entries are rewritten each time."""
        actors: Set[str] = set()
        for stamp in event.timestamps:
            if (
                stamp.label == DIGEvent.Timestamp.Label.REACTED
                and stamp.reaction_label == DIGEvent.Reaction.Label.REROUTE
                and stamp.activation_id
            ):
                actors.add(stamp.activation_id)
            elif (
                stamp.label == DIGEvent.Timestamp.Label.MODIFIED
                and stamp.metadata.get("change") == "reroute"
                and (stamp.activation_id or stamp.by)
            ):
                # The rewrite actor is an activation id (stamp.activation_id);
                # `by` is only a fallback for agent-actor stamps.
                actors.add(stamp.activation_id or stamp.by)
        for reaction in event.recipients.values():
            if (
                reaction.label == DIGEvent.Reaction.Label.REROUTE
                and reaction.routed_by
            ):
                actors.add(reaction.routed_by)
        return len(actors)

    @staticmethod
    def _was_rerouted_by(event: DIGEvent | None, activation_id: str | None) -> bool:
        # Read the log, not just current state: a self-reroute (the rerouter
        # among the new recipients) overwrites its own REROUTE entry with a
        # fresh PENDING before this hook runs, but the REACTED stamp stays.
        if event is None or activation_id is None:
            return False
        if any(
            stamp.label == DIGEvent.Timestamp.Label.REACTED
            and stamp.reaction_label == DIGEvent.Reaction.Label.REROUTE
            and stamp.activation_id == activation_id
            for stamp in event.timestamps
        ):
            return True
        return any(
            reaction.label == DIGEvent.Reaction.Label.REROUTE and reaction.routed_by == activation_id
            for reaction in event.recipients.values()
        )

    def _build_intervention(
        self,
        event: DIGEvent,
        reroute_count: int,
    ) -> Intervention:
        problem_id = event.metadata.get("problem_id") or event.payload.get(
            "problem_id", "unknown"
        )
        message = (
            f"SYSTEM NOTICE: This event (problem_id={problem_id}) "
            f"has been rerouted {reroute_count} times -- over the limit of "
            f"{self._max_reroutes}. DO NOT REROUTE again. Try your best to "
            f"handle it -- break it into smaller pieces if it is too "
            f"large -- and share the result with everyone including yourself."
        )
        return Intervention.annotate(
            label=Intervention.Label.EXCESSIVE_REROUTING.value,
            target_event_id=event.id,
            message=message,
            metadata={
                "reroute_count": reroute_count,
                "max_reroutes": self._max_reroutes,
                "problem_id": problem_id,
            },
        )
