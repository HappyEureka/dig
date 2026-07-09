"""DIGGraph facade and recording core."""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Mapping, Optional

from ..node import DIGActivation, DIGEvent
from ..util.validate import expect_type, is_instance_sequence, jsonable
from .delivery import DIGDelivery
from .roster import DIGRoster


class DIGGraph(
    DIGRoster,
    DIGDelivery,
):
    """Public DIG facade: the graph REPRESENTATION -- event/activation
    stores, the recording funnels, and delivery/observation over registered
    agents. It answers nothing itself: derived views (bipartite edges,
    lineage/coverage) are questions you ask OF the graph and live in
    `dig.views`."""

    events: Dict[str, DIGEvent]
    activations: Dict[str, DIGActivation]
    # Registered agents expose their own visible_state(); DIG does not own runtime state.
    agents: Dict[str, Any]

    def __init__(self):
        """Create an empty DIG."""
        self.events = {}
        self.activations = {}
        self.agents = {}
        self._event_counter = 0
        self._activation_counter = 0
        self._created_at = time.time()
        self._listeners: List[Callable[[], None]] = []

    def offset(self, at: float) -> float:
        """Return seconds since this DIG was created."""
        return at - self._created_at

    def subscribe(self, listener: Callable[[], None]) -> None:
        """Call `listener()` after every graph mutation (record/deliver/update).

        This is the substrate's only outward hook; live renderers and other
        observers attach here. DIG never imports them.
        """
        self._listeners.append(listener)

    def _notify_update(self) -> None:
        for listener in self._listeners:
            listener()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the recorded representation: events, activations,
        counters. Derived reads (the bipartite edge list, lineage, applied
        intervention counts) are query answers, not representation --
        artifact writers enrich with them via `dig.views` and
        `dig.heal.intervention_stats`."""
        return {
            "schema": "dig.graph.v2",
            "created_at": self._created_at,
            "events": {
                event_id: jsonable(event)
                for event_id, event in self.events.items()
            },
            "activations": {
                activation_id: jsonable(activation)
                for activation_id, activation in self.activations.items()
            },
            "event_counter": self._event_counter,
            "activation_counter": self._activation_counter,
        }

    @classmethod
    def _merge_metadata(
        cls,
        target: Dict[str, Any],
        updates: Mapping[str, Any],
    ) -> None:
        for key, value in updates.items():
            if isinstance(value, Mapping) and isinstance(target.get(key), dict):
                cls._merge_metadata(target[key], value)
            else:
                target[key] = dict(value) if isinstance(value, Mapping) else value

    def update_activation_metadata(
        self,
        activation_id: str,
        updates: Mapping[str, Any],
    ) -> DIGActivation:
        """Deep-merge metadata updates into a recorded activation."""
        if activation_id not in self.activations:
            raise KeyError(f"unknown DIG activation id: {activation_id}")
        expect_type(updates, Mapping, what="DIGGraph.update_activation_metadata")

        activation = self.activations[activation_id]
        checked_updates = DIGActivation.normalize_metadata(dict(updates))
        self._merge_metadata(activation.metadata, checked_updates)
        activation.metadata = DIGActivation.normalize_metadata(activation.metadata)
        self._notify_update()
        return activation

    def record_event(self, event: DIGEvent, *, _notify: bool = True) -> DIGEvent:
        """Record a DIG event, assigning an id if needed."""
        expect_type(event, DIGEvent, what="DIGGraph.record_event")
        if event.id is not None and event.id in self.events:
            return self.events[event.id]
        if event.id is None:
            # Never overwrite a caller-preset id: skip minted ids already
            # taken (a deserialized or framework-carried "eN" is legitimate).
            self._event_counter += 1
            while f"e{self._event_counter}" in self.events:
                self._event_counter += 1
            event.id = f"e{self._event_counter}"
        event.stamp_generated()
        self.events[event.id] = event
        src = self.activations.get(event.source_activation_id)
        if src is not None and event.id not in src.output_event_ids:
            src.outputs.append(event)   # output_event_ids is derived from outputs
            src.annotate_recorded()     # keep the structural stamp true under late links
        if _notify:
            self._notify_update()
        return event

    def reroute_event(
        self,
        event: DIGEvent,
        *,
        to: List[str],
        by: str,
        from_recipients: "List[str] | None" = None,
    ) -> DIGEvent:
        """Rewrite a recorded event's recipient routing and DIVERT the event:
        rerouted-away recipients stop receiving it (`deliver` skips REROUTE
        entries) and their unconsumed buffered copies are retracted; the new
        recipients are delivered to.

        `from_recipients=None` (the system/healer default) flips the LIVE
        recipients -- those still PENDING or WAIT. Recipients who already
        consumed or discarded keep their declared reaction: a routing rewrite
        redirects outstanding work, it does not rewrite history. Pass
        `from_recipients=[...]` to name the flipped set explicitly (`[]` =
        transport only, e.g. when the flip was already declared with a
        firing).

        Naming a recipient in `to` declares NEW outstanding work for them --
        a fresh PENDING entry and a fresh copy, even if they reacted to this
        event before (the append-only stamps keep that history). `by` must
        be unique per reroute act (an activation id): occurrence counts
        derived from the log dedup on it."""
        previous = event.recipient_reactions_snapshot()
        if from_recipients is None:
            live = {
                DIGEvent.Reaction.Label.PENDING,
                DIGEvent.Reaction.Label.WAIT,
            }
            flipping = [
                recipient
                for recipient, reaction in event.recipients.items()
                if reaction.label in live
            ]
        else:
            flipping = from_recipients
        for recipient in flipping:
            if recipient not in event.recipients:
                continue
            # REPLACE the entry, never mutate through it: the old entry may be
            # a past activation's declared record, which a routing rewrite must
            # not edit (the stamps + this MODIFIED stamp carry the history).
            event.recipients[recipient] = DIGEvent.Reaction(
                label=DIGEvent.Reaction.Label.REROUTE,
                routed_by=by,
            )
            agent = self.agents.get(recipient)
            if agent is not None:
                agent.mailbox.retract(event)
        deliverable = event.delivery_policy is not None
        for recipient in to:
            event.recipients[recipient] = DIGEvent.Reaction()
        event.stamp_modified(
            activation_id=by,   # the actor is an ACTIVATION; `by` is for agent ids
            change="reroute",
            previous_recipient_reactions=previous,
            recipients=event.recipient_reactions_snapshot(),
        )
        if deliverable:
            for recipient in to:
                agent = self.agents.get(recipient)
                if agent is not None:
                    # Hand over directly: a rerouted-back recipient may carry
                    # an old DELIVERED stamp that `deliver` would dedup on,
                    # but the rewrite intends a fresh copy. Reset the
                    # recipient's dedup memory first -- they may have SETTLED
                    # this event in a past firing (consumed/rerouted it, so
                    # its id sits in mailbox.seen); being named anew makes it
                    # fresh work again.
                    agent.mailbox.retract(event)
                    agent.receive(event)
            self.deliver(event)
        self._notify_update()
        return event

    def _next_activation_id(self) -> str:
        """Mint the next activation id, skipping ids already taken."""
        self._activation_counter += 1
        while f"a{self._activation_counter}" in self.activations:
            self._activation_counter += 1
        return f"a{self._activation_counter}"

    def record_activation(self, activation: DIGActivation) -> DIGActivation:
        """Record a DIG activation in place: the node you pass in IS the
        recorded node. Assigns its id, interns its input/output events,
        normalizes its reaction (dense: one entry per input) and metadata
        annotations, stamps the span, stores it, and applies the per-input
        reaction."""
        expect_type(activation, DIGActivation, what="DIGGraph.record_activation")
        if activation.id is not None and activation.id in self.activations:
            raise ValueError(
                f"DIG activation {activation.id!r} is already recorded"
            )
        # Validate everything that can raise BEFORE mutating: a rejected
        # activation must leave no partially interned events behind.
        if not is_instance_sequence(activation.inputs, DIGEvent):
            raise TypeError("DIGActivation.inputs must be a sequence of DIGEvent")
        if not is_instance_sequence(activation.outputs, DIGEvent):
            raise TypeError("DIGActivation.outputs must be a sequence of DIGEvent")
        if not activation.failed:
            DIGActivation.check_input_reactions_shape(
                activation.inputs,
                activation.input_reactions or None,
            )
        aid = self._next_activation_id()
        activation.inputs = [
            self.record_event(e, _notify=False) for e in activation.inputs
        ]
        if activation.failed:
            # A failed firing records the attempt only: no reactions are
            # declared (its inputs stay pending for a retry) and nothing was
            # produced -- shaped-but-unfinished outputs are dropped unrecorded.
            activation.outputs = []
            activation.input_reactions = {}
        else:
            output_events: List[DIGEvent] = []
            for e in activation.outputs:
                # Claim provenance only for events this firing actually
                # minted: an already-recorded event flowing through outputs,
                # or one carrying declared provenance, keeps its original
                # producer.
                already_recorded = e.id is not None and e.id in self.events
                if not already_recorded and e.source_activation_id is None:
                    e.source_activation_id = aid   # this firing produced it
                output_events.append(self.record_event(e, _notify=False))
            activation.outputs = output_events
            activation.input_reactions = DIGActivation.normalize_input_reactions(
                activation.inputs,
                activation.input_reactions or None,
            )
        activation.annotate_recorded()  # the node stamps its own dig namespace
        now = time.time()
        if activation.started_at is None:
            activation.started_at = now
        if activation.ended_at is None:
            activation.ended_at = now
        activation.tool_calls = list(activation.tool_calls or [])
        activation.id = aid
        self.activations[aid] = activation

        if not activation.failed:
            for e in activation.inputs:
                e.apply_reaction(
                    activation.input_reactions[e.id],
                    agent_id=activation.agent_id,
                    activation_id=aid,
                )

        self._notify_update()
        return activation
